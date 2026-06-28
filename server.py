"""FastAPI server — REST API + WebSocket for Electron frontend."""
import asyncio, json, logging, os, sys, tempfile, threading, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, File, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from application.orchestrator import SayitOrchestrator
from application.eventbus import Events
from application.usecases import UseCases
from infrastructure.config_store import ConfigStore
from infrastructure.asr import AsrCascade

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")

app = FastAPI(title="Sayit Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Init backend (wrapped for graceful failure) ─────
try:
    orchestrator = SayitOrchestrator()
except Exception as e:
    logger.critical("Orchestrator init failed: %s", e)
    raise  # Let the process crash visibly — Electron's main.js error handler will catch stderr
config = orchestrator.get_config()
db = orchestrator.get_database()
hotwords = orchestrator.get_hotwords_manager()
usecases = UseCases(db, config, hotwords)
ws_clients: list[WebSocket] = []

# ── Current recording session ─────────────────────
_current_session_id: str = ""


async def broadcast(data: dict):
    global _current_session_id
    # Attach current session_id to every broadcast unless already set
    if "session_id" not in data and _current_session_id:
        data["session_id"] = _current_session_id
    msg = json.dumps(data, ensure_ascii=False)
    for ws in ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            pass


# ── Wire events to WebSocket ──────────────────────
import queue, threading
_event_queue = queue.Queue()

def _process_events():
    """Process events on the asyncio event loop (called from FastAPI startup)."""
    loop = asyncio.get_event_loop()
    def _drain():
        loop = asyncio.get_event_loop()
        def _do():
            try:
                while True:
                    try: data = _event_queue.get_nowait()
                    except: break
                    try: asyncio.ensure_future(broadcast(data))
                    except: pass
            finally:
                loop.call_later(0.05, _do)
        loop.call_soon(_do)
    loop.call_soon(_drain)

@app.on_event("startup")
async def startup_event():
    _process_events()

def wire_events():
    eb = orchestrator.eventbus

    def _on_recording_started(session_id=""):
        global _current_session_id
        _current_session_id = session_id or uuid.uuid4().hex[:12]
        _event_queue.put({"event": "recording_started", "session_id": _current_session_id})

    eb.on(Events.RECORDING_STARTED, _on_recording_started)
    eb.on(Events.RMS_LEVEL, lambda l: _state.update({"last_rms": l}))
    eb.on(Events.RECORDING_STOPPED, lambda: _event_queue.put({"event": "recording_stopped"}))
    eb.on(Events.RECORDING_STOPPING, lambda: _event_queue.put({"event": "recording_stopping"}))
    eb.on(Events.RECORDING_TICK, lambda s: _event_queue.put({"event": "tick", "seconds": s}))
    eb.on(Events.RMS_LEVEL, lambda l: _event_queue.put({"event": "rms_level", "level": l}))
    eb.on(Events.ASR_RESULT, lambda t, e: _event_queue.put({"event": "asr_result", "text": t, "engine": e}))
    eb.on(Events.ASR_PARTIAL, lambda t, e: _event_queue.put({"event": "asr_partial", "text": t, "engine": e}))
    eb.on(Events.ASR_PROGRESS, lambda s, m, e="": _event_queue.put({
        "event": "asr_progress", "stage": s, "message": m, "engine": e,
    }))
    eb.on(Events.ASR_DEGRADED, lambda f, t, r: _event_queue.put({
        "event": "asr_degraded", "from": f, "to": t, "reason": r,
    }))
    eb.on(Events.AI_RESULT, lambda t, pid=None, mn=None: _event_queue.put({
        "event": "ai_result", "text": t, "provider": pid, "model": mn,
    }))
    eb.on(Events.PIPELINE_DONE, lambda t: _event_queue.put({"event": "pipeline_done", "text": t}))
    eb.on(Events.PIPELINE_ERROR, lambda m: _event_queue.put({"event": "error", "message": str(m)}))
    eb.on(Events.RECORDING_ERROR, lambda m: _event_queue.put({"event": "error", "message": str(m)}))
    eb.on(Events.ASR_ERROR, lambda m: _event_queue.put({"event": "error", "message": str(m)}))
    eb.on(Events.INJECTION_DONE, lambda result: _event_queue.put({
        "event": "injection_done", "ok": result.ok,
        "state": result.state, "verified": result.verified,
        "method": result.method, "reason": result.reason or "",
        "clipboard_restored": result.clipboard_restored,
    }))
    eb.on(Events.NO_EDITABLE_TARGET, lambda t: _event_queue.put({"event": "no_editable_target", "text": t}))
    eb.on(Events.RESULT_CARD_SHOW, lambda t, lt, s="", m="": _event_queue.put({
        "event": "result_card_show", "text": t, "last_transcription": lt,
        "state": s, "message": m,
    }))
    eb.on(Events.RESULT_CARD_CLOSE, lambda: _event_queue.put({"event": "result_card_close"}))
    eb.on(Events.LIGHT_HINT, lambda m: _event_queue.put({"event": "light_hint", "message": str(m)}))
    eb.on(Events.SILENT_LEARNED, lambda c: _event_queue.put({"event": "silent_learned", "count": c}))
    eb.on(Events.AI_ERROR, lambda m: _event_queue.put({"event": "ai_error", "message": str(m)}))
    eb.on(Events.AI_DEGRADED, lambda m: _event_queue.put({"event": "ai_degraded", "message": str(m)}))
    eb.on(Events.UIPI_WARNING, lambda: _event_queue.put({"event": "uipi_warning"}))


# ── REST API ─────────────────────────────────────

@app.get("/api/config")
def get_config():
    return _mask_keys(config.get_all())

@app.post("/api/config")
def set_config(data: dict):
    # Strip masked keys — don't overwrite real keys with '…' placeholders
    data = _clean_masked_keys(data)
    # Defense: discard any stray masked/placeholder values before merge
    _reject_masked_values(data)
    # Also strip read-only fields (key_set / key_masked) that frontend may echo
    _strip_readonly_fields(data)
    # Sync keys between top-level and ai_providers
    _sync_provider_keys(data)
    # Preserve existing nested fields that frontend doesn't manage (app_id, cluster, etc.)
    _preserve_nested(data)
    # Merge instead of replace — preserves sub-fields frontend didn't send
    existing = config.get_all()
    for k, v in data.items():
        if k in existing and isinstance(existing[k], dict) and isinstance(v, dict):
            config._deep_merge(existing[k], v)
        else:
            config.set(k, v)
    # Save to disk (keys persist as plaintext in local config file;
    # masked in GET /api/config via _mask_keys)
    config.save()
    # Force rebuild without mtime check
    orchestrator._audio.set_gain(config.get("audio", "gain_multiplier", 2.0))
    orchestrator._asr = AsrCascade(config.get_all())
    orchestrator._corrector.reload_config()
    orchestrator._hotwords.set_asr_engine(orchestrator._asr)
    orchestrator._hotwords._sync_to_asr()
    return {"ok": True}

@app.get("/api/history")
def get_history(search: str = "", limit: int = 100, offset: int = 0):
    return usecases.get_history(search, limit, offset)

@app.put("/api/history/{entry_id}")
def update_history(entry_id: str, data: dict):
    usecases.update_history_text(entry_id, data.get("text", ""))
    return {"ok": True}

@app.delete("/api/history/{entry_id}")
def delete_history(entry_id: str):
    usecases.delete_history(entry_id)
    return {"ok": True}

@app.get("/api/dictionary")
def get_dictionary():
    hotwords.ensure_core_hotwords()
    return usecases.get_dictionary()

@app.post("/api/dictionary")
def add_word(data: dict):
    ok = usecases.add_dictionary_word(data.get("word", ""), data.get("pinyin", ""))
    return {"ok": ok}

@app.delete("/api/dictionary/{word}")
def remove_word(word: str):
    usecases.remove_dictionary_word(word)
    return {"ok": True}


@app.post("/api/hotwords/sync-aliyun-vocabulary")
def sync_aliyun_vocabulary():
    """Create/update DashScope hotword vocabulary and activate vocabulary_id."""
    hotwords.ensure_core_hotwords()
    return hotwords.sync_aliyun_vocabulary(config)

@app.get("/api/stats/apps")
def app_stats():
    """Return top apps by voice input usage count from history."""
    return db.get_app_stats()

@app.get("/api/available-models")
def available_models():
    """Return available model options for all ASR and AI providers.
    Frontend uses this to populate <select> dropdowns dynamically."""
    return {
        "asr": {
            "aliyun": [
                {"value": "fun-asr-realtime", "label": "Fun-ASR-Realtime — 通义语音（推荐）"},
                {"value": "paraformer-realtime-v2", "label": "Paraformer-Realtime-V2"},
            ],
            "volcengine": [
                {"value": "doubao-asr-streaming", "label": "Doubao-ASR-Streaming — 流式"},
                {"value": "doubao-asr-offline", "label": "Doubao-ASR-Offline — 离线"},
            ],
        },
        "ai": {
            "deepseek": [
                {"value": "deepseek-v4-flash", "label": "DeepSeek-V4-Flash — 高性价比（推荐）"},
                {"value": "deepseek-v4-pro", "label": "DeepSeek-V4-Pro — 高质量"},
            ],
            "aliyun": [
                {"value": "qwen-flash", "label": "Qwen-Flash — 高性价比（推荐）"},
                {"value": "qwen-plus", "label": "Qwen-Plus — 高质量"},
            ],
            "volcengine": [
                {"value": "doubao-seed-2-0-mini-260428", "label": "Doubao-Seed-2.0-Mini — 极速低延迟"},
                {"value": "doubao-seed-2-0-lite-260428", "label": "Doubao-Seed-2.0-Lite — 轻量"},
            ],
        },
    }


@app.get("/api/active-models")
def active_models():
    """Return currently active ASR engine and AI correction model info.
    Used by settings summary (E) — shows actual engine, not configured preference.
    """
    from infrastructure.ai_providers import PROVIDER_DISPLAY, ASR_DISPLAY
    from infrastructure.corrector import get_active_correction_info

    # ASR: actual active engine from cascade
    asr_info = {"engine_id": None, "display_name": None, "model": None, "degraded": False}
    cascade = orchestrator._asr
    asr_order = orchestrator._config.get("asr_fallback", {}).get("order", ["aliyun", "volcengine", "onnx"])
    configured_primary = asr_order[0] if asr_order else None
    for eng_id in asr_order:
        eng = cascade._get_engine(eng_id)
        if eng is not None:
            disp = ASR_DISPLAY.get(eng_id, (eng_id, eng_id))
            asr_info["engine_id"] = eng_id
            asr_info["display_name"] = disp[0]
            asr_info["model"] = disp[1]
            asr_info["degraded"] = (eng_id != configured_primary) if configured_primary else False
            break

    # AI: active correction provider
    corr_info = get_active_correction_info()

    return {
        "asr": asr_info,
        "correction": corr_info,
    }


@app.get("/api/rules")
def get_rules(active_only: bool = False):
    return usecases.get_rules(active_only)

@app.get("/api/microphones")
def detect_microphones():
    return usecases.detect_microphones()

@app.get("/api/engine-status")
def engine_status():
    return _get_engine_status()

@app.post("/api/test-provider/{provider_id}")
def test_provider(provider_id: str):
    return _test_provider_connection(provider_id)

_state = {"last_rms": 0.0}

@app.get("/api/is-recording")
def is_recording():
    state = None
    try:
        state = orchestrator._pipeline.state.value if orchestrator._pipeline else "idle"
    except Exception:
        state = "unknown"
    return {"recording": orchestrator.is_recording(), "state": state, "rms": _state["last_rms"]}

@app.get("/api/rms-level")
def rms_level():
    return {"level": _state["last_rms"]}

@app.post("/api/start-recording")
def start_recording():
    ok = orchestrator.start_recording()
    return {"ok": bool(ok)}

@app.post("/api/stop-recording")
def stop_recording():
    ok = orchestrator.stop_recording()
    return {"ok": bool(ok)}

# ── Result card endpoints ──────────────────────────────
# Renderer must NOT supply arbitrary text — clipboard is written by Electron
# main process via the trusted preload IPC. This endpoint exists only so the
# main process can notify the backend that a user-confirmed copy happened
# (for history/observability). The old /api/result-card/copy that accepted
# arbitrary `{text}` is retained for backwards-compatibility but is
# defanged — it no longer writes the clipboard.

@app.post("/api/result-card/copy-confirmed")
def result_card_copy_confirmed():
    """Notify backend that Electron main wrote the pending text to clipboard.
    Backend does NOT write the clipboard itself; this is purely observational."""
    try:
        from application.eventbus import Events as _E
        orchestrator.eventbus.emit(_E.RESULT_CARD_COPY, "")
    except Exception:
        pass
    _event_queue.put({"event": "result_card_copy_done"})
    return {"ok": True}


@app.post("/api/result-card/copy")
def result_card_copy(data: dict | None = None):
    """DEPRECATED — kept for backwards compatibility only.
    Accepts a `{text}` body for legacy callers; the renderer must use the
    trusted IPC path via Electron main instead. To prevent any local-origin
    page from silently overwriting the user's clipboard, this endpoint
    refuses to write unless the request comes with a sentinel marker.
    """
    # Refuse to write clipboard from this endpoint — the trusted path is
    # Electron main + clipboard.writeText. Return 410 Gone semantics.
    return {"ok": False, "error": "deprecated_use_electron_ipc"}

@app.post("/api/result-card/close")
def result_card_close():
    """Close the result card."""
    try:
        from application.eventbus import Events as _E
        orchestrator.eventbus.emit(_E.RESULT_CARD_CLOSE)
    except Exception:
        pass
    _event_queue.put({"event": "result_card_close"})
    return {"ok": True}

@app.get("/api/version")
def version():
    from infrastructure.version import VERSION
    return {"version": VERSION}


@app.get("/api/runtime-info")
def runtime_info():
    """Return source/runtime identity so Electron cannot silently use stale backends."""
    from infrastructure.paths import PROJECT_ROOT, config_path, database_path, log_path
    from infrastructure.ai_providers import build_providers, get_active_provider
    from domain.hotwords import canonical_hotwords
    cfg = config.get_all()
    providers = build_providers(cfg)
    active_ai = get_active_provider(providers)
    asr = orchestrator._asr
    asr_available = []
    if getattr(asr, "_aliyun", None) is not None:
        asr_available.append("aliyun")
    if getattr(asr, "_volcengine", None) is not None:
        asr_available.append("volcengine")
    if os.path.exists(os.path.join(getattr(asr, "_onnx_dir", ""), "model.onnx")):
        asr_available.append("onnx")
    return {
        "pid": os.getpid(),
        "executable": sys.executable,
        "project_root": PROJECT_ROOT,
        "cwd": os.getcwd(),
        "config_path": config_path(),
        "database_path": database_path(),
        "log_path": log_path(),
        "organize_level": cfg.get("organize_level", "light"),
        "asr": {
            "order": cfg.get("asr_fallback", {}).get("order", []),
            "available": asr_available,
            "aliyun_context": cfg.get("aliyun", {}).get("context", ""),
            "layer1_context": hotwords.get_layer1_context(),
            "vocabulary_id": cfg.get("aliyun", {}).get("vocabulary_id", ""),
            "vocabulary_prefix": cfg.get("aliyun", {}).get("vocabulary_prefix", "sayithot"),
            "vocabulary_target_model": cfg.get("aliyun", {}).get("vocabulary_target_model", ""),
            "volcengine": {
                "endpoint": cfg.get("volcengine", {}).get("asr", {}).get("endpoint", ""),
                "resource_id": cfg.get("volcengine", {}).get("asr", {}).get("resource_id", ""),
                "hotwords_enabled": "volcengine" in asr_available,
                "hotwords_mode": "inline_corpus_context",
            },
            "dictionary_word_count": hotwords.count(),
            "dictionary_words": hotwords.get_words(),
            "canonical_words": canonical_hotwords(hotwords.get_words()),
        },
        "ai": {
            "providers": [
                {
                    "id": p.id,
                    "model": p.model,
                    "enabled": p.enabled,
                    "available": p.available,
                    "endpoint": p.endpoint,
                }
                for p in providers
            ],
            "active": {
                "id": active_ai.id,
                "model": active_ai.model,
                "endpoint": active_ai.endpoint,
            } if active_ai else None,
        },
    }


# ── Debug endpoints (diagnostic fixtures) ───────

@app.get("/api/diagnostics/hotkey")
def hotkey_diagnostics():
    """Return loaded DLL identity + recent toggle dispatch records.

    The records contain only sequence numbers, monotonic timestamps and
    thread ids — no user text. Lets the user verify which DLL build is
    actually loaded and that RAlt presses propagate through the chain.
    """
    helper = getattr(orchestrator, "_keyboard_helper", None)
    if helper is None or not helper.is_available:
        return {"available": False}
    try:
        diag = helper.diagnostics()
        events = helper.recent_events(limit=16)
        return {"available": True, "diagnostics": diag, "recent_events": events}
    except Exception as e:
        return {"available": True, "error": str(e)}


@app.post("/api/debug/inject")
def debug_inject(data: dict):
    """Inject text directly, bypassing audio/ASR/AI. For injection path diagnosis.

    Optional flag:
      paste_only: true → call paste() directly, skip _release_modifiers + _inject_uia
    """
    text = data.get("text", "")
    if not text:
        return {"ok": False, "error": "empty text"}
    orchestrator.eventbus.emit("debug_inject_start", {"text": text, "len": len(text)})

    if data.get("paste_only"):
        ok = orchestrator._injector.paste(text)
        return {
            "ok": ok, "route": "paste_only",
            "text_len": len(text),
            "target_proc": orchestrator._injector.last_target_proc,
            "target_class": orchestrator._injector.last_target_class,
        }

    ok = orchestrator._injector.inject(text)
    return {
        "ok": ok,
        "text_len": len(text),
        "target_proc": orchestrator._injector.last_target_proc,
        "target_class": orchestrator._injector.last_target_class,
        "target_title": orchestrator._injector.last_target_title,
    }


@app.post("/api/debug/release-only")
def debug_release_only():
    """Call _release_modifiers() only — isolate modifier keyup side effects."""
    orchestrator._injector._release_modifiers()
    return {"ok": True, "note": "release_modifiers sent, check Notepad for stray chars"}


@app.post("/api/debug/pipeline-text")
def debug_pipeline_text(data: dict):
    """Run text through corrector → injector, no audio/ASR.

    Pass dry_run: true to skip injection — corrector-only diagnostic mode
    (the corrector version of wav-replay).
    """
    text = data.get("text", "")
    if not text:
        return {"ok": False, "error": "empty text"}
    dry_run = data.get("dry_run", False)
    hotwords.ensure_core_hotwords()

    raw_text = text
    refined_text = hotwords.apply_layer2_correction(raw_text)
    try:
        from domain.correction import apply_rules
        rules = db.get_rules(active_only=True)
        if rules:
            refined_text = apply_rules(refined_text, rules)
    except Exception as e:
        logger.warning("debug_pipeline_text: local rules failed: %s", e)

    final_text = refined_text
    ai_pid = None
    ai_model = None
    ai_error = None
    organize_level = config.get("organize_level", "light")
    if config.get("enable_correction", True) and organize_level != "none":
        try:
            corrected, ai_pid, ai_model = orchestrator._corrector.process(
                refined_text, hotwords_mgr=hotwords)
            if corrected and corrected.strip():
                final_text = corrected
            if ai_pid is None:
                ai_error = "No AI provider available for correction"
        except Exception as e:
            ai_error = str(e)
            logger.warning("debug_pipeline_text: AI correction failed: %s", e)

    cfg = config.get_all()
    from domain.hotwords import canonical_hotwords
    response = {
        "ok": True,
        "dry_run": dry_run,
        "raw_text": raw_text,
        "refined_text": refined_text,
        "final_text": final_text,
        "original": raw_text,
        "corrected": final_text,
        "correction_provider": ai_pid,
        "correction_model": ai_model,
        "ai_error": ai_error,
        "organize_level": organize_level,
        "asr": {
            "engine": cfg.get("asr_engine", "aliyun"),
            "order": cfg.get("asr_fallback", {}).get("order", []),
            "context": cfg.get("aliyun", {}).get("context", ""),
            "layer1_context": hotwords.get_layer1_context(),
            "vocabulary_id": cfg.get("aliyun", {}).get("vocabulary_id", ""),
            "vocabulary_prefix": cfg.get("aliyun", {}).get("vocabulary_prefix", "sayithot"),
            "vocabulary_target_model": cfg.get("aliyun", {}).get("vocabulary_target_model", ""),
            "volcengine": {
                "endpoint": cfg.get("volcengine", {}).get("asr", {}).get("endpoint", ""),
                "resource_id": cfg.get("volcengine", {}).get("asr", {}).get("resource_id", ""),
                "hotwords_mode": "inline_corpus_context",
            },
        },
        "hotwords": {
            "word_count": hotwords.count(),
            "words": hotwords.get_words(),
            "canonical_words": canonical_hotwords(hotwords.get_words()),
        },
    }
    if dry_run:
        return response
    ok = orchestrator._injector.inject(final_text)
    response.update({
        "ok": ok,
        "target_proc": orchestrator._injector.last_target_proc,
        "target_class": orchestrator._injector.last_target_class,
        "target_title": orchestrator._injector.last_target_title,
    })
    return response


@app.get("/api/debug/wav-check")
def debug_wav_check():
    """Return info on last recorded WAV (desktop sayit_last.wav)."""
    import os as _os
    path = _os.path.expanduser("~/Desktop/sayit_last.wav")
    if not _os.path.exists(path):
        return {"ok": False, "error": "no WAV found", "path": path}
    import wave as _wave
    try:
        with _wave.open(path, "rb") as w:
            return {
                "ok": True,
                "path": path,
                "framerate": w.getframerate(),
                "nframes": w.getnframes(),
                "channels": w.getnchannels(),
                "sampwidth": w.getsampwidth(),
                "duration_s": round(w.getnframes() / max(w.getframerate(), 1), 3),
                "size_bytes": _os.path.getsize(path),
            }
    except Exception as e:
        return {"ok": False, "error": str(e), "path": path}


@app.post("/api/debug/wav-replay")
async def debug_wav_replay(
    file: UploadFile = File(...),
    engine: str = "cascade",
    hotwords: bool = False,
    resample: bool = False,
):
    """Replay a WAV file through the ASR chain. Feeds raw PCM as-is (no resample by default).

    Query params:
      engine: "cascade" | "aliyun" | "volcengine" | "onnx"
      hotwords: true → inject dictionary hotwords into DashScopeASR call
      resample: true → resample to 16000 if header_rate differs (for A/B comparison only)

    Sampling rate note: pyaudio opens at RATE=16000 and resamples internally from
    the device's native 44100. The PCM data IS 16000 — the WAV header is correct.
    Use (b) recording duration check + (c) ear test to confirm, not a circular formula.
    """
    import wave as _wave
    import numpy as np
    import time as _time

    # ── Read uploaded WAV ──────────────────────────
    pcm_data = await file.read()
    fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="wav_replay_")
    os.close(fd)
    with open(tmp_path, "wb") as f:
        f.write(pcm_data)

    try:
        with _wave.open(tmp_path, "rb") as w:
            header_rate = w.getframerate()
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            nframes = w.getnframes()
            pcm = w.readframes(nframes)
    except Exception as e:
        os.remove(tmp_path)
        return {"ok": False, "error": f"Invalid WAV: {e}"}

    duration_s = nframes / max(header_rate, 1) if header_rate else 0
    pcm_bytes = len(pcm)
    expected_pcm = nframes * channels * sampwidth

    # ── Validate format ────────────────────────────
    if channels != 1:
        os.remove(tmp_path)
        return {"ok": False, "error": f"Expected mono WAV, got {channels} channels"}
    if sampwidth != 2:
        os.remove(tmp_path)
        return {"ok": False, "error": f"Expected 16-bit WAV, got {sampwidth * 8}-bit"}

    logger.info(
        "[WAV-REPLAY] header_rate=%d channels=%d sampwidth=%d nframes=%d "
        "pcm_bytes=%d duration_s=%.3f resample=%s hotwords=%s engine=%s",
        header_rate, channels, sampwidth, nframes,
        pcm_bytes, duration_s, resample, hotwords, engine)

    # ── Optional resample (default OFF) ────────────
    if resample and header_rate != 16000:
        t0 = _time.perf_counter()
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        # Linear interpolation to 16000
        old_len = len(arr)
        new_len = int(old_len * 16000 / header_rate)
        old_idx = np.linspace(0, old_len - 1, old_len)
        new_idx = np.linspace(0, old_len - 1, new_len)
        arr_resampled = np.interp(new_idx, old_idx, arr).astype(np.int16)
        pcm = arr_resampled.tobytes()
        resample_ms = (_time.perf_counter() - t0) * 1000
        logger.info("[WAV-REPLAY] resampled %d→%d Hz, %d→%d samples, %.1fms",
                    header_rate, 16000, old_len, new_len, resample_ms)
        header_rate = 16000  # Update for hotword path
        os.remove(tmp_path)
        fd2, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="wav_replay_resampled_")
        os.close(fd2)
        with _wave.open(tmp_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm)

    # ── Get environment info ───────────────────────
    available_engines = []
    if orchestrator._asr._aliyun:
        available_engines.append("aliyun")
    if orchestrator._asr._volcengine:
        available_engines.append("volcengine")
    if orchestrator._asr._onnx:
        available_engines.append("onnx")
    dict_words = usecases.get_dictionary()  # returns list[str]
    dict_word_list = list(dict_words) if isinstance(dict_words, list) else []

    # ── Run ASR ────────────────────────────────────
    t0 = _time.perf_counter()
    asr_text = ""
    asr_engine_used = engine
    layer1_context_built = ""

    logger.info("[WAV-REPLAY] routing: hotwords=%s engine=%s aliyun_ok=%s cascade_ok=%s",
                hotwords, engine,
                orchestrator._asr._aliyun is not None,
                engine == "cascade")

    if hotwords and engine in ("aliyun", "cascade") and orchestrator._asr._aliyun:
        # ── hotwords=true: bypass _sync() dead code, directly construct Recognition with context + phrase_id ──
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback
        from infrastructure.asr import _pcm_to_wav
        cfg = orchestrator._config.get_all()
        a = cfg.get("aliyun", {})
        # Set API key (DashScopeASR.__init__ does this; we must do it manually here)
        dashscope.api_key = a.get("api_key", "")
        # Build context from dictionary words
        hotword_ctx = ", ".join(dict_word_list) if dict_word_list else ""
        layer1_context_built = hotword_ctx
        vocab_id = a.get("vocabulary_id", "")
        logger.info("[WAV-REPLAY] hotwords=true constructing Recognition(context=%r, phrase_id=%r) dict_words=%d",
                    hotword_ctx, vocab_id or None, len(dict_word_list))
        # Write PCM to temp WAV for Recognition(file=...) API
        wav_path = _pcm_to_wav(pcm, "wav_replay_hotwords")
        try:
            rec = Recognition(
                model=a.get("asr_model", "fun-asr-realtime"),
                callback=RecognitionCallback(),
                format="wav",
                sample_rate=16000,
                context=hotword_ctx)
            result = rec.call(file=wav_path, phrase_id=vocab_id or None)
            # ── Check for API error ──
            code = result.get("code", "")
            if code:
                logger.error("[WAV-REPLAY] hotwords Recognition error: %r", dict(result))
                asr_text = f"[hotwords API error: code={code} message={result.get('message', '')}]"
            else:
                sentence = result.get_sentence()
                if isinstance(sentence, list):
                    asr_text = "".join(s.get("text", "") for s in sentence).strip()
                elif isinstance(sentence, dict):
                    asr_text = sentence.get("text", "").strip()
                else:
                    asr_text = str(sentence or "").strip()
            asr_engine_used = "aliyun+hotwords"
        except Exception as e:
            logger.error("[WAV-REPLAY] hotwords call failed: %s", e)
            asr_text = f"[hotwords error: {e}]"
        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass
    elif engine == "cascade":
        try:
            asr_text, asr_engine_used = orchestrator._asr.transcribe(pcm)
        except Exception as e:
            asr_text = f"[cascade error: {e}]"
            asr_engine_used = "cascade"
    else:
        eng = orchestrator._asr._get_engine(engine)
        if eng is None:
            os.remove(tmp_path)
            return {"ok": False, "error": f"Engine '{engine}' not available. Available: {available_engines}"}
        try:
            asr_text = eng.transcribe(pcm)
            asr_engine_used = engine
        except Exception as e:
            asr_text = f"[{engine} error: {e}]"

    latency_ms = (_time.perf_counter() - t0) * 1000

    # ── Cleanup ────────────────────────────────────
    try:
        os.remove(tmp_path)
    except Exception:
        pass

    return {
        "ok": True,
        "wav_info": {
            "header_rate": header_rate,
            "channels": channels,
            "sampwidth": sampwidth,
            "nframes": nframes,
            "pcm_bytes": pcm_bytes,
            "duration_s": round(duration_s, 3),
            "rate_note": (
                "pyaudio opens at RATE=16000 and resamples internally from device native rate. "
                "PCM data IS 16000 — WAV header is correct. "
                "Verify with: record ~5s known speech → check duration_s → listen to audio."
            ),
        },
        "asr_result": {
            "engine": asr_engine_used,
            "raw_text": asr_text,
            "text_len": len(asr_text),
            "latency_ms": round(latency_ms, 1),
        },
        "environment": {
            "available_engines": available_engines,
            "dictionary_word_count": len(dict_word_list),
            "dictionary_words": dict_word_list,
            "layer1_context_built": layer1_context_built,
        },
    }


# ── Hotkey control ───────────────────────────────

@app.get("/api/config-value")
def get_config_value(key: str = ""):
    """Get a single config value. e.g. /api/config-value?key=hotkey → "RAlt" """
    if not key:
        return {"value": None}
    return {"value": config.get(key, None)}


@app.post("/api/hotkey/pause")
def pause_hotkey():
    """Hotkey pause — no-op (hook is in Electron addon, not Python)."""
    logger.debug("[server] hotkey/pause ignored — hook lives in Electron addon")
    return {"ok": True}


@app.post("/api/hotkey/resume")
def resume_hotkey():
    """Hotkey resume — no-op (hook is in Electron addon, not Python)."""
    logger.debug("[server] hotkey/resume ignored — hook lives in Electron addon")
    return {"ok": True}


@app.post("/api/hotkey/set")
def set_hotkey(data: dict):
    """Hotkey change — no-op (hook is in Electron addon, recompile to change)."""
    logger.debug("[server] hotkey/set ignored — hook lives in Electron addon")
    return {"ok": True}


# ── WebSocket ────────────────────────────────────

@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                cmd = msg.get("command", "")
                if cmd == "toggle_recording":
                    orchestrator.toggle_recording()
                elif cmd == "start_recording":
                    orchestrator.start_recording()
                elif cmd == "stop_recording":
                    orchestrator.stop_recording()
                else:
                    logger.debug("[ws] unknown command: %s", cmd)
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    finally:
        ws_clients.remove(ws)


# ── Helpers ──────────────────────────────────────

# Fields that contain API keys/tokens → must be masked in GET /api/config.
# Each entry is a tuple path into the config dict (last element = key name).
_MASKED_KEY_PATHS = [
    ("aliyun", "api_key"),
    ("volcengine", "asr", "api_key"),
    ("volcengine", "asr", "access_token"),
    ("volcengine", "ai", "api_key"),
    ("deepseek", "api_key"),
]


def _mask_key(value: str) -> str:
    """Unified: first 6 chars + … + last 4 chars. Uses U+2026 (single char)."""
    if not value or len(value) <= 13 or "…" in value:
        return value
    return value[:6] + "…" + value[-4:]


def _mask_keys(cfg: dict) -> dict:
    """Mask API keys AND add _set/_masked boolean siblings for frontend rendering."""
    import copy
    s = copy.deepcopy(cfg)

    def _apply_mask(parent: dict, key: str):
        original = parent.get(key, "")
        key_set = bool(original and original.strip())
        masked_val = _mask_key(original) if key_set else original
        key_masked = key_set and masked_val != original
        parent[key] = masked_val
        parent[key + "_set"] = key_set
        parent[key + "_masked"] = key_masked

    try:
        # Fixed paths
        for path in _MASKED_KEY_PATHS:
            node = s
            for seg in path[:-1]:
                node = node.get(seg, {})
                if not isinstance(node, dict):
                    node = {}
                    break
            if isinstance(node, dict):
                _apply_mask(node, path[-1])

        # ai_providers list — each entry has api_key
        for p in s.get("ai_providers", []):
            if isinstance(p, dict):
                _apply_mask(p, "api_key")
    except Exception:
        pass
    return s

def _clean_masked_keys(data: dict) -> dict:
    """Replace masked keys (containing '…') with real keys from existing config."""
    import copy
    cleaned = copy.deepcopy(data)
    existing = config.get_all() if hasattr(config, 'get_all') else {}
    def _restore_masked(d, existing_d, path=""):
        if not isinstance(d, dict) or not isinstance(existing_d, dict):
            return
        for k, v in list(d.items()):
            key_path = f"{path}.{k}" if path else k
            if isinstance(v, str) and "…" in v and ("key" in k.lower() or "token" in k.lower()):
                # If existing config has a real key, restore it; otherwise just skip (don't overwrite)
                old_val = existing_d.get(k, "")
                if old_val and "…" not in str(old_val):
                    d[k] = old_val
                else:
                    d.pop(k)  # Skip this field entirely, keep old value
            elif isinstance(v, dict) and isinstance(existing_d.get(k), dict):
                _restore_masked(v, existing_d[k], key_path)
            elif isinstance(v, list):
                ex_list = existing_d.get(k, []) if isinstance(existing_d.get(k), list) else []
                for i, item in enumerate(v):
                    if isinstance(item, dict) and i < len(ex_list) and isinstance(ex_list[i], dict):
                        _restore_masked(item, ex_list[i], f"{key_path}[{i}]")
    _restore_masked(cleaned, existing)
    return cleaned


def _reject_masked_values(data: dict):
    """Defense: recursively remove any string value containing '…' or '•••••'.
    Prevents placeholder text from being written as a real key."""
    if not isinstance(data, dict):
        return
    for k, v in list(data.items()):
        if isinstance(v, str) and ("…" in v or "•••••" in v):
            data.pop(k)  # Discard — will be preserved by merge
        elif isinstance(v, dict):
            _reject_masked_values(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _reject_masked_values(item)


def _strip_readonly_fields(data: dict):
    """Remove _set / _masked suffix fields — these are read-only from backend."""
    if not isinstance(data, dict):
        return
    for k in list(data.keys()):
        if isinstance(k, str) and (k.endswith("_set") or k.endswith("_masked")):
            data.pop(k)
        elif isinstance(data[k], dict):
            _strip_readonly_fields(data[k])
        elif isinstance(data[k], list):
            for item in data[k]:
                if isinstance(item, dict):
                    _strip_readonly_fields(item)


def _sync_provider_keys(data: dict):
    """Sync api_key from top-level aliyun/volcengine/deepseek into ai_providers list."""
    if 'ai_providers' not in data:
        return
    for p in data.get('ai_providers', []):
        pid = p.get('id', '')
        if pid == 'aliyun' and 'aliyun' in data:
            p['api_key'] = data['aliyun'].get('api_key', '')
        elif pid == 'volcengine' and 'volcengine' in data:
            p['api_key'] = data['volcengine'].get('ai', {}).get('api_key', '')
        elif pid == 'deepseek' and 'deepseek' in data:
            p['api_key'] = data['deepseek'].get('api_key', '')

def _preserve_nested(data: dict):
    """Restore nested fields frontend doesn't manage from existing config."""
    existing = config.get_all()
    # volcengine.asr → preserve app_id, cluster, endpoint
    if 'volcengine' in data and 'volcengine' in existing:
        v_new = data['volcengine']
        v_old = existing['volcengine']
        if isinstance(v_new, dict) and isinstance(v_old, dict):
            for sub in ['asr', 'ai']:
                if sub in v_new and sub in v_old:
                    if isinstance(v_new[sub], dict) and isinstance(v_old[sub], dict):
                        for k in v_old[sub]:
                            if k not in v_new[sub] or v_new[sub].get(k, '') == '':
                                if v_old[sub].get(k):
                                    v_new[sub][k] = v_old[sub][k]

def _get_engine_status():
    cfg = config.get_all()
    asr_engines = []
    if cfg.get("aliyun", {}).get("api_key", "").strip():
        asr_engines.append("aliyun")
    v = cfg.get("volcengine", {}).get("asr", {})
    if (v.get("api_key", "").strip() or v.get("access_token", "").strip()):
        asr_engines.append("volcengine")
    from infrastructure.paths import PROJECT_ROOT
    onnx_dir = cfg.get("asr_fallback", {}).get("onnx_model_dir", "") or os.path.join(PROJECT_ROOT, "models", "sensevoice")
    if os.path.exists(os.path.join(onnx_dir, "model.onnx")):
        asr_engines.append("onnx")
    from infrastructure.ai_providers import build_providers
    providers = build_providers(cfg)
    ai_engines = [p.id for p in providers if p.available]
    return {"asr": asr_engines, "ai": ai_engines}


def _test_aliyun_asr(cfg: dict) -> dict:
    """Test Aliyun DashScope ASR — verify api_key is configured (no real ASR WS call)."""
    a = cfg.get("aliyun", {})
    key = a.get("api_key", "").strip()
    if not key:
        return {"ok": False, "message": "未配置 API Key"}
    return {"ok": True, "message": "连接成功"}


def _test_provider_connection(provider_id: str):
    from infrastructure.ai_providers import build_providers, test_provider
    try:
        cfg = config.get_all()
        # Aliyun ASR uses api_key presence (same UX convention as Volcengine ASR)
        if provider_id == "aliyun":
            return _test_aliyun_asr(cfg)
        # Volcengine ASR uses a different endpoint & auth than AI chat
        if provider_id == "volcengine":
            return _test_volcengine_asr(cfg)
        if provider_id == "volcengine_ai":
            return _test_volcengine_ai(cfg)
        providers = build_providers(cfg)
        for p in providers:
            if p.id == provider_id:
                ok, msg = test_provider(p)
                return {"ok": ok, "message": msg}
        return {"ok": False, "message": "Provider not configured"}
    except Exception as e:
        logger.warning("test_provider route error: %s", e)
        return {"ok": False, "message": "连接失败"}

def _test_volcengine_asr(cfg: dict) -> dict:
    """Test volcengine ASR v3 — verify api_key is configured."""
    v = cfg.get("volcengine", {}).get("asr", {})
    key = v.get("api_key", "").strip() or v.get("access_token", "").strip()
    if not key:
        return {"ok": False, "message": "未配置 API Key"}
    return {"ok": True, "message": "连接成功"}


def _test_volcengine_ai(cfg: dict) -> dict:
    """Test volcengine AI chat — verify ai.api_key is configured."""
    from infrastructure.ai_providers import PROVIDER_REGISTRY, test_provider
    v = cfg.get("volcengine", {}).get("ai", {})
    key = v.get("api_key", "").strip()
    if not key:
        return {"ok": False, "message": "未配置火山 AI Key（与 ASR Token 不同）"}
    # Build a minimal AIProvider to test the chat endpoint
    entry = PROVIDER_REGISTRY.get("volcengine")
    if not entry:
        return {"ok": False, "message": "Provider not found in registry"}
    from infrastructure.ai_providers import AIProvider
    model = v.get("correction_model") or entry.get("default_model", "doubao-seed-2-0-mini-260428")
    endpoint = v.get("endpoint") or entry.get("endpoint", "")
    if endpoint and not endpoint.endswith("/chat/completions"):
        endpoint = endpoint.rstrip("/") + "/chat/completions"
    p = AIProvider(
        id="volcengine", name="火山引擎", api_key=key,
        model=model, endpoint=endpoint, priority=2, enabled=True,
    )
    ok, msg = test_provider(p)
    return {"ok": ok, "message": msg}


# ── Startup ──────────────────────────────────────

def main():
    # ── File logging: also write to %APPDATA%/Sayit/sayit.log ──
    from infrastructure.paths import log_path as _log_path
    logging.getLogger().addHandler(
        logging.FileHandler(_log_path(), encoding="utf-8"))

    # ── [PORT-BUSY] guard: fail fast before installing hook ──
    # P0: Exit hard (os._exit, not return) to prevent a second process from
    # staying alive with stale WH_KEYBOARD_LL hook, which would conflict with
    # the already-running backend's hook.
    import socket as _socket
    _s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        _s.bind(("127.0.0.1", 17890))
        _s.close()
    except OSError:
        import subprocess as _sp
        try:
            out = _sp.check_output("netstat -ano | findstr :17890", shell=True, text=True)
            logger.error("[PORT-BUSY] 17890 occupied: %s", out.strip())
        except Exception:
            logger.error("[PORT-BUSY] 17890 already in use (could not determine owner)")
        os._exit(1)  # hard exit — no daemon-thread lingering

    orchestrator.start()
    wire_events()

    logger.info("Sayit backend starting on :17890")
    uvicorn.run(app, host="127.0.0.1", port=17890, log_level="info")


if __name__ == "__main__":
    main()

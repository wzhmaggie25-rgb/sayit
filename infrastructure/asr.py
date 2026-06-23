"""ASR engine cascade — DashScope (primary) → VolcEngine (backup) → ONNX SenseVoice (offline)."""
from __future__ import annotations
import array
import concurrent.futures
import json
import logging
import os
import tempfile
import time
import wave
from typing import Optional
from urllib.parse import urlparse

import numpy as np

from infrastructure.config_store import ConfigStore

logger = logging.getLogger(__name__)

# ── PCM stats helper ─────────────────────────────────────────

def _pcm_stats(pcm: bytes) -> str:
    if not pcm:
        return "0B"
    try:
        arr = array.array("h")
        arr.frombytes(pcm[:len(pcm) - len(pcm) % 2])
        n = len(arr)
        if n == 0:
            return f"{len(pcm)}B"
        sq = sum(v * v for v in arr)
        rms = (sq / n) ** 0.5 / 32768.0
        dur = len(pcm) / 32000.0
        return f"{len(pcm)}B ({dur:.1f}s) RMS={rms:.3f}"
    except Exception:
        return f"{len(pcm)}B"


# ── Error classification ──────────────────────────────────────

def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    if any(kw in msg for kw in ("401", "403", "unauthorized", "authentication failed",
                                  "invalid api key", "access denied")):
        return False
    import httpx
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return True


# ── WAV helper ────────────────────────────────────────────────

def _pcm_to_wav(pcm: bytes, prefix: str = "recording", rate: int = 16000,
                ch: int = 1, width: int = 2) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav", prefix=f"{prefix}_")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
        # ── [WAV-CHECK] diagnostic — verify WAV header matches PCM data ──
        logger.info(
            "[WAV-CHECK] prefix=%s header_rate=%d pcm_bytes=%d "
            "computed_dur=%.3fs sampwidth=%d channels=%d",
            prefix, rate, len(pcm),
            len(pcm) / (rate * ch * width) if rate and ch and width else 0,
            width, ch)
        # ── optional: copy WAV to desktop for manual verification ──
        try:
            from infrastructure.config_store import ConfigStore
            dump_enabled = ConfigStore().get("audio", "dump_last_wav", True)
        except Exception:
            dump_enabled = True
        if dump_enabled:
            try:
                import shutil
                desktop = os.path.expanduser("~/Desktop/sayit_last.wav")
                shutil.copy(path, desktop)
                logger.info("[WAV-CHECK] copied to %s", desktop)
            except Exception:
                pass
    return path


# ── DashScope ASR (Alibaba Cloud) ────────────────────────────

class DashScopeASR:
    """Fun-ASR / qwen3-asr-flash synchronous/streaming recognition via DashScope.

    Endpoints are locked to China mainland (Beijing region). DO NOT change to
    dashscope-intl.aliyuncs.com — that doubles billing and Fun-ASR hotwords won't work.
    """

    def __init__(self, api_key: str, model: str = "fun-asr-realtime",
                 context: str = "",
                 base_url: str = "https://dashscope.aliyuncs.com/api/v1",
                 ws_endpoint: str = "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
                 vocabulary_id: str = ""):
        self.api_key = api_key
        self.model = model
        self.context = context
        self.vocabulary_id = vocabulary_id
        import dashscope
        dashscope.api_key = api_key
        dashscope.base_http_api_url = base_url               # 固定中国内地(北京)节点
        dashscope.base_websocket_api_url = ws_endpoint         # 实时 ASR 走 WebSocket，同样固定国内节点

    def set_context(self, context: str):
        self.context = context

    def set_vocabulary_id(self, vocabulary_id: str):
        self.vocabulary_id = vocabulary_id or ""

    def transcribe(self, pcm_bytes: bytes) -> str:
        return self._sync(pcm_bytes)

    def _sync(self, pcm_bytes: bytes) -> str:
        from dashscope.audio.asr import Recognition, RecognitionCallback
        logger.info("[DashScopeASR] PCM: %s", _pcm_stats(pcm_bytes))
        path = _pcm_to_wav(pcm_bytes, "dashscope")
        try:
            # ── diagnostic: what and how we're calling ──
            logger.info("[ASR-CALL-DS] api=Recognition model=%s audio=%s sample_rate=%d format=%s ch=%d bytes=%d",
                        self.model, path, 16000, "wav", 1, len(pcm_bytes))
            logger.info("[ASR-MODEL-CHECK] DashScopeASR model=%r", self.model)

            rec = Recognition(
                model=self.model,
                callback=RecognitionCallback(),
                format="wav",
                sample_rate=16000,
                context=self.context)
            # ── Hotword context and phrase_id now passed to API ──
            logger.info("[ASR-CALL-DS-HOTWORD] context=%r vocabulary_id=%r phrase_id_passed=%s",
                        self.context, self.vocabulary_id,
                        "YES" if self.vocabulary_id else "N/A")

            # ── P0: 15s timeout wrapper — sync call must NOT block indefinitely ──
            # DashScope Recognition.call() is a synchronous HTTP request with no
            # built-in timeout. On long audio (>30s) it can block 60–120s,
            # freezing the pipeline thread and triggering cascade timeouts.
            # We wrap it in a ThreadPoolExecutor with a hard 15s deadline.
            # If it times out, RuntimeError propagates up → AsrCascade falls
            # back to next engine (Volcengine → ONNX local).
            DASHSCOPE_TIMEOUT = 15.0
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                rec.call, file=path, phrase_id=self.vocabulary_id or None)
            try:
                result = future.result(timeout=DASHSCOPE_TIMEOUT)
            except concurrent.futures.TimeoutError:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                raise RuntimeError(
                    f"DashScope ASR timed out after {DASHSCOPE_TIMEOUT}s "
                    f"(PCM={_pcm_stats(pcm_bytes)}) — falling back to next engine")
            else:
                executor.shutdown(wait=False, cancel_futures=True)

            # ── diagnostic: dump full response on error ──
            code = result.get("code", "")
            if code:
                logger.error("[ASR-ERR-DS] %r", dict(result))
                raise RuntimeError(
                    f"DashScope ASR error: code={code} "
                    f"message={result.get('message', '')} "
                    f"request_id={result.get('request_id', '')}")

            # Extract text from sentence results
            sentence = result.get_sentence()
            if isinstance(sentence, list):
                text = "".join(s.get("text", "") for s in sentence).strip()
            elif isinstance(sentence, dict):
                text = sentence.get("text", "").strip()
            else:
                text = str(sentence or "").strip()

            os.remove(path)
            logger.info("[DashScopeASR] text(len=%d): %s", len(text), repr(text[:200]))
            return text
        except Exception:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
            raise


# ── VolcEngine ASR (ByteDance) ────────────────────────────────

class VolcengineASR:
    """Volcano Engine HTTP speech recognition — backup cloud ASR."""

    def __init__(self, app_id: str, access_token: str,
                 endpoint: str = "https://openspeech.bytedance.com/api/v1/asr",
                 cluster: str = ""):
        self.app_id = app_id
        self.access_token = access_token
        self.endpoint = endpoint
        self.cluster = cluster

    def transcribe(self, pcm_bytes: bytes) -> str:
        import httpx
        logger.info("[VolcengineASR] PCM: %s", _pcm_stats(pcm_bytes))
        path = _pcm_to_wav(pcm_bytes, "volcengine")
        try:
            with open(path, "rb") as f:
                files = {"audio": ("audio.wav", f, "audio/wav")}
                headers = {"Authorization": f"Bearer;{self.access_token}"}
                params = {"appid": self.app_id}
                if self.cluster:
                    params["cluster"] = self.cluster
                # ── [VOLC-ASR-EP] diagnostic — log endpoint before request ──
                logger.info(
                    "[VOLC-ASR-EP] engine=volcengine_v1 endpoint=%r scheme=%s host=%s",
                    self.endpoint,
                    urlparse(self.endpoint).scheme if self.endpoint else "N/A",
                    urlparse(self.endpoint).hostname if self.endpoint else "N/A")
                with httpx.Client(timeout=30.0, trust_env=False) as client:
                    resp = client.post(
                        self.endpoint, headers=headers, params=params, files=files)
                    resp.raise_for_status()
                    data = resp.json()
            text = self._extract_text(data)
            if not text:
                raise RuntimeError(f"Volcengine returned empty text. response={data}")
            os.remove(path)
            logger.info("[VolcengineASR] text(len=%d): %s", len(text), repr(text[:200]))
            return text
        except Exception:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
            raise

    def _extract_text(self, data: dict) -> str:
        if "result" in data:
            result = data["result"]
            if isinstance(result, dict):
                return result.get("text", "").strip()
            return str(result).strip()
        if "text" in data:
            return data["text"].strip()
        if "results" in data:
            texts = []
            for r in data["results"]:
                if isinstance(r, dict):
                    texts.append(r.get("text", ""))
                else:
                    texts.append(str(r))
            return "".join(texts).strip()
        return ""


# ── ONNX Local ASR (SenseVoice) ──────────────────────────────

_mel_fb_cache: np.ndarray | None = None


def _mel_filterbank() -> np.ndarray:
    global _mel_fb_cache
    if _mel_fb_cache is not None:
        return _mel_fb_cache
    sample_rate = 16000
    n_fft = 512
    n_mels = 80
    f_min = 20.0
    f_max = 8000.0

    def _hz_to_mel(hz):
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def _mel_to_hz(mel):
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    mel_pts = np.linspace(_hz_to_mel(f_min), _hz_to_mel(f_max), n_mels + 2)
    hz_pts = _mel_to_hz(mel_pts)
    bins = np.floor((n_fft + 1) * hz_pts / sample_rate).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        lo, ctr, hi = bins[i], bins[i + 1], bins[i + 2]
        if ctr > lo:
            fb[i, lo:ctr] = np.linspace(0, 1, ctr - lo, endpoint=False, dtype=np.float32)
        if hi > ctr:
            fb[i, ctr:hi] = np.linspace(1, 0, hi - ctr, endpoint=False, dtype=np.float32)
    _mel_fb_cache = fb
    return fb


class OnnxLocalASR:
    """Offline SenseVoice ONNX ASR — free, no network required."""

    _FS = 16000
    _WIN_LEN = 400
    _HOP_LEN = 160
    _N_FFT = 512
    _N_MELS = 80
    _LFR_M = 7
    _LFR_N = 6
    _BLANK = 0

    _LANG_MAP = {"auto": 0, "zh": 1, "en": 2, "yue": 3, "ja": 4, "ko": 5}
    _TEXTNORM_MAP = {"withitn": 0, "woitn": 1}

    def __init__(self, model_dir: str, language: str = "zh", itn: bool = True):
        self.model_dir = model_dir
        model_path = os.path.join(model_dir, "model.onnx")
        tokens_path = os.path.join(model_dir, "tokens.json")
        self._session = None
        self._torch_model = None
        self._tokens: list[str] | None = None
        self._special_ids: set[int] = set()
        self._lang_id = self._LANG_MAP.get(language, 1)
        self._textnorm_id = self._TEXTNORM_MAP["withitn"] if itn else self._TEXTNORM_MAP["woitn"]
        self._last_ms = 0.0
        self._language = language
        self._itn = itn

        # Try ONNX first
        if os.path.exists(model_path):
            try:
                import onnxruntime as ort
                self._session = ort.InferenceSession(
                    model_path, providers=["CPUExecutionProvider"])
                with open(tokens_path, encoding="utf-8") as f:
                    self._tokens = json.load(f)
                for idx, tok in enumerate(self._tokens):
                    if tok.startswith("<|") and tok.endswith("|>"):
                        self._special_ids.add(idx)
                logger.info("OnnxLocalASR: ONNX model loaded, %d tokens", len(self._tokens))
                return
            except Exception as e:
                logger.warning("OnnxLocalASR: ONNX load failed: %s, trying PyTorch", e)
                self._session = None

        # Fallback to PyTorch/FunASR
        try:
            from funasr import AutoModel
            self._torch_model = AutoModel(
                model="iic/SenseVoiceSmall", device="cpu",
                disable_pbar=True, disable_update=True)
            # Load tokens from model cache
            import glob
            cache_dir = os.path.expanduser("~/.cache/modelscope/hub/models/iic/SenseVoiceSmall")
            if os.path.exists(cache_dir):
                token_files = glob.glob(os.path.join(cache_dir, "**/tokens.json"), recursive=True)
                if token_files:
                    with open(token_files[0], encoding="utf-8") as f:
                        self._tokens = json.load(f)
                    for idx, tok in enumerate(self._tokens):
                        if tok.startswith("<|") and tok.endswith("|>"):
                            self._special_ids.add(idx)
            logger.info("OnnxLocalASR: PyTorch/FunASR model loaded")
        except Exception as e:
            logger.warning("OnnxLocalASR: PyTorch load failed: %s", e)
            self._torch_model = None

    @property
    def available(self) -> bool:
        return (self._session is not None or self._torch_model is not None) and self._tokens is not None

    def transcribe(self, pcm_bytes: bytes) -> str:
        if self._session is not None:
            return self._sync_onnx(pcm_bytes)
        elif self._torch_model is not None:
            return self._sync_torch(pcm_bytes)
        raise RuntimeError("OnnxLocalASR: no model loaded")

    def _sync_torch(self, pcm_bytes: bytes) -> str:
        """Use FunASR PyTorch model directly."""
        import torch
        t0 = time.perf_counter()
        logger.info("[LocalASR-PT] PCM: %s", _pcm_stats(pcm_bytes))
        arr = array.array("h")
        arr.frombytes(pcm_bytes)
        # Keep as 1D [time] — FunASR WavFrontend expects 1D waveform
        samples = torch.tensor(list(arr), dtype=torch.float32) / 32768.0
        if samples.numel() < 1600:
            raise RuntimeError("LocalASR: audio too short (< 0.1s)")
        try:
            res = self._torch_model.generate(
                input=samples, language=self._language,
                textnorm="withitn" if self._itn else "woitn")
            text = res[0]["text"].strip() if res else ""
            # Strip SenseVoice special tokens: <|lang|>, <|emotion|>, <|speech_type|>, <|textnorm|>
            import re
            text = re.sub(r'<\|\w+\|>', '', text).strip()
        except Exception as e:
            raise RuntimeError(f"LocalASR inference failed: {e}")
        self._last_ms = (time.perf_counter() - t0) * 1000.0
        logger.info("[LocalASR-PT] text(len=%d, %.0f ms)", len(text), self._last_ms)
        return text

    def _sync_onnx(self, pcm_bytes: bytes) -> str:
        """Use pre-exported ONNX model (legacy path)."""
        t0 = time.perf_counter()
        logger.info("[OnnxLocalASR] PCM: %s", _pcm_stats(pcm_bytes))
        arr = array.array("h")
        arr.frombytes(pcm_bytes)
        samples = np.array(arr, dtype=np.float32) / 32768.0
        if samples.size == 0:
            raise RuntimeError("OnnxLocalASR: empty PCM input")
        log_mel = self._compute_log_mel(samples)
        feats = self._lfr(log_mel)
        if feats.shape[0] == 0:
            raise RuntimeError("OnnxLocalASR: audio too short for LFR")
        import onnxruntime as ort
        inputs = {
            "speech": feats[np.newaxis, :, :].astype(np.float32),
            "speech_lengths": np.array([feats.shape[0]], dtype=np.int32),
            "language": np.array([self._lang_id], dtype=np.int32),
            "textnorm": np.array([self._textnorm_id], dtype=np.int32),
        }
        logits, out_lens = self._session.run(None, inputs)
        token_ids = self._ctc_greedy(logits[0])
        text = self._ids_to_text(token_ids)
        self._last_ms = (time.perf_counter() - t0) * 1000.0
        logger.info("[OnnxLocalASR] text(len=%d, %.0f ms)", len(text), self._last_ms)
        return text

    def get_elapsed_ms(self) -> float:
        return self._last_ms

    def _compute_log_mel(self, samples: np.ndarray) -> np.ndarray:
        n_frames = max(1, 1 + (len(samples) - self._WIN_LEN) // self._HOP_LEN)
        frames = np.zeros((n_frames, self._WIN_LEN), dtype=np.float32)
        for i in range(n_frames):
            start = i * self._HOP_LEN
            end = min(start + self._WIN_LEN, len(samples))
            frames[i, :end - start] = samples[start:end]
        window = np.hamming(self._WIN_LEN).astype(np.float32)
        frames *= window
        spec = np.abs(np.fft.rfft(frames, n=self._N_FFT, axis=1)).astype(np.float32) ** 2
        mel_spec = np.dot(spec, _mel_filterbank().T)
        return np.log(mel_spec + 1e-10, dtype=np.float32)

    def _lfr(self, log_mel: np.ndarray) -> np.ndarray:
        T = log_mel.shape[0]
        if T < self._LFR_M:
            pad = np.tile(log_mel[-1:], (self._LFR_M - T, 1))
            log_mel = np.concatenate([log_mel, pad], axis=0)
            T = log_mel.shape[0]
        chunks = []
        for i in range(0, T - self._LFR_M + 1, self._LFR_N):
            chunk = log_mel[i:i + self._LFR_M].ravel()
            chunks.append(chunk)
        return np.array(chunks, dtype=np.float32)

    def _ctc_greedy(self, logits: np.ndarray) -> list[int]:
        ids = np.argmax(logits, axis=-1)
        result = []
        prev = self._BLANK
        for tid in ids:
            if tid == self._BLANK:
                prev = self._BLANK
                continue
            if tid != prev:
                result.append(int(tid))
            prev = tid
        return result

    def _ids_to_text(self, token_ids: list[int]) -> str:
        parts = []
        for tid in token_ids:
            if tid in self._special_ids or tid >= len(self._tokens):
                continue
            tok = self._tokens[tid]
            if tok == "<unk>":
                continue
            parts.append(tok)
        text = ""
        for p in parts:
            if p.startswith("▁"):
                text += " " + p[1:]
            else:
                text += p
        return text.strip()


# ── Three-tier cascade orchestrator ──────────────────────────

class AsrCascade:
    """Multi-level ASR orchestrator with fallback chain."""

    def __init__(self, config: dict):
        self._config = config
        fb = config.get("asr_fallback", {})
        self._enabled = fb.get("enable", True)
        self._order = fb.get("order", ["aliyun", "volcengine", "onnx"])
        primary = config.get("asr_engine", "aliyun")

        self._aliyun = None
        self._volcengine = None
        self._onnx = None
        self._onnx_dir = ""
        self._onnx_language = config.get("local", {}).get("language", "zh")
        self._onnx_itn = config.get("local", {}).get("itn", True)

        # DashScope config — used for batch ASR and streaming session context
        a = config.get("aliyun", {})
        self._streaming_context = a.get("context", "")

        # DashScope ASR — only if API key is configured
        if a.get("api_key", "").strip():
            self._aliyun = DashScopeASR(
                a.get("api_key", ""),
                a.get("asr_model", "fun-asr-realtime"),
                context=a.get("context", ""),
                base_url=a.get("endpoint", "https://dashscope.aliyuncs.com/api/v1"),
                ws_endpoint=a.get("ws_endpoint", "wss://dashscope.aliyuncs.com/api-ws/v1/inference"),
                vocabulary_id=a.get("vocabulary_id", ""))
        else:
            logger.warning("AsrCascade: DashScope API key not configured, skipping")

        # VolcEngine v3 — WebSocket API, needs api_key
        v = config.get("volcengine", {}).get("asr", {})
        api_key = v.get("api_key", "").strip() or v.get("access_token", "").strip()
        if api_key:
            from domain.hotwords import canonical_hotwords
            from infrastructure.asr_v3 import VolcengineASR as VolcengineV3
            volc_endpoint = v.get(
                "endpoint",
                "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream")
            self._volcengine = VolcengineV3(
                api_key,
                resource_id=v.get("resource_id", "volc.seedasr.sauc.duration"),
                endpoint=volc_endpoint,
                hotwords=canonical_hotwords(config.get("dictionary_words", [])))
        else:
            logger.warning("AsrCascade: Volcengine credentials not configured, skipping")

        # Local SenseVoice/FunASR is the final fallback. Do not load it at
        # startup; the model can be slow and should not block cloud ASR readiness.
        onnx_dir = fb.get("onnx_model_dir", "")
        if not onnx_dir:
            from infrastructure.paths import PROJECT_ROOT
            onnx_dir = os.path.join(PROJECT_ROOT, "models", "sensevoice")
        self._onnx_dir = onnx_dir

        # Don't auto-add engines — respect configured cascade order

        # Log available engines
        available = []
        if self._aliyun: available.append("aliyun")
        if self._volcengine: available.append("volcengine")
        if os.path.exists(os.path.join(self._onnx_dir, "model.onnx")):
            available.append("onnx(lazy)")
        if available:
            logger.info("AsrCascade: available=%s primary=%s", ",".join(available), primary)
        else:
            logger.error("AsrCascade: NO engines available! Configure API keys or download ONNX model.")

    def create_streaming_session(self, event_callback=None):
        """Create the preferred realtime streaming ASR session, if available."""
        streaming_cfg = self._config.get("asr_streaming", {})
        if streaming_cfg.get("enabled", True) is False:
            return None
        a = self._config.get("aliyun", {})
        if not a.get("api_key", "").strip():
            return None
        try:
            from infrastructure.asr_streaming import DashScopeStreamingASRSession
            return DashScopeStreamingASRSession(
                api_key=a.get("api_key", ""),
                model=a.get("asr_model", "fun-asr-realtime"),
                ws_endpoint=a.get("ws_endpoint", "wss://dashscope.aliyuncs.com/api-ws/v1/inference"),
                vocabulary_id=a.get("vocabulary_id", ""),
                context=a.get("context", "") or getattr(self, "_streaming_context", ""),
                language=self._config.get("local", {}).get("language", "zh"),
                max_sentence_silence=int(streaming_cfg.get("max_sentence_silence", 1300)),
                event_callback=event_callback,
            )
        except Exception as e:
            logger.warning("AsrCascade: streaming session unavailable: %s", e)
            return None

    def transcribe(self, pcm_bytes: bytes) -> tuple[str, str]:
        """Transcribe PCM bytes. Returns (text, engine_name)."""
        errors = []
        for level_name in self._order:
            engine = self._get_engine(level_name)
            if engine is None:
                continue
            try:
                return engine.transcribe(pcm_bytes), level_name
            except Exception as e:
                logger.warning("Level (%s): %s: %s", level_name, type(e).__name__, e)
                errors.append((level_name, f"{type(e).__name__}: {e}"))
                if not self._enabled:
                    raise
                # Don't silently degrade on permanent errors (401/403/auth)
                if not _is_retryable(e):
                    raise
        detail = "; ".join(f"[{n}] {m}" for n, m in errors)
        raise RuntimeError(f"All ASR levels failed: {detail}")

    def set_hotwords_context(self, context: str):
        self._streaming_context = context
        if self._aliyun:
            self._aliyun.set_context(context)
        if self._volcengine and hasattr(self._volcengine, "set_context"):
            self._volcengine.set_context(context)

    def set_hotwords_vocabulary_id(self, vocabulary_id: str):
        if self._aliyun:
            self._aliyun.set_vocabulary_id(vocabulary_id)

    def _get_engine(self, name: str):
        if name == "aliyun":
            return self._aliyun
        elif name == "volcengine":
            return self._volcengine
        elif name == "onnx":
            if self._onnx is None:
                logger.info("AsrCascade: lazy-loading local ASR fallback from %s", self._onnx_dir)
                onnx = OnnxLocalASR(
                    self._onnx_dir,
                    language=self._onnx_language,
                    itn=self._onnx_itn)
                if onnx.available:
                    self._onnx = onnx
                else:
                    logger.warning("AsrCascade: local ASR fallback unavailable at %s", self._onnx_dir)
            return self._onnx
        return None

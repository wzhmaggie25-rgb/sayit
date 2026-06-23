"""Recording pipeline — state machine orchestrating audio → ASR → AI → inject → learn."""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional

from domain.models import RecordingState
from application.eventbus import EventBus, Events

logger = logging.getLogger(__name__)


class RecordingPipeline:
    """State machine that runs the full recording → injection pipeline.

    States: IDLE → CAPTURING → TRANSCRIBING → CORRECTING → DONE/ERROR

    Thread-safe: state transitions are protected by a lock.
    Designed to be used from a background thread.
    """

    def __init__(self, eventbus: EventBus):
        self._eb = eventbus
        self._state = RecordingState.IDLE
        self._lock = threading.Lock()
        self._stop_flag = False

    @property
    def state(self) -> RecordingState:
        with self._lock:
            return self._state

    @state.setter
    def state(self, new_state: RecordingState):
        with self._lock:
            self._state = new_state

    def is_idle(self) -> bool:
        return self.state == RecordingState.IDLE

    def run(self, audio_capture, asr_cascade, corrector,
            hotwords_mgr, injector, silent_monitor, db,
            enable_correction: bool = True,
            injection_target=None):
        """Execute the full pipeline on a background thread.

        Args:
            audio_capture: AudioCapture instance
            asr_cascade: AsrCascade instance
            corrector: Corrector instance
            hotwords_mgr: HotwordsManager instance
            injector: Injector instance
            silent_monitor: SilentMonitor instance
            db: Database instance
            enable_correction: Whether to run AI correction
        """
        self._stop_flag = False

        # ── Phase 1: Recording ───────────────────────────────────
        self.state = RecordingState.CAPTURING
        self._eb.emit(Events.RECORDING_STARTED)
        seconds = 0

        def _on_rms(level: float):
            self._eb.emit(Events.RMS_LEVEL, level)

        streaming_session = None

        def _on_stream_event(kind: str, payload: dict):
            engine = payload.get("engine", "aliyun_streaming")
            if kind == "partial":
                self._eb.emit(Events.ASR_PARTIAL, payload.get("text", ""), engine)
            elif kind == "sentence_end":
                self._eb.emit(Events.ASR_PARTIAL, payload.get("text", ""), engine)
                self._eb.emit(Events.ASR_PROGRESS, "sentence_end", "识别到一句话", engine)
            elif kind == "started":
                self._eb.emit(Events.ASR_PROGRESS, "streaming", "实时识别中", engine)
            elif kind == "complete":
                self._eb.emit(Events.ASR_PROGRESS, "finalizing", "识别收尾中", engine)
            elif kind == "warning":
                self._eb.emit(Events.ASR_PROGRESS, "warning", payload.get("message", ""), engine)
            elif kind == "error":
                self._eb.emit(Events.ASR_PROGRESS, "degrading", payload.get("message", ""), engine)

        try:
            streaming_session = asr_cascade.create_streaming_session(_on_stream_event)
            if streaming_session:
                streaming_session.start()
                audio_capture.set_chunk_callback(streaming_session.enqueue_audio)
        except Exception as e:
            logger.warning("Streaming ASR start failed, will use batch cascade: %s", e)
            streaming_session = None
            self._eb.emit(Events.ASR_DEGRADED, "aliyun_streaming", "cascade", str(e))

        audio_capture.set_level_callback(_on_rms)
        try:
            audio_capture.start()
        except Exception as e:
            if streaming_session:
                streaming_session.abort()
            audio_capture.set_chunk_callback(None)
            self._eb.emit(Events.RECORDING_ERROR, f"音频设备启动失败: {e}")
            self.state = RecordingState.ERROR
            return

        # Tick timer thread
        def _tick():
            nonlocal seconds
            while not self._stop_flag:
                time.sleep(1.0)
                if self._stop_flag:
                    break
                seconds += 1
                self._eb.emit(Events.RECORDING_TICK, seconds)

        tick_thread = threading.Thread(target=_tick, daemon=True)
        tick_thread.start()

        # Wait for stop signal
        while not self._stop_flag:
            time.sleep(0.05)

        tick_thread.join(timeout=1.0)
        pcm = audio_capture.stop()
        audio_capture.set_chunk_callback(None)
        audio_capture.set_level_callback(None)

        # ── Too short check ─────────────────────────────────────
        from infrastructure.audio_capture import MIN_PCM_LENGTH
        if len(pcm) < MIN_PCM_LENGTH:
            if streaming_session:
                streaming_session.abort()
            self._eb.emit(Events.RECORDING_STOPPED)
            self._eb.emit(Events.RECORDING_ERROR, "录音太短")
            self.state = RecordingState.ERROR
            self._eb.emit(Events.PIPELINE_ERROR, "录音太短")   # P0: always send final event so float exits STOPPING
            return

        self._eb.emit(Events.RECORDING_STOPPED)
        logger.info("Pipeline: captured %d PCM bytes in %ds", len(pcm), seconds)

        # ── Phase 2: ASR ─────────────────────────────────────────
        self.state = RecordingState.TRANSCRIBING
        raw_text = ""
        engine = ""
        if streaming_session:
            try:
                self._eb.emit(Events.ASR_PROGRESS, "finalizing", "等待实时识别最终结果", "aliyun_streaming")
                raw_text = streaming_session.finish(timeout=max(45.0, seconds * 0.35))
                engine = "aliyun_streaming"
            except Exception as e:
                logger.warning("Streaming ASR failed, falling back to batch cascade: %s", e)
                self._eb.emit(Events.ASR_DEGRADED, "aliyun_streaming", "cascade", str(e))
                raw_text = ""
                engine = ""
        if not raw_text:
            try:
                self._eb.emit(Events.ASR_PROGRESS, "fallback", "降级识别中", "cascade")
                raw_text, engine = asr_cascade.transcribe(pcm)
            except Exception as e:
                logger.error("ASR failed: %s", e)
                self._eb.emit(Events.ASR_ERROR, str(e))
                self._eb.emit(Events.RECORDING_ERROR, f"ASR失败: {e}")
                self.state = RecordingState.ERROR
                self._eb.emit(Events.PIPELINE_ERROR, f"ASR失败: {e}")
                return
        logger.info("[ASR-RAW] provider=%s text=%r len=%d", engine, raw_text, len(raw_text))
        self._eb.emit(Events.ASR_RESULT, raw_text, engine)
        asr_raw_text = raw_text

        if not raw_text.strip():
            self._eb.emit(Events.RECORDING_ERROR, "未识别到语音内容")
            self.state = RecordingState.ERROR
            self._eb.emit(Events.PIPELINE_ERROR, "未识别到语音内容")
            return

        # ── Layer 2: Local correction (hotwords + learned rules) ───
        # Step 2a: Hotwords fuzzy matching correction
        raw_text = hotwords_mgr.apply_layer2_correction(raw_text)
        # Step 2b: Apply learned correction rules from silent self-learning
        from domain.correction import apply_rules_with_stats
        active_rules = db.get_rules(active_only=True)
        if active_rules:
            before = raw_text
            raw_text, applied_rule_ids = apply_rules_with_stats(raw_text, active_rules)
            if raw_text != before:
                logger.info("Pipeline: applied %d correction rules", len(active_rules))
                db.update_rules_apply_counts(applied_rule_ids)
        locally_refined_text = raw_text

        # ── Phase 3: AI Correction ───────────────────────────────
        self.state = RecordingState.CORRECTING
        self._eb.emit(Events.ASR_PROGRESS, "correcting", "AI 整理中", engine)
        final_text = raw_text
        ai_provider_id = None
        ai_model_name = None
        # 对标闪电说 organize_level="none": 原话模式 → 跳过 AI 纠错
        organize_skip = False
        try:
            from infrastructure.config_store import ConfigStore
            organize_skip = ConfigStore().get("organize_level", "light") == "none"
        except Exception:
            pass
        if enable_correction and not organize_skip:
            try:
                # P1: pass hotwords_mgr for Layer 3 hotword bodyguard
                corrected, ai_provider_id, ai_model_name = corrector.process(
                    raw_text, hotwords_mgr=hotwords_mgr)
                if corrected and corrected.strip():
                    final_text = corrected
                    if ai_provider_id is None:
                        self._eb.emit(Events.AI_ERROR, "No AI provider available for correction")
                else:
                    logger.warning("AI correction returned empty, using raw text")
            except Exception as e:
                logger.warning("AI correction failed: %s, using raw text", e)
                self._eb.emit(Events.AI_ERROR, str(e))
        self._eb.emit(Events.AI_RESULT, final_text, ai_provider_id, ai_model_name)

        # ── Post-processing: remove trailing period (对标闪电说 "去除结尾句号") ──
        try:
            from infrastructure.config_store import ConfigStore
            if ConfigStore().get("remove_trailing_period", False):
                final_text = final_text.rstrip('。').rstrip('.')
        except Exception:
            pass

        # ── Phase 4: Injection ───────────────────────────────────
        self.state = RecordingState.INJECTING
        self._eb.emit(Events.ASR_PROGRESS, "injecting", "注入中", engine)
        try:
            ok = injector.inject(final_text, target=injection_target)
            self._eb.emit(Events.INJECTION_DONE, ok)
        except Exception as e:
            logger.warning("Injection failed: %s", e)
            self._eb.emit(Events.INJECTION_DONE, False)
            ok = False

        # ── Phase 5: Save to history ─────────────────────────────
        history_id = db.add_history(
            raw_text=asr_raw_text,
            refined_text=locally_refined_text,
            normalized_text="",
            final_text=final_text,
            app_name=injector.last_target_proc,
            app_exe=injector.last_target_proc,
            window_title=injector.last_target_title,
            window_class=injector.last_target_class,
            duration=seconds,
            pasted=ok,
            error_msg="" if ok else "injection failed",
            status="completed" if ok else "error",
            debug_info=f"asr_engine={engine};streaming={'1' if engine == 'aliyun_streaming' else '0'}",
        )

        if not ok:
            self._eb.emit(Events.PIPELINE_ERROR, "文本已保存到历史，但未能注入目标输入窗口")
            self.state = RecordingState.ERROR
            return

        # ── Phase 6: Silent monitor ─────────────────────────────
        silent_learning_enabled = True
        try:
            from infrastructure.config_store import ConfigStore
            silent_learning_enabled = ConfigStore().get("silent_learning", True)
        except Exception:
            pass
        if ok and silent_learning_enabled and injector.last_target_hwnd:
            try:
                silent_monitor.start(
                    history_id=str(history_id),
                    original_text=final_text,
                    hwnd=injector.last_target_hwnd,
                    pid=injector.last_target_pid,
                    hotwords_mgr=hotwords_mgr,
                )
            except Exception as e:
                logger.warning("Silent monitor start failed: %s", e)

        self._eb.emit(Events.PIPELINE_DONE, final_text)
        self.state = RecordingState.DONE

    def stop(self):
        """Signal the pipeline to stop recording."""
        self._stop_flag = True

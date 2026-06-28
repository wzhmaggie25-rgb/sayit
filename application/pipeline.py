"""Recording pipeline — state machine orchestrating audio → ASR → AI → inject → learn."""
from __future__ import annotations
import logging
import threading
import time
import uuid
import httpx

from domain.models import RecordingState
from application.eventbus import EventBus, Events
from application.result_card_eligibility import should_show_large_result_card
from infrastructure.injector import InjectionResult
from infrastructure.config_store import ConfigStore

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
        self._session_id = uuid.uuid4().hex[:12]

        # ── COM apartment initialization (for UIA injector) ─────
        com_initialized = False
        try:
            import comtypes
            comtypes.CoInitialize()
            com_initialized = True
        except Exception:
            pass

        try:
            # ── Phase 1: Recording ───────────────────────────────────
            self.state = RecordingState.CAPTURING
            self._eb.emit(Events.RECORDING_STARTED, self._session_id)
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
            # Note: we do NOT clear chunk/level callbacks here because the
            # orchestrator may have detached us (via _on_hotkey_stop) and a
            # new pipeline may have already set fresh callbacks on the same
            # AudioCapture instance. Since audio_capture.stop() already closed
            # the stream and exited the read thread, stale callbacks are
            # harmless — they are never invoked without an active stream.

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
                    # ── Quality gate: if streaming output is too short for the
                    #     recording duration, fall back to batch cascade which has
                    #     hotword context and phrase_id support.
                    text_len = len(raw_text.replace(" ", "").strip())
                    duration = max(seconds, 1)
                    if duration >= 3 and text_len < max(3, int(duration * 1.0)):
                        logger.warning(
                            "Pipeline: streaming output too short (%d chars for %ds), "
                            "falling back to batch cascade", text_len, duration)
                        self._eb.emit(Events.ASR_DEGRADED, "aliyun_streaming", "cascade",
                                      f"streaming output too short ({text_len} chars for {duration}s)")
                        raw_text = ""
                        engine = ""
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

            # ── Phase 3: AI Correction with deadline watchdog ─────────────
            self.state = RecordingState.CORRECTING
            self._eb.emit(Events.ASR_PROGRESS, "correcting", "AI 整理中", engine)
            final_text = raw_text
            ai_provider_id = None
            ai_model_name = None
            # 对标闪电说 organize_level="none": 原话模式 → 跳过 AI 纠错
            organize_skip = False
            try:
                organize_skip = ConfigStore().get("organize_level", "light") == "none"
            except Exception:
                pass
            ai_degraded = False
            if enable_correction and not organize_skip:
                # Read configurable AI deadline (default 25s, range 15-45)
                ai_deadline = 25.0
                try:
                    ai_deadline = float(ConfigStore().get("ai_timeout", 25.0))
                    ai_deadline = max(15.0, min(45.0, ai_deadline))
                except Exception:
                    pass
                # Synchronous AI correction with httpx timeout.
                # No daemon thread needed — httpx raises TimeoutException on expiry.
                # This eliminates the risk of lingering orphan daemon threads.
                try:
                    corrected, provider_id, model_name = corrector.process(
                        raw_text,
                        hotwords_mgr=hotwords_mgr,
                        timeout=ai_deadline)
                    if corrected and corrected.strip():
                        final_text = corrected
                        ai_provider_id = provider_id
                        ai_model_name = model_name
                    else:
                        logger.warning("AI correction returned empty, using raw text")
                        ai_degraded = True
                except httpx.TimeoutException:
                    logger.warning(
                        "[AI] deadline %.0fs exceeded — falling back to locally_refined_text",
                        ai_deadline)
                    ai_degraded = True
                    self._eb.emit(Events.AI_DEGRADED,
                                  f"AI 整理超时（{ai_deadline:.0f}s），已使用识别结果")
                    try:
                        self._eb.emit(Events.ASR_PROGRESS,
                                      "degrading", "AI 整理超时，已使用识别结果", engine)
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning("AI correction failed: %s, using raw text", e)
                    self._eb.emit(Events.AI_ERROR, str(e))
                    ai_degraded = True
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
            inject_result = None
            try:
                inject_result = injector.inject(final_text, target=injection_target)
            except Exception as e:
                logger.warning("Injection threw exception: %s", e)

            # Determine state and emit appropriate events
            if inject_result is None:
                # Exception before InjectionResult was returned
                synthetic = InjectionResult(ok=False, state="injection_failed",
                                             reason="injection_exception")
                self._eb.emit(Events.INJECTION_DONE, synthetic)
                self._eb.emit(Events.PIPELINE_ERROR, "文本已保存到历史，但未能注入目标输入窗口")
                self.state = RecordingState.ERROR
                history_pasted = False
                history_status = "error"
                history_error = "injection_exception"
                ok = False
            elif inject_result.state == "verified_success":
                ok = True
                self._eb.emit(Events.INJECTION_DONE, inject_result)
                history_pasted = True
                history_status = "completed"
                history_error = ""
            elif inject_result.state == "attempted_unverified":
                # Paste/SendInput shortcut dispatched but target readback was
                # not possible. We must NOT retry — risks duplicate text in
                # a target that already accepted the first attempt. Show a
                # lightweight hint on the float bar (NOT a large result card).
                ok = False  # gate SilentMonitor off
                self._eb.emit(Events.INJECTION_DONE, inject_result)
                self._eb.emit(Events.LIGHT_HINT, "文本可能已输入，请检查目标窗口")
                history_pasted = False
                history_status = "completed_unverified"
                history_error = inject_result.reason or "attempted_unverified"
            elif inject_result.state == "no_editable_target":
                ok = True  # Not a failure — user needs result card
                self._eb.emit(Events.INJECTION_DONE, inject_result)
                self._eb.emit(Events.NO_EDITABLE_TARGET, final_text)
                # Gate large result card through production eligibility
                if should_show_large_result_card(
                    state=inject_result.state,
                    injection_dispatched=inject_result.injection_dispatched,
                    inserted_verified=inject_result.verified if hasattr(inject_result, "verified") else False,
                    target_is_sayit_window=False,
                ):
                    self._eb.emit(Events.RESULT_CARD_SHOW, final_text,
                                  locally_refined_text,
                                  inject_result.state,
                                  "未找到可输入的目标窗口")
                history_pasted = False
                history_status = "completed_no_target"
                history_error = ""
            else:
                # injection_failed or recognition_failed
                ok = False
                self._eb.emit(Events.INJECTION_DONE, inject_result)
                # Gate large result card through production eligibility
                if should_show_large_result_card(
                    state=inject_result.state,
                    injection_dispatched=inject_result.injection_dispatched if inject_result else False,
                    inserted_verified=inject_result.verified if (inject_result and hasattr(inject_result, "verified")) else False,
                    target_is_sayit_window=False,
                ):
                    self._eb.emit(Events.RESULT_CARD_SHOW, final_text,
                                  locally_refined_text,
                                  inject_result.state,
                                  "未能将文本注入目标窗口")
                else:
                    self._eb.emit(Events.LIGHT_HINT, "文本未能输入，请查看历史记录")
                if not (inject_result and inject_result.injection_dispatched):
                    self._eb.emit(Events.PIPELINE_ERROR, "文本已保存到历史，但未能注入目标输入窗口")
                history_pasted = False
                history_status = "error"
                history_error = inject_result.reason or "injection_failed"

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
                pasted=history_pasted,
                error_msg=history_error,
                status=history_status,
                debug_info=f"asr_engine={engine};streaming={'1' if engine == 'aliyun_streaming' else '0'}",
            )

            if not ok or inject_result is None:
                if inject_result is not None and inject_result.state in (
                        "no_editable_target", "attempted_unverified"):
                    # no_editable_target / attempted_unverified: save history,
                    # show result card, but skip SilentMonitor.
                    pass
                else:
                    return  # already emitted PIPELINE_ERROR

            # ── Phase 6: Silent monitor ─────────────────────────────
            # Per ROUND5_CODE_REVIEW.md P0-7: only verified_success with a
            # target_verified readback may start the SilentMonitor. Other
            # states (no_editable_target, attempted_unverified, injection_failed,
            # recognition_failed) must NEVER engage learning on an unrelated
            # window or stale hwnd.
            silent_learning_enabled = True
            try:
                from infrastructure.config_store import ConfigStore
                silent_learning_enabled = ConfigStore().get("silent_learning", True)
            except Exception:
                pass
            can_learn = (
                inject_result is not None
                and inject_result.state == "verified_success"
                and inject_result.target_verified
                and injector.last_target_hwnd
            )
            if can_learn and silent_learning_enabled:
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
        finally:
            if com_initialized:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

    def stop(self):
        """Signal the pipeline to stop recording."""
        self._stop_flag = True

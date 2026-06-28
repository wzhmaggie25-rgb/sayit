"""Application orchestrator — wires together all components.

Manages the lifecycle of: hotkey listening, audio capture, ASR, AI correction,
text injection, silent learning, hotwords, and config hot-reload.
"""
from __future__ import annotations
import ctypes
import logging
import threading
import time
from typing import Optional

from application.eventbus import EventBus, Events
from application.pipeline import RecordingPipeline
from domain.models import RecordingState
from infrastructure.audio_capture import AudioCapture
from infrastructure.asr import AsrCascade
from infrastructure.corrector import Corrector
from infrastructure.injector import Injector
from infrastructure.silent_monitor import SilentMonitor
from infrastructure.hotwords_manager import HotwordsManager
from infrastructure.config_store import ConfigStore
from infrastructure.database import Database
from infrastructure.keyboard_helper_dll import KeyboardHelperDll
from infrastructure.ralt_stop_watcher import RAltStopWatcher

logger = logging.getLogger(__name__)


class SayitOrchestrator:
    """Central orchestrator for the Sayit application.

    Responsibilities:
    - Manage hotkey lifecycle
    - Create and run recording pipelines on background threads
    - Coordinate config hot-reload
    - Bridge events between backend and UI (via EventBus)

    Thread safety: _pipeline_lock ensures at most ONE pipeline thread exists.
    When a second hotkey press arrives before the previous pipeline finishes,
    the request is silently rejected — preventing concurrent competition for
    injector._lock (root cause of keyboard hijack/corruption).
    """

    def __init__(self):
        self._eb = EventBus()
        self._config = ConfigStore()
        self._db = Database()

        # Build components from config
        self._audio = AudioCapture(
            gain=self._config.get("audio", "gain_multiplier", 2.0))
        self._asr = AsrCascade(self._config.get_all())
        self._corrector = Corrector()
        self._injector = Injector(
            injection_mode=self._config.get("injection_mode", "auto"))
        self._silent_monitor = SilentMonitor()
        self._hotwords = HotwordsManager()
        self._hotwords.set_asr_engine(self._asr)

        # Wire silent monitor callback to event bus
        self._silent_monitor.set_on_learned(
            lambda count: self._eb.emit(Events.SILENT_LEARNED, count))

        # Sync hotwords to ASR
        self._hotwords._sync_to_asr()

        # Pipeline — guarded by exclusive mutex.
        #
        # The mutex holds for the ENTIRE pipeline lifetime: from
        # capture-start through post-processing, injection, and history
        # save. A second hotkey press while the pipeline is past the
        # capture phase (TRANSCRIBING / CORRECTING / INJECTING) is
        # silently ignored — never spawns a parallel pipeline.
        #
        # _pipeline_active is the canonical busy-flag. It is set under
        # the lock in _on_hotkey_start and cleared ONLY by
        # _pipeline_wrapper.finally — never by _on_hotkey_stop.
        self._pipeline: Optional[RecordingPipeline] = None
        self._pipeline_thread: Optional[threading.Thread] = None
        self._pipeline_lock = threading.Lock()
        self._pipeline_active = False

# Stop request latch: hook and fallback race, first wins.
        # Reset on next recording start. Guards RECORDING_STOPPING ACK
        # to emit exactly once per session.
        # Protected by _stop_latch_lock for atomic try_latch_stop().
        self._stop_request_latched = False
        self._stop_latch_lock = threading.Lock()

        # Focus snapshot: captures the foreground hwnd just before the
        # stop signal, so we can restore focus after injection completes.
        # Reset on next recording start; captured by _execute_stop_request.
        self._pre_stop_focus_hwnd = 0

        # Config hot-reload
        self._reload_running = False
        self._reload_thread: Optional[threading.Thread] = None

        # Keyboard hook: WH_KEYBOARD_LL via ctypes DLL (Typeless architecture)
        self._keyboard_helper = None
        self._stop_watcher: Optional[RAltStopWatcher] = None

    # ── Public API ──────────────────────────────────────────

    @property
    def eventbus(self) -> EventBus:
        return self._eb

    def start(self):
        """Start the orchestrator: config watcher + keyboard hook (Typeless DLL)."""
        self._start_config_watcher()
        self._install_keyboard_hook()
        logger.info("SayitOrchestrator: started")

    def stop(self):
        """Stop the orchestrator gracefully."""
        self._uninstall_keyboard_hook()
        self._stop_config_watcher()
        # Disarm RAlt watcher before stopping pipeline
        try:
            if self._stop_watcher is not None:
                self._stop_watcher.disarm()
        except Exception:
            pass
        with self._pipeline_lock:
            if self._pipeline and self._pipeline_active and not self._pipeline.is_idle():
                self._pipeline.stop()
        if self._pipeline_thread and self._pipeline_thread.is_alive():
            self._pipeline_thread.join(timeout=2.0)
        self._audio.close()
        logger.info("SayitOrchestrator: stopped")

    def is_recording(self) -> bool:
        with self._pipeline_lock:
            pipeline = self._pipeline
        return bool(pipeline and pipeline.state == RecordingState.CAPTURING)

    def is_busy(self) -> bool:
        """True while a pipeline is active in any phase (capture through DONE)."""
        with self._pipeline_lock:
            return self._pipeline_active

    def start_recording(self):
        """Public API — start recording manually (e.g. from UI button)."""
        return self._on_hotkey_start()

    def stop_recording(self):
        """Public API — stop recording manually."""
        return self._on_hotkey_stop()

    def toggle_recording(self):
        """Toggle recording on/off. Called from the keyboard hook worker thread.

        State table:
          - idle (no pipeline)             → start a new pipeline
          - CAPTURING                       → signal stop (no new pipeline)
          - TRANSCRIBING/CORRECTING/INJECTING/DONE/ERROR (pipeline still alive)
                                            → IGNORED + UI event TOGGLE_IGNORED
        """
        with self._pipeline_lock:
            active = self._pipeline_active
            pipeline = self._pipeline
        if not active:
            return self._on_hotkey_start()
        if pipeline is None:
            return self._on_hotkey_start()
        # Pipeline alive — only honor a stop when we are still capturing.
        state = pipeline.state
        if state == RecordingState.CAPTURING:
            return self._on_hotkey_stop()
        # Past capture: post-processing is in flight. Drop the press so a
        # second pipeline cannot share the audio device or injector.
        stage = state.value if hasattr(state, "value") else str(state)
        logger.info(
            "[orchestrator] toggle ignored — pipeline busy in stage=%s", stage)
        try:
            self._eb.emit(Events.TOGGLE_IGNORED, stage)
        except Exception:
            pass
        return False

    def get_hotwords_manager(self) -> HotwordsManager:
        return self._hotwords

    def get_database(self) -> Database:
        return self._db

    def get_config(self) -> ConfigStore:
        return self._config

    def reload_config(self):
        """Reload all components from config."""
        if self._config.reload_if_changed():
            # Rebuild audio gain
            self._audio.set_gain(self._config.get("audio", "gain_multiplier", 2.0))
            # Rebuild ASR cascade
            self._asr = AsrCascade(self._config.get_all())
            # Rebuild corrector
            self._corrector.reload_config()
            # Rebuild injector
            self._injector = Injector(
                injection_mode=self._config.get("injection_mode", "auto"))
            # Update hotwords → ASR
            self._hotwords.set_asr_engine(self._asr)
            self._hotwords._sync_to_asr()
            self._eb.emit(Events.CONFIG_CHANGED)
            logger.info("SayitOrchestrator: config reloaded")

    # ── Keyboard hook (WH_KEYBOARD_LL via ctypes DLL, Typeless architecture) ──

    def _install_keyboard_hook(self):
        """Install the WH_KEYBOARD_LL hook via the keyboard helper DLL.

        The DLL is loaded lazily and the hook callback simply calls
        toggle_recording() — same logic as the old Electron addon callback.
        """
        try:
            self._keyboard_helper = KeyboardHelperDll()
            if not self._keyboard_helper.is_available:
                logger.warning("[orchestrator] keyboard helper DLL not available — RAlt disabled")
                return
            # Log runtime identity of the loaded DLL so we can prove which
            # build is actually in this process. The dict contains only
            # paths/versions/counters — never user text.
            try:
                diag = self._keyboard_helper.diagnostics()
                logger.info(
                    "[orchestrator] keyboard helper identity: "
                    "path=%s version=%s build=%s pid=%s",
                    diag.get("dll_path"), diag.get("helper_version"),
                    diag.get("helper_build_id"), diag.get("pid"))
            except Exception:
                pass
            ok = self._keyboard_helper.install(self.toggle_recording)
            if ok:
                logger.info("[orchestrator] RAlt hotkey installed via keyboard helper DLL")
                self._stop_watcher = RAltStopWatcher(
                    self._fallback_stop, self._keyboard_helper)
                logger.info("[orchestrator] RAltStopWatcher created with helper v%d",
                            self._keyboard_helper.helper_version)
            else:
                logger.warning("[orchestrator] RAlt hotkey install failed")
        except Exception as e:
            logger.warning("[orchestrator] keyboard hook init failed: %s", e)
            self._keyboard_helper = None

    def _uninstall_keyboard_hook(self):
        """Uninstall the WH_KEYBOARD_LL hook."""
        try:
            if self._keyboard_helper and self._keyboard_helper.is_installed:
                self._keyboard_helper.uninstall()
                logger.info("[orchestrator] keyboard hook uninstalled")
        except Exception as e:
            logger.warning("[orchestrator] keyboard hook uninstall failed: %s", e)
            self._keyboard_helper = None

    # ── Internal ────────────────────────────────────────────

    def _on_hotkey_start(self):
        """Called by hotkey manager when recording should start.

        P0 mutex guard: silently rejects when a pipeline is already active.
        Two pipelines must never compete for injector._lock — that is the
        root cause of keyboard hijack and corruption on long recordings.
        """
        # UIPI check: warn if foreground window is elevated (admin) and we are not
        try:
            from infrastructure.injector import is_uipi_blocked
            if is_uipi_blocked():
                self._eb.emit(Events.UIPI_WARNING)
                logger.warning("[orchestrator] UIPI blocked — admin window in foreground")
        except Exception:
            pass

        # Reset stop latch for the new recording session.
        # Allows the user to stop this new recording with the next RAlt press.
        self._stop_request_latched = False

        with self._pipeline_lock:
            if self._pipeline_active:
                logger.warning(
                    "[orchestrator] start rejected — pipeline already active "
                    "(concurrent pipeline race prevented)")
                return False
            self._pipeline_active = True
            # Take the slot under the lock so a concurrent toggle on a
            # different thread cannot observe active=True with pipeline=None.
            _my_pipeline = RecordingPipeline(self._eb)
            self._pipeline = _my_pipeline

        injection_target = None
        try:
            injection_target = self._injector.capture_target()
        except Exception as e:
            logger.warning("[orchestrator] capture injection target failed: %s", e)

        def _pipeline_wrapper():
            """Run pipeline; ALWAYS clear active flag in finally.

            The mutex is held for the entire pipeline life — capture,
            transcribe, correct, inject, save. _on_hotkey_stop never
            detaches us; we are the single owner of state reset.
            """
            try:
                _my_pipeline.run(
                    audio_capture=self._audio,
                    asr_cascade=self._asr,
                    corrector=self._corrector,
                    hotwords_mgr=self._hotwords,
                    injector=self._injector,
                    silent_monitor=self._silent_monitor,
                    db=self._db,
                    enable_correction=(
                        self._config.get("enable_correction", True) or
                        self._config.get("enable_structuring", True)
                    ),
                    injection_target=injection_target,
                )
            except Exception as e:
                logger.error("[orchestrator] pipeline crashed: %s", e)
            finally:
                # Defensive: wait for audio device to fully release so the
                # next pipeline doesn't see a still-active stream. The
                # pipeline already calls audio_capture.stop() inside run(),
                # so this is just a guard against early-abort paths.
                try:
                    self._audio.wait_for_stop(timeout=3.0)
                except Exception:
                    pass
                # Safety net: disarm the RAlt stop watcher in case
                # _on_hotkey_stop never ran (e.g. pipeline self-terminated
                # or an error path bypassed normal stop). Idempotent.
                try:
                    if self._stop_watcher is not None:
                        self._stop_watcher.disarm()
                except Exception:
                    pass
                # Focus restore: after pipeline completes, try to restore
                # the focus that was captured at stop time. Only restores
                # if the hwnd is still valid and is NOT a SayIt window.
                if self._pre_stop_focus_hwnd:
                    self._focus_window(self._pre_stop_focus_hwnd)
                    self._pre_stop_focus_hwnd = 0
                with self._pipeline_lock:
                    if self._pipeline is _my_pipeline:
                        self._pipeline_active = False
                        self._pipeline = None
                        self._pipeline_thread = None
                        logger.info("[orchestrator] pipeline mutex released")

        self._pipeline_thread = threading.Thread(
            target=_pipeline_wrapper, daemon=True, name="pipeline")
        self._pipeline_thread.start()

        # Arm the RAlt stop watcher as soon as the pipeline is running.
        # It will detect the second RAlt down→up and fire a fallback stop
        # if the hook misses it. The snapshot of total_emitted must be
        # taken AFTER the pipeline thread starts so that the start-toggle
        # has already been processed by the hook.
        if self._stop_watcher is not None:
            try:
                te = self._keyboard_helper.get_total_emitted() \
                    if self._keyboard_helper else -1
                self._stop_watcher.arm(total_emitted=te)
            except Exception as e:
                logger.warning("[orchestrator] RAltStopWatcher arm failed: %s", e)

        return True

    def _is_sayit_hwnd(self, hwnd: int) -> bool:
        """Return True if hwnd belongs to one of SayIt's own windows."""
        if not hwnd:
            return False
        try:
            title_buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 256)
            title = title_buf.value or ""
            cls_buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, cls_buf, 256)
            cls = cls_buf.value or ""
            # SayIt windows: main window, float bar, result card.
            # Match by class prefix or known title patterns.
            return any(kw in title for kw in ("SayIt", "sayit", "Sayit")) \
                or "Chrome_WidgetWin_0" in cls and ("SayIt" in title or "sayit" in title)
        except Exception:
            return False

    def _get_foreground_hwnd(self) -> int:
        """Capture the current foreground window hwnd."""
        try:
            return int(ctypes.windll.user32.GetForegroundWindow() or 0)
        except Exception:
            return 0

    def _try_latch_stop(self) -> bool:
        """Atomically try to obtain the stop latch.

        Returns True if this caller wins the latch (first to acquire it).
        Only the latch winner may proceed with _execute_stop_request.
        Thread-safe via _stop_latch_lock.
        """
        with self._stop_latch_lock:
            if self._stop_request_latched:
                return False
            self._stop_request_latched = True
            return True

    def _focus_window(self, hwnd: int) -> bool:
        """Restore focus to a specific hwnd.

        Only restores if the hwnd is still valid (window exists) and is
        NOT a SayIt window. Returns True if focus was restored.
        """
        if not hwnd:
            return False
        if self._is_sayit_hwnd(hwnd):
            return False
        try:
            if not ctypes.windll.user32.IsWindow(hwnd):
                return False
            cur = ctypes.windll.user32.GetForegroundWindow()
            if cur == hwnd:
                return True
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)
            return True
        except Exception:
            return False

    def _execute_stop_request(self, pipeline):
        """Shared stop execution: capture focus, emit ACK, signal pipeline, disarm watcher.

        Caller must hold _stop_request_latched already and must have
        validated the pipeline state. This method does NOT acquire locks.
        """
        # Capture foreground window hwnd BEFORE stopping the pipeline,
        # so we can restore focus after injection completes.
        self._pre_stop_focus_hwnd = self._get_foreground_hwnd()
        # Emit the visible "stopping" ACK BEFORE we call pipeline.stop().
        # This is the immediate UI feedback the user expects on the second
        # RAlt: don't make them stare at the recording indicator while
        # audio_capture.stop() and ASR drain. The full RECORDING_STOPPED
        # event still fires later from the pipeline thread.
        try:
            self._eb.emit(Events.RECORDING_STOPPING)
        except Exception:
            pass
        pipeline.stop()
        # Disarm the RAlt watch now — the stop signal has been sent to the
        # pipeline; we don't need the fallback anymore for this cycle.
        try:
            if self._stop_watcher is not None:
                self._stop_watcher.disarm()
        except Exception:
            pass

    def _on_hotkey_stop(self):
        """Called when the user wants to stop the current capture.

        Only signals the pipeline's _stop_flag. We DO NOT detach the
        pipeline here — that responsibility lives in _pipeline_wrapper's
        finally clause, after ASR / AI / inject / history have completed.
        Returning early from this method must not allow a second pipeline
        to start while the first is still post-processing — that is the
        root cause of "third RAlt only stops" in long dictations.

        stop_request_latched: the hook and fallback race; first wins.
        Subsequent stop requests are no-ops; RECORDING_STOPPING ACK fires
        exactly once per session.
        """
        if not self._try_latch_stop():
            logger.debug("[orchestrator] stop ignored — already latched")
            return False
        with self._pipeline_lock:
            pipeline = self._pipeline
            active = self._pipeline_active
        if not (pipeline and active):
            logger.debug(
                "[orchestrator] stop ignored — no active pipeline "
                "(pipeline=%s active=%s)", pipeline is not None, active)
            # Release latch since we didn't actually stop
            self._stop_request_latched = False
            return False
        if pipeline.is_idle():
            self._stop_request_latched = False
            return False
        # Only stop while still in CAPTURING — any later state means the
        # pipeline already moved past the user's control point and a stop
        # signal would be a no-op anyway.
        if pipeline.state != RecordingState.CAPTURING:
            self._stop_request_latched = False
            return False
        self._execute_stop_request(pipeline)
        # NB: we don't wait_for_stop / clear flags here. The pipeline
        # thread runs through to DONE/ERROR, and only then does its
        # _pipeline_wrapper.finally clear _pipeline_active. That is what
        # keeps RAlt presses arriving during ASR/AI/inject from racing
        # into a parallel pipeline.
        return True

    def _fallback_stop(self):
        """Fallback stop invoked by RAltStopWatcher when hook missed second RAlt.

        This method is called from the watcher's polling thread (daemon).
        It must NOT hold _pipeline_lock to avoid deadlock with the pipeline
        thread (which may be in _on_hotkey_stop already if the hook just
        barely processed the event). We set the latch and do the stop work
        directly, using the same _execute_stop_request shared path.

        stop_request_latched prevents double-firing if the hook also
        delivered a stop signal before the fallback runs.
        """
        if not self._try_latch_stop():
            logger.debug(
                "[orchestrator] fallback stop ignored — already latched")
            return
        logger.warning(
            "[orchestrator] _fallback_stop invoked — RAlt hook miss detected, "
            "forcing stop via fallback path")
        # Collect native event diagnostics before stopping
        try:
            if self._keyboard_helper:
                diag = self._keyboard_helper.diagnostics()
                native_count = diag.get("native_event_count", -1)
                logger.info(
                    "[orchestrator] fallback diagnostic: total_emitted=%s "
                    "native_events=%s hook_misses=%s fallback_stops=%s "
                    "helper_version=%s",
                    self._keyboard_helper.get_total_emitted(),
                    native_count,
                    self._stop_watcher.hook_misses if self._stop_watcher else -1,
                    self._stop_watcher.fallback_stops if self._stop_watcher else -1,
                    self._keyboard_helper.helper_version)
        except Exception as e:
            logger.debug("[orchestrator] fallback diagnostic error: %s", e)

        # Fast path: we already atomically latched ourselves above.
        # Now capture the pipeline snapshot under _pipeline_lock and execute stop.
        # This is intentionally NOT acquired for the whole stop — we must avoid
        # deadlock with the pipeline thread which may hold the injector lock.
        with self._pipeline_lock:
            pipeline = self._pipeline
            active = self._pipeline_active
        if pipeline and active and not pipeline.is_idle() \
                and pipeline.state == RecordingState.CAPTURING:
            self._execute_stop_request(pipeline)

    def _start_config_watcher(self):
        """Start background thread that watches config.json for changes."""
        self._reload_running = True

        def _watch():
            while self._reload_running:
                time.sleep(2.0)
                try:
                    self.reload_config()
                except Exception as e:
                    logger.debug("Config watcher error: %s", e)

        self._reload_thread = threading.Thread(
            target=_watch, daemon=True, name="config-watcher")
        self._reload_thread.start()

    def _stop_config_watcher(self):
        self._reload_running = False

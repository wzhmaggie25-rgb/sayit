"""Application orchestrator — wires together all components.

Manages the lifecycle of: hotkey listening, audio capture, ASR, AI correction,
text injection, silent learning, hotwords, and config hot-reload.
"""
from __future__ import annotations
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

        # Pipeline — guarded by exclusive mutex
        self._pipeline: Optional[RecordingPipeline] = None
        self._pipeline_thread: Optional[threading.Thread] = None
        self._pipeline_lock = threading.Lock()     # ✓ P0: absolute mutex — only 1 pipeline alive
        self._pipeline_active = False               # ✓ P0: flag checked under lock

        # Config hot-reload
        self._reload_running = False
        self._reload_thread: Optional[threading.Thread] = None

        # Keyboard hook: WH_KEYBOARD_LL via ctypes DLL (Typeless architecture)
        self._keyboard_helper = None

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

    def start_recording(self):
        """Public API — start recording manually (e.g. from UI button)."""
        return self._on_hotkey_start()

    def stop_recording(self):
        """Public API — stop recording manually."""
        return self._on_hotkey_stop()

    def toggle_recording(self):
        """Toggle recording on/off. Called from Electron addon via WS."""
        if self.is_recording():
            return self._on_hotkey_stop()
        else:
            return self._on_hotkey_start()

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
            ok = self._keyboard_helper.install(self.toggle_recording)
            if ok:
                logger.info("[orchestrator] RAlt hotkey installed via keyboard helper DLL")
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

        with self._pipeline_lock:
            if self._pipeline_active:
                logger.warning(
                    "[orchestrator] start rejected — pipeline already active "
                    "(concurrent pipeline race prevented)")
                return False
            self._pipeline_active = True

        injection_target = None
        try:
            injection_target = self._injector.capture_target()
        except Exception as e:
            logger.warning("[orchestrator] capture injection target failed: %s", e)

        self._pipeline = RecordingPipeline(self._eb)

        # Capture the pipeline object so the finally block can safely check
        # whether it's still the active pipeline — _on_hotkey_stop may have
        # detached it (set self._pipeline = None) and a new _on_hotkey_start
        # may have created a replacement.
        _my_pipeline = self._pipeline

        def _pipeline_wrapper():
            """Run pipeline, then clear the active flag so next hotkey works."""
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
                # Only clear orchestrator state if WE are still the active
                # pipeline — if _on_hotkey_stop detached us + a new pipeline
                # was started, self._pipeline points to the new object.
                with self._pipeline_lock:
                    if self._pipeline is _my_pipeline:
                        self._pipeline_active = False
                        self._pipeline = None
                        self._pipeline_thread = None
                        logger.info("[orchestrator] pipeline mutex released")

        self._pipeline_thread = threading.Thread(
            target=_pipeline_wrapper, daemon=True, name="pipeline")
        self._pipeline_thread.start()
        return True

    def _on_hotkey_stop(self):
        """Called by hotkey manager when recording should stop.

        Signals the pipeline to stop capturing, then waits for the audio
        device to be fully released before detaching the pipeline.
        This ensures the shared AudioCapture object is idle before a new
        pipeline can start recording again.

        The old pipeline thread continues post-processing (ASR → AI → inject
        → save) independently as a fire-and-forget thread.
        """
        with self._pipeline_lock:
            pipeline = self._pipeline
            active = self._pipeline_active
        if pipeline and active and not pipeline.is_idle():
            pipeline.stop()  # sets _stop_flag — capture loop exits

            # Wait for audio capture to complete (read thread exits, stream
            # closed). The pipeline thread calls audio_capture.stop() ~50-200ms
            # after _stop_flag is set. We wait up to 3s to be safe.
            self._audio.wait_for_stop(timeout=3.0)

            # Now it's safe to detach — audio device is idle, no more
            # callbacks will fire from the old pipeline.
            with self._pipeline_lock:
                if self._pipeline is pipeline:
                    self._pipeline_active = False
                    self._pipeline = None
                    self._pipeline_thread = None
                    logger.info("[orchestrator] pipeline detached (audio captured)")
            return True
        else:
            logger.debug(
                "[orchestrator] stop ignored — no active pipeline "
                "(pipeline=%s active=%s)", pipeline is not None, active)
            return False

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

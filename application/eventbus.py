"""Global event bus — decouples UI from backend.

Signals are callback-based. Each event type can have multiple listeners.
All callbacks are invoked on the calling thread (use pywebview's
evaluate_js to marshal to the webview thread when needed).
"""
from __future__ import annotations
import logging
from collections import defaultdict
from typing import Callable, Any

logger = logging.getLogger(__name__)


class EventBus:
    """Simple publish-subscribe event bus."""

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, callback: Callable):
        """Register a listener for an event type."""
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable):
        """Remove a listener."""
        if event in self._listeners:
            self._listeners[event] = [cb for cb in self._listeners[event] if cb is not callback]

    def emit(self, event: str, *args, **kwargs):
        """Emit an event to all listeners. Exceptions are logged, not raised."""
        if event not in self._listeners:
            return
        for cb in self._listeners[event]:
            try:
                cb(*args, **kwargs)
            except Exception:
                logger.exception("[EventBus] Error in listener for '%s'", event)

    def clear(self, event: str = None):
        """Clear all listeners for an event, or all events if event is None."""
        if event is None:
            self._listeners.clear()
        elif event in self._listeners:
            self._listeners[event].clear()


# Event name constants
class Events:
    """Well-known event names for type-safety."""
    # Recording pipeline
    RECORDING_STARTED = "recording:started"            # session_id: str
    RECORDING_STOPPED = "recording:stopped"
    RECORDING_TICK = "recording:tick"           # seconds: int
    RECORDING_ERROR = "recording:error"          # error_msg: str
    RMS_LEVEL = "recording:rms-level"            # level: float

    # ASR
    ASR_RESULT = "asr:result"                    # text: str, engine: str
    ASR_ERROR = "asr:error"                      # error_msg: str
    ASR_PROGRESS = "asr:progress"                # stage: str, message: str, engine: str
    ASR_PARTIAL = "asr:partial"                  # text: str, engine: str
    ASR_DEGRADED = "asr:degraded"                # from_engine: str, to_engine: str, reason: str

    # AI Correction
    AI_RESULT = "ai:result"                      # text: str
    AI_ERROR = "ai:error"                        # error_msg: str
    AI_DEGRADED = "ai:degraded"                  # message: str (e.g. "AI 整理超时，已使用识别结果")

    # Pipeline
    PIPELINE_DONE = "pipeline:done"              # final_text: str
    PIPELINE_ERROR = "pipeline:error"            # error_msg: str

    # Injection
    INJECTION_DONE = "injection:done"            # result: InjectionResult (structured)

    # Result card (no editable target)
    NO_EDITABLE_TARGET = "pipeline:no-editable-target"  # final_text: str
    RESULT_CARD_SHOW = "result_card:show"               # final_text, last_transcription, state, message
    RESULT_CARD_COPY = "result_card:copy"               # final_text: str
    RESULT_CARD_CLOSE = "result_card:close"             # no payload

    # Silent learning
    SILENT_LEARNED = "silent:learned"            # rule_count: int (0 = none learned)

    # Config
    CONFIG_CHANGED = "config:changed"

    # UIPI
    UIPI_WARNING = "uipi:warning"                # foreground window is elevated

    # Hotkey
    HOTKEY_CHANGED = "hotkey:changed"            # new_hotkey: str

    # Toggle gating — fired by orchestrator when a hotkey press is dropped
    # because the previous pipeline is still working through ASR / AI / inject.
    # Payload: stage name (e.g. "transcribing", "injecting") for UI hint.
    TOGGLE_IGNORED = "toggle:ignored"            # stage: str

    # Lightweight hint — for attempted_unverified or injection_failed with dispatch.
    # Shows a brief toast on the float bar instead of a large result card.
    LIGHT_HINT = "result_card:light-hint"        # message: str

    # Stop ACK — fired by orchestrator the moment a second RAlt press is
    # accepted as a stop request, BEFORE audio_capture.stop() returns or the
    # downstream ASR/AI/inject phases complete. UI subscribers should treat
    # this as "user wants to stop; show processing state immediately". No
    # payload — RECORDING_STOPPED still fires later once audio actually
    # finalizes.
    RECORDING_STOPPING = "recording:stopping"

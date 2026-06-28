"""A2: Test pipeline crash terminalization.

Verify that when any stage of the pipeline throws an exception,
a terminal event (PIPELINE_TERMINAL) is emitted with outcome=failed and the
frontend gets notified so it exits STOPPING state.

Also verifies: empty text never creates a result card.
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)


class FakeEventBus:
    """Event bus that records all emits for verification."""
    def __init__(self):
        self.emits = []

    def on(self, event, cb):
        pass

    def emit(self, event, *args, **kwargs):
        self.emits.append((event, args, kwargs))


def _start_stop_timer(p, delay=0.1):
    """Start a timer that will stop the pipeline after a delay.
    Returns the timer so caller can join it."""
    def _do_stop():
        p.stop()
    t = threading.Timer(delay, _do_stop)
    t.daemon = True
    t.start()
    return t


class TestPipelineTerminalEvents(unittest.TestCase):
    """Verify PIPELINE_TERMINAL is emitted in all failure scenarios."""

    def setUp(self):
        from application.eventbus import Events
        from application.pipeline import RecordingPipeline
        self.Events = Events
        self.Pipeline = RecordingPipeline

    def _make_pipeline(self):
        eb = FakeEventBus()
        p = self.Pipeline(eb)
        return p, eb

    def _pcm_bytes(self, seconds=2):
        """Generate fake PCM data that passes MIN_PCM_LENGTH check."""
        import struct
        # 16kHz 16-bit mono = 32000 bytes/sec
        return b"\x00\x00" * (16000 * seconds)

    def test_pipeline_crash_streaming_sends_terminal(self):
        """Streaming ASR finish failure must produce terminal event."""
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.2)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes()

        asr = MagicMock()
        streaming = MagicMock()
        streaming.finish.side_effect = RuntimeError("streaming crash")
        asr.create_streaming_session.return_value = streaming
        # Configure transcribe to raise
        type(asr).transcribe = MagicMock(side_effect=RuntimeError("batch asr crash too"))

        corrector = MagicMock()
        hotwords = MagicMock()
        injector = MagicMock()
        silent = MagicMock()
        db = MagicMock()
        db.get_rules.return_value = []

        try:
            p.run(
                audio_capture=audio,
                asr_cascade=asr,
                corrector=corrector,
                hotwords_mgr=hotwords,
                injector=injector,
                silent_monitor=silent,
                db=db,
                enable_correction=False,
            )
        except Exception:
            pass
        tmr.join(timeout=3)

        # Verify terminal event was emitted with outcome=failed
        terminal_events = [
            e for e in eb.emits
            if e[0] == "pipeline:terminal"
        ]
        self.assertGreaterEqual(
            len(terminal_events), 1,
            f"Expected PIPELINE_TERMINAL event, got emits: {eb.emits}"
        )
        # Check outcome — payload is first positional arg
        payload = terminal_events[0][1][0] if terminal_events[0][1] else terminal_events[0][2]
        outcome = payload.get("outcome", "")
        self.assertEqual(outcome, "failed")

    def test_pipeline_crash_asr_batch_sends_terminal(self):
        """Batch ASR failure must produce terminal event."""
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.2)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes()

        asr = MagicMock()
        asr.create_streaming_session.return_value = None
        asr.transcribe.side_effect = RuntimeError("batch asr crash")

        corrector = MagicMock()
        hotwords = MagicMock()
        injector = MagicMock()
        silent = MagicMock()
        db = MagicMock()
        db.get_rules.return_value = []

        try:
            p.run(
                audio_capture=audio,
                asr_cascade=asr,
                corrector=corrector,
                hotwords_mgr=hotwords,
                injector=injector,
                silent_monitor=silent,
                db=db,
                enable_correction=False,
            )
        except Exception:
            pass
        tmr.join(timeout=3)

        terminal_events = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertGreaterEqual(
            len(terminal_events), 1,
            f"Expected PIPELINE_TERMINAL, got: {eb.emits}"
        )

    def test_pipeline_crash_injector_sends_terminal(self):
        """Injector failure must produce terminal event."""
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.2)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes()

        asr = MagicMock()
        streaming = MagicMock()
        streaming.finish.return_value = "测试文字"
        asr.create_streaming_session.return_value = streaming
        asr.transcribe.return_value = ("测试文字", "mock")

        corrector = MagicMock()
        hotwords = MagicMock()
        hotwords.apply_layer2_correction.side_effect = lambda x: x

        injector = MagicMock()
        injector.inject.side_effect = RuntimeError("inject crash")

        db = MagicMock()
        db.get_rules.return_value = []
        db.add_history.return_value = 1

        silent = MagicMock()

        try:
            p.run(
                audio_capture=audio,
                asr_cascade=asr,
                corrector=corrector,
                hotwords_mgr=hotwords,
                injector=injector,
                silent_monitor=silent,
                db=db,
                enable_correction=False,
            )
        except Exception:
            pass
        tmr.join(timeout=3)

        terminal_events = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertGreaterEqual(
            len(terminal_events), 1,
            f"Expected PIPELINE_TERMINAL, got: {eb.emits}"
        )

    def test_empty_text_does_not_create_result_card(self):
        """Whitespace-only final_text must not emit RESULT_CARD_SHOW."""
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.2)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes()

        asr = MagicMock()
        streaming = MagicMock()
        streaming.finish.return_value = "   "  # whitespace-only
        asr.create_streaming_session.return_value = streaming
        asr.transcribe.return_value = ("测试文字", "mock")

        corrector = MagicMock()
        hotwords = MagicMock()
        hotwords.apply_layer2_correction.side_effect = lambda x: x

        injector = MagicMock()
        inject_result = MagicMock()
        inject_result.state = "no_editable_target"
        inject_result.injection_dispatched = False
        inject_result.verified = False
        inject_result.target_verified = False
        injector.inject.return_value = inject_result
        injector.last_target_proc = "test.exe"
        injector.last_target_title = "Test"
        injector.last_target_class = "TestClass"
        injector.last_target_hwnd = 0
        injector.last_target_pid = 0

        db = MagicMock()
        db.get_rules.return_value = []
        db.add_history.return_value = 1

        silent = MagicMock()

        try:
            p.run(
                audio_capture=audio,
                asr_cascade=asr,
                corrector=corrector,
                hotwords_mgr=hotwords,
                injector=injector,
                silent_monitor=silent,
                db=db,
                enable_correction=False,
            )
        except Exception:
            pass
        tmr.join(timeout=3)

        # Verify no RESULT_CARD_SHOW for whitespace text
        result_card_shows = [
            e for e in eb.emits
            if e[0] == "result_card:show"
        ]
        self.assertEqual(
            len(result_card_shows), 0,
            f"Empty text should not create result card, got: {result_card_shows}"
        )

    def test_terminal_emitted_only_once(self):
        """A terminal event should be emitted exactly once per session."""
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.2)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes()

        asr = MagicMock()
        streaming = MagicMock()
        streaming.finish.return_value = "测试文字"
        asr.create_streaming_session.return_value = streaming
        asr.transcribe.return_value = ("测试文字", "mock")

        corrector = MagicMock()
        hotwords = MagicMock()
        hotwords.apply_layer2_correction.side_effect = lambda x: x

        injector = MagicMock()
        inject_result = MagicMock()
        inject_result.state = "verified_success"
        inject_result.injection_dispatched = True
        inject_result.verified = True
        inject_result.target_verified = True
        injector.inject.return_value = inject_result
        injector.last_target_proc = "test.exe"
        injector.last_target_title = "Test"
        injector.last_target_class = "TestClass"
        injector.last_target_hwnd = 12345
        injector.last_target_pid = 6789

        db = MagicMock()
        db.get_rules.return_value = []
        db.add_history.return_value = 1

        silent = MagicMock()

        try:
            p.run(
                audio_capture=audio,
                asr_cascade=asr,
                corrector=corrector,
                hotwords_mgr=hotwords,
                injector=injector,
                silent_monitor=silent,
                db=db,
                enable_correction=False,
            )
        except Exception:
            pass
        tmr.join(timeout=3)

        terminal_events = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertEqual(
            len(terminal_events), 1,
            f"Expected exactly 1 terminal, got {len(terminal_events)}: {[e[2] for e in terminal_events]}"
        )


if __name__ == "__main__":
    unittest.main()
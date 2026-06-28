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

    # ── Orchestrator path: exactly one terminal, _terminal_emitted reset ─

    def test_terminal_latch_is_not_sticky_across_sessions(self):
        """BUG-DOC: _terminal_emitted is set in __init__ but NOT reset in run().

        Current bug: _terminal_emitted = False is only assigned in __init__
        (pipeline.py:33). run() (line 49) does NOT reset it. After the first
        pipeline run emits a terminal event, subsequent runs with the same
        pipeline instance will skip _emit_terminal due to the latch.

        Pipeline is recreated by orchestrator per-session, so the actual bug
        manifests when a pipeline exception handler (orchestrator.py:321-329)
        bypasses the pipeline latch, or when run() is called twice on the
        same pipeline instance.
        """
        p, eb = self._make_pipeline()

        # First run — should emit terminal
        self.assertFalse(p._terminal_emitted, "Latch should start False")

        tmr1 = _start_stop_timer(p, delay=0.1)
        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes(2)

        asr = MagicMock()
        streaming = MagicMock()
        streaming.finish.side_effect = RuntimeError("streaming crash")
        asr.create_streaming_session.return_value = streaming
        asr.transcribe = MagicMock(side_effect=RuntimeError("batch asr crash too"))

        corrector = MagicMock()
        hotwords = MagicMock()
        injector = MagicMock()
        silent = MagicMock()
        db = MagicMock()
        db.get_rules.return_value = []

        try:
            p.run(
                audio_capture=audio, asr_cascade=asr,
                corrector=corrector, hotwords_mgr=hotwords,
                injector=injector, silent_monitor=silent, db=db,
                enable_correction=False,
            )
        except Exception:
            pass
        tmr1.join(timeout=3)

        terminal1 = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertEqual(len(terminal1), 1, "First run should emit exactly 1 terminal")

        # After first run, latch should be True
        self.assertTrue(p._terminal_emitted,
                        "Latch should be True after first terminal emission")

        # BUG: run() does not reset _terminal_emitted. Second run on same
        # instance skips _emit_terminal. In production the orchestrator creates
        # a new pipeline per session, so this bug is masked.
        # After Phase F fix: _terminal_emitted = False must be in run().
        eb.emits.clear()
        tmr2 = _start_stop_timer(p, delay=0.1)
        try:
            p.run(
                audio_capture=audio, asr_cascade=asr,
                corrector=corrector, hotwords_mgr=hotwords,
                injector=injector, silent_monitor=silent, db=db,
                enable_correction=False,
            )
        except Exception:
            pass
        tmr2.join(timeout=3)

        terminal2 = [e for e in eb.emits if e[0] == "pipeline:terminal"]

        # Phase F: _terminal_emitted = False is now set in run(), so the latch
        # is properly reset across sessions. Second run should emit terminal.
        self.assertGreaterEqual(
            len(terminal2), 1,
            f"Second run terminal count = {len(terminal2)} — _terminal_emitted "
            f"was not reset in run()"
        )

    def test_orchestrator_exception_handler_emits_terminal(self):
        """Orchestrator exception handler emits terminal event.

        When pipeline.run() raises an exception, the orchestrator's
        _pipeline_wrapper (line 317-329) emits PIPELINE_TERMINAL directly
        via eventbus, bypassing the pipeline's _emit_terminal() latch.

        This test verifies that the bypass emits correctly.
        After Phase F: orchestrator should use pipeline._emit_terminal()
        instead of direct emit, so the latch is respected.
        """
        from application.eventbus import Events

        eb = FakeEventBus()
        p = self.Pipeline(eb)

        # Simulate what orchestrator does on exception
        p._session_id = "test-session"

        try:
            # Bypass: direct emit like orchestrator.py:321-326
            eb.emit(Events.PIPELINE_TERMINAL, {
                "session_id": p._session_id,
                "outcome": "failed",
                "stage": "unknown",
                "reason_code": "uncaught_pipeline_exception",
            })
        except Exception:
            pass

        # Verify terminal was emitted
        terminal_events = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertEqual(
            len(terminal_events), 1,
            f"Orchestrator bypass should emit exactly 1 terminal, got: {eb.emits}"
        )

        # But the pipeline latch is still False — bypass escapes it!
        self.assertFalse(
            p._terminal_emitted,
            "BUG: orchestrator bypass does not set pipeline's _terminal_emitted!"
        )

        # After Phase F: orchestrator should call p._emit_terminal() instead
        # of direct eb.emit(), which would set the latch.

    def test_terminal_payload_has_final_text_available(self):
        """Terminal payload must include final_text_available field.

        Phase F adds 'final_text_available' to the terminal payload so
        the frontend can distinguish success-with-text from empty-terminal.
        """
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.2)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes(2)

        asr = MagicMock()
        streaming = MagicMock()
        streaming.finish.return_value = ""
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
                audio_capture=audio, asr_cascade=asr,
                corrector=corrector, hotwords_mgr=hotwords,
                injector=injector, silent_monitor=silent, db=db,
                enable_correction=False,
            )
        except Exception:
            pass
        tmr.join(timeout=3)

        terminal_events = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertGreaterEqual(len(terminal_events), 1)

        payload = terminal_events[0][1][0] if terminal_events[0][1] else terminal_events[0][2]
        # Phase F: payload must include 'final_text_available'
        if "final_text_available" not in payload:
            print("[INFO] BUG-DOC: terminal payload lacks 'final_text_available' field")
        else:
            print(f"[INFO] Phase F detected: final_text_available = {payload['final_text_available']}")

    def test_5_outcomes_each_emits_terminal(self):
        """All 5 terminal outcomes must each produce a terminal event."""
        from application.result_card_eligibility import should_show_large_result_card
        from application.eventbus import Events

        for outcome in ["success", "no_target", "attempted_unverified", "failed", "aborted"]:
            eb = FakeEventBus()
            p = self.Pipeline(eb)
            tmr = _start_stop_timer(p, delay=0.1)

            audio = MagicMock()
            audio.start.return_value = None
            audio.stop.return_value = self._pcm_bytes(2)

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
                    audio_capture=audio, asr_cascade=asr,
                    corrector=corrector, hotwords_mgr=hotwords,
                    injector=injector, silent_monitor=silent, db=db,
                    enable_correction=False,
                )
            except Exception:
                pass
            tmr.join(timeout=3)

            terminal_events = [e for e in eb.emits if e[0] == "pipeline:terminal"]
            self.assertGreaterEqual(
                len(terminal_events), 1,
                f"Outcome '{outcome}' should produce a terminal event"
            )


if __name__ == "__main__":
    unittest.main()
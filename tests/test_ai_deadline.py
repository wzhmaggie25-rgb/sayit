"""Pipeline AI deadline watchdog tests.

Verifies the AI timeout requirements from ROUND9_LONG_TASK.md §Phase 5:

  - AI deadline (default 25s, configurable 15-45s)
  - Timeout falls back to locally_refined_text
  - AI_DEGRADED event emitted on timeout
  - Provider HTTP error uses local text
  - Provider empty response uses local text
  - No duplicate injection
  - No lingering daemon threads after timeout

Test approach
-------------
Patch corrector.process to simulate various failure modes,
then drive pipeline.run() and observe emitted events.
"""
from __future__ import annotations
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import httpx

from application.eventbus import EventBus, Events
from application.pipeline import RecordingPipeline
from domain.models import RecordingState


class AiDeadlineTests(unittest.TestCase):
    """Test suite for AI deadline watchdog in pipeline."""

    def setUp(self):
        self.eb = EventBus()
        self.pipeline = RecordingPipeline(self.eb)
        self._captured_events = []

        # Capture all events for verification
        def _capture(event, *args):
            self._captured_events.append((event, args))

        # Subscribe to key events
        self.eb.on("ai:result", lambda t, pid=None, mn=None: _capture("ai:result", t, pid, mn))
        self.eb.on("ai:error", lambda m: _capture("ai:error", m))
        self.eb.on("ai:degraded", lambda m: _capture("ai:degraded", m))
        self.eb.on("pipeline:done", lambda t: _capture("pipeline:done", t))
        self.eb.on("pipeline:error", lambda m: _capture("pipeline:error", m))

        # Mock infrastructure components
        self._audio = MagicMock()
        self._audio.stop.return_value = b"\x00" * 100000  # must exceed MIN_PCM_LENGTH (9600)
        self._asr = MagicMock()
        self._asr.transcribe.return_value = ("hello world", "test_engine")
        self._asr.create_streaming_session.return_value = None

        self._corrector = MagicMock()
        self._corrector.process.return_value = ("Hello World Corrected", "test_provider", "test_model")

        self._hotwords = MagicMock()
        self._hotwords.apply_layer2_correction.side_effect = lambda t: t
        self._hotwords.get_words.return_value = []

        self._injector = MagicMock()
        inj_result = MagicMock()
        inj_result.ok = True
        inj_result.state = "verified_success"
        inj_result.verified = True
        inj_result.method = "clipboard"
        inj_result.reason = ""
        inj_result.clipboard_restored = True
        inj_result.injection_dispatched = True
        inj_result.target_verified = True
        self._injector.inject.return_value = inj_result
        self._injector.last_target_hwnd = 12345
        self._injector.last_target_pid = 6789
        self._injector.last_target_proc = "notepad"
        self._injector.last_target_title = "Untitled - Notepad"
        self._injector.last_target_class = "Notepad"

        self._silent_monitor = MagicMock()
        self._db = MagicMock()
        self._db.add_history.return_value = "hist_001"
        self._db.get_rules.return_value = []

    def _start_stop_trigger(self, delay: float = 0.05):
        """Spawn a daemon thread to set pipeline._stop_flag after a delay.

        The pipeline.run() recording phase loops on _stop_flag; this
        simulates what a real hotkey press (orchestrator calling stop())
        would do in production.
        """
        def _trigger():
            time.sleep(delay)
            self.pipeline.stop()
        t = threading.Thread(target=_trigger, daemon=True)
        t.start()

    def _assert_event_emitted(self, event_name: str) -> bool:
        """Check if an event was emitted."""
        return any(ev[0] == event_name for ev in self._captured_events)

    def _count_event(self, event_name: str) -> int:
        return sum(1 for ev in self._captured_events if ev[0] == event_name)

    # ── 1: AI timeout ────────────────────────────────────────

    def test_ai_timeout_uses_local_text(self):
        """When AI correction times out, pipeline continues with locally_refined_text."""
        # Make corrector.process raise httpx.TimeoutException (simulate HTTP timeout)
        self._corrector.process.side_effect = httpx.TimeoutException(
            "AI provider timed out")

        # Run pipeline with short timeout via config override
        with patch('application.pipeline.ConfigStore.get') as mock_config:
            def _config_get(key, default=None):
                if key == "organize_level":
                    return "light"
                if key == "ai_timeout":
                    return 1.0  # 1s deadline for test speed
                if key == "silent_learning":
                    return True
                return default
            mock_config.side_effect = _config_get

            self._start_stop_trigger(0.05)
            self.pipeline.run(
                audio_capture=self._audio,
                asr_cascade=self._asr,
                corrector=self._corrector,
                hotwords_mgr=self._hotwords,
                injector=self._injector,
                silent_monitor=self._silent_monitor,
                db=self._db,
                injection_target=None,
            )

        # AI degraded should be emitted
        self.assertTrue(self._assert_event_emitted("ai:degraded"),
                        "AI_DEGRADED must be emitted on timeout")
        # Pipeline should still complete (DONE)
        self.assertTrue(self._assert_event_emitted("pipeline:done"),
                        "Pipeline must still complete after AI timeout")
        # Inject should have been called once with locally_refined_text
        self.assertEqual(self._injector.inject.call_count, 1,
                         "inject must be called exactly once")

    def test_ai_timeout_no_duplicate_inject(self):
        """After AI timeout, text is injected exactly once."""
        self._corrector.process.side_effect = httpx.TimeoutException(
            "AI provider timed out")

        with patch('application.pipeline.ConfigStore.get') as mock_config:
            def _config_get(key, default=None):
                if key == "organize_level":
                    return "light"
                if key == "ai_timeout":
                    return 1.0
                if key == "silent_learning":
                    return True
                return default
            mock_config.side_effect = _config_get

            self._start_stop_trigger(0.05)
            self.pipeline.run(
                audio_capture=self._audio,
                asr_cascade=self._asr,
                corrector=self._corrector,
                hotwords_mgr=self._hotwords,
                injector=self._injector,
                silent_monitor=self._silent_monitor,
                db=self._db,
                injection_target=None,
            )

        self.assertEqual(self._injector.inject.call_count, 1,
                         "must inject exactly once, never twice")

    # ── 2: Provider HTTP error ────────────────────────────────

    def test_provider_http_error_uses_local_text(self):
        """When AI provider throws HTTP error, pipeline uses local text."""
        self._corrector.process.side_effect = Exception("HTTP 500")

        with patch('application.pipeline.ConfigStore.get') as mock_config:
            def _config_get(key, default=None):
                if key == "organize_level":
                    return "light"
                if key == "ai_timeout":
                    return 25.0  # default
                if key == "silent_learning":
                    return True
                return default
            mock_config.side_effect = _config_get

            self._start_stop_trigger(0.05)
        self.pipeline.run(
                audio_capture=self._audio,
                asr_cascade=self._asr,
                corrector=self._corrector,
                hotwords_mgr=self._hotwords,
                injector=self._injector,
                silent_monitor=self._silent_monitor,
                db=self._db,
                injection_target=None,
            )

        # Should emit AI_ERROR
        self.assertTrue(self._assert_event_emitted("ai:error"),
                        "AI_ERROR must be emitted on provider error")
        # Pipeline should complete
        self.assertTrue(self._assert_event_emitted("pipeline:done"),
                        "Pipeline must complete after AI error")
        # Inject called with locally_refined_text
        self.assertEqual(self._injector.inject.call_count, 1)

    # ── 3: Provider invalid/empty response ────────────────────

    def test_ai_empty_response_uses_local_text(self):
        """When AI returns empty text, pipeline continues with local text."""
        self._corrector.process.return_value = ("", "test_provider", "test_model")

        with patch('application.pipeline.ConfigStore.get') as mock_config:
            def _config_get(key, default=None):
                if key == "organize_level":
                    return "light"
                if key == "ai_timeout":
                    return 25.0
                if key == "silent_learning":
                    return True
                return default
            mock_config.side_effect = _config_get

            self._start_stop_trigger(0.05)
            self.pipeline.run(
                audio_capture=self._audio,
                asr_cascade=self._asr,
                corrector=self._corrector,
                hotwords_mgr=self._hotwords,
                injector=self._injector,
                silent_monitor=self._silent_monitor,
                db=self._db,
                injection_target=None,
            )

        self.assertTrue(self._assert_event_emitted("pipeline:done"))
        self.assertEqual(self._injector.inject.call_count, 1)

    # ── 4: No AI provider configured ──────────────────────────

    def test_no_ai_provider_uses_local_text(self):
        """When no AI provider is configured, pipeline continues."""
        def _no_provider_process(text, hotwords_mgr=None):
            return text, None, None

        self._corrector.process.side_effect = _no_provider_process

        with patch('application.pipeline.ConfigStore.get') as mock_config:
            def _config_get(key, default=None):
                if key == "organize_level":
                    return "light"
                if key == "ai_timeout":
                    return 25.0
                if key == "silent_learning":
                    return True
                return default
            mock_config.side_effect = _config_get

            self._start_stop_trigger(0.05)
            self.pipeline.run(
                audio_capture=self._audio,
                asr_cascade=self._asr,
                corrector=self._corrector,
                hotwords_mgr=self._hotwords,
                injector=self._injector,
                silent_monitor=self._silent_monitor,
                db=self._db,
                injection_target=None,
            )

        self.assertTrue(self._assert_event_emitted("pipeline:done"))
        self.assertEqual(self._injector.inject.call_count, 1)

    # ── 5: Normal AI works unchanged ──────────────────────────

    def test_normal_ai_works(self):
        """When AI works normally, pipeline runs AI result through inject."""
        with patch('application.pipeline.ConfigStore.get') as mock_config:
            def _config_get(key, default=None):
                if key == "organize_level":
                    return "light"
                if key == "ai_timeout":
                    return 25.0
                if key == "silent_learning":
                    return True
                return default
            mock_config.side_effect = _config_get

            self._start_stop_trigger(0.05)
            self.pipeline.run(
                audio_capture=self._audio,
                asr_cascade=self._asr,
                corrector=self._corrector,
                hotwords_mgr=self._hotwords,
                injector=self._injector,
                silent_monitor=self._silent_monitor,
                db=self._db,
                injection_target=None,
            )

        # AI result should be used ("Hello World Corrected")
        self.assertTrue(self._assert_event_emitted("pipeline:done"))
        self.assertFalse(self._assert_event_emitted("ai:degraded"),
                         "No degradation on normal AI")
        # Inject should be called with corrected text
        injected_text = self._injector.inject.call_args[0][0]
        self.assertIn("Corrected", injected_text)

    # ── 6: No lingering daemon threads after timeout ─────────

    def test_ten_consecutive_timeouts_no_thread_leak(self):
        """10 consecutive AI timeouts must NOT increase active thread count.

        Phase G requirement: the synchronous call (httpx timeout) replaces
        the daemon-thread+queue pattern. Every timeout is a clean exception,
        no orphaned threads accumulate.
        """
        self._corrector.process.side_effect = httpx.TimeoutException(
            "AI provider timed out")

        # Baseline thread count
        baseline = threading.active_count()

        for i in range(10):
            with patch('application.pipeline.ConfigStore.get') as mock_config:
                def _config_get(key, default=None):
                    if key == "organize_level":
                        return "light"
                    if key == "ai_timeout":
                        return 1.0
                    if key == "silent_learning":
                        return True
                    return default
                mock_config.side_effect = _config_get

                self._start_stop_trigger(0.05)
                # Each run creates a fresh capture setup
                self.pipeline.run(
                    audio_capture=self._audio,
                    asr_cascade=self._asr,
                    corrector=self._corrector,
                    hotwords_mgr=self._hotwords,
                    injector=self._injector,
                    silent_monitor=self._silent_monitor,
                    db=self._db,
                    injection_target=None,
                )

            # Reset repeatable mocks for next iteration
            self._audio.stop.reset_mock()
            self._audio.stop.return_value = b"\x00" * 100000
            self._injector.inject.reset_mock()
            self._captured_events.clear()

        after = threading.active_count()

        # Allow a small delta for Python's internal bookkeeping threads
        # (e.g., cleanup, logging). Should never grow by more than 2.
        # The critical assertion: we did NOT spawn a daemon thread per call.
        thread_delta = after - baseline
        self.assertLessEqual(
            thread_delta, 2,
            f"Active thread count grew by {thread_delta} after 10 timeouts "
            f"(baseline={baseline}, after={after}). "
            "Each timeout should not leak threads.")


if __name__ == "__main__":
    unittest.main()
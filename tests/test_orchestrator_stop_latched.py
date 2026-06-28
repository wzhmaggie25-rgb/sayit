"""Orchestrator stop_request_latched tests.

Verifies the stop_request_latched contract from ROUND9_LONG_TASK.md §Phase 4:

  - hook and fallback race: first stop request wins
  - subsequent stop requests are no-ops
  - RECORDING_STOPPING emitted exactly once per session
  - latch resets on next recording start

Test approach
-------------
We create the orchestrator with all infrastructure components mocked, then
drive _on_hotkey_stop, _fallback_stop, and _on_hotkey_start directly.
"""
from __future__ import annotations
import threading
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from application.eventbus import Events
from domain.models import RecordingState


class StopRequestLatchedTests(unittest.TestCase):
    """Test suite for orchestrator stop_request_latched."""

    def setUp(self):
        # Patch ALL infrastructure imports used by SayitOrchestrator
        # so no real hardware or filesystem is touched.
        self._stack = []

        def _patch_module(modname):
            p = patch(modname, autospec=False)
            m = p.start()
            self._stack.append(p)
            return m

        # Patch every infrastructure class used in __init__
        _patch_module('application.orchestrator.ConfigStore')
        _patch_module('application.orchestrator.Database')
        _patch_module('application.orchestrator.AudioCapture')
        _patch_module('application.orchestrator.AsrCascade')
        _patch_module('application.orchestrator.Corrector')
        _patch_module('application.orchestrator.Injector')
        _patch_module('application.orchestrator.SilentMonitor')
        _patch_module('application.orchestrator.HotwordsManager')
        _patch_module('application.orchestrator.KeyboardHelperDll')

        # Prevent pipeline threads from actually starting
        self._orig_thread = threading.Thread
        _patch_module('application.orchestrator.RAltStopWatcher')
        p_thread = patch.object(threading, 'Thread',
                                side_effect=self._fake_thread)
        p_thread.start()
        self._stack.append(p_thread)

        from application.orchestrator import SayitOrchestrator
        self.orch = SayitOrchestrator()

        # Drop the real eventbus and use a mock to track emit calls
        self.orch._eb = MagicMock()
        self.orch._eb.emit = MagicMock()

        # Set up a fake pipeline that looks like an active capture
        self._pipeline = MagicMock()
        self._pipeline.state = RecordingState.CAPTURING
        self._pipeline.is_idle.return_value = False

        # Manually set orchestrator state to simulate an active pipeline
        self.orch._pipeline = self._pipeline
        self.orch._pipeline_active = True
        self.orch._pipeline_thread = None
        self.orch._stop_request_latched = False
        self.orch._stop_watcher = None

    def tearDown(self):
        for p in reversed(self._stack):
            try:
                p.stop()
            except Exception:
                pass

    def _fake_thread(self, *args, **kwargs):
        """Create a no-op thread that never starts."""
        t = self._orig_thread(*args, **kwargs)
        t.start = MagicMock()  # prevent thread from actually running
        return t

    def _recording_stopping_count(self) -> int:
        """Count how many times RECORDING_STOPPING was emitted."""
        return sum(
            1 for call in self.orch._eb.emit.call_args_list
            if call[0][0] == Events.RECORDING_STOPPING
        )

    # ── 1: latch lifecycle ──────────────────────────────────────

    def test_stop_latched_starts_false(self):
        """stop_request_latched is False after construction."""
        self.assertFalse(self.orch._stop_request_latched)

    def test_first_stop_sets_latched(self):
        """First _on_hotkey_stop sets stop_request_latched and returns True."""
        result = self.orch._on_hotkey_stop()
        self.assertTrue(result)
        self.assertTrue(self.orch._stop_request_latched)

    def test_second_stop_is_noop(self):
        """Second _on_hotkey_stop sees latched=True and returns False."""
        self.orch._on_hotkey_stop()       # first — succeeds
        result = self.orch._on_hotkey_stop()  # second — should be no-op
        self.assertFalse(result)

    def test_fallback_after_stop_is_noop(self):
        """_fallback_stop after _on_hotkey_stop is no-op (latch already set)."""
        self.orch._on_hotkey_stop()
        self.orch._fallback_stop()
        self.assertEqual(self._recording_stopping_count(), 1,
                         "RECORDING_STOPPING must be emitted exactly once")

    def test_stop_after_fallback_is_noop(self):
        """_on_hotkey_stop after _fallback_stop is no-op."""
        self.orch._fallback_stop()
        self.assertTrue(self.orch._stop_request_latched)
        result = self.orch._on_hotkey_stop()
        self.assertFalse(result)
        self.assertEqual(self._recording_stopping_count(), 1,
                         "RECORDING_STOPPING must be emitted exactly once")

    def test_latched_resets_on_next_start(self):
        """stop_request_latched resets to False when _on_hotkey_start runs."""
        self.orch._on_hotkey_stop()
        self.assertTrue(self.orch._stop_request_latched)
        self.orch._on_hotkey_start()
        self.assertFalse(self.orch._stop_request_latched,
                         "latch must reset on next recording start")

    # ── 2: RECORDING_STOPPING emission ──────────────────────────

    def test_recording_stopping_emitted_once(self):
        """RECORDING_STOPPING fires exactly once despite multiple stop calls."""
        self.orch._on_hotkey_stop()       # 1st — fires ACK
        self.orch._on_hotkey_stop()       # 2nd — no-op
        self.orch._fallback_stop()        # 3rd — no-op
        self.assertEqual(self._recording_stopping_count(), 1)

    def test_recording_stopping_emitted_by_fallback_first(self):
        """RECORDING_STOPPING fires when _fallback_stop wins the race."""
        self.orch._fallback_stop()        # fires ACK
        self.orch._on_hotkey_stop()       # no-op
        self.assertEqual(self._recording_stopping_count(), 1)

    # ── 3: Edge cases ───────────────────────────────────────────

    def test_no_pipeline_stop_does_not_latch(self):
        """_on_hotkey_stop with no active pipeline does NOT set latch."""
        self.orch._pipeline = None
        self.orch._pipeline_active = False
        result = self.orch._on_hotkey_stop()
        self.assertFalse(result)
        self.assertFalse(self.orch._stop_request_latched)

    def test_stop_already_after_capturing_no_latch(self):
        """_on_hotkey_stop when pipeline past CAPTURING does NOT set latch."""
        self.orch._pipeline.state = RecordingState.TRANSCRIBING
        result = self.orch._on_hotkey_stop()
        self.assertFalse(result)
        self.assertFalse(self.orch._stop_request_latched,
                         "latch must NOT be set when state is past CAPTURING")


if __name__ == "__main__":
    unittest.main()
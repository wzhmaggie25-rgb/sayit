"""RAltStopWatcher fallback tests.

Verifies the fallback contract from CURRENT_TASK.md §B3:

  When a physical second RAlt press is NOT processed by the WH_KEYBOARD_LL hook
  (hook miss), the RAltStopWatcher polling loop must detect the complete
  down→up cycle via GetAsyncKeyState and fire a fallback stop callback.

Test approach
-------------
All tests use the watcher's test-injection flags (_test_ralt_pressed and
_test_emitted_override) to simulate physical key state without touching
real hardware. This allows deterministic verification of the fallback
decision logic without driving real Windows input.
"""
from __future__ import annotations
import threading
import time
import unittest
from unittest.mock import patch

from infrastructure.ralt_stop_watcher import RAltStopWatcher


class RAltStopWatcherTests(unittest.TestCase):
    """Test suite for RAltStopWatcher fallback mechanism."""

    def setUp(self):
        self.fallback_calls = []

    def _fake_fallback(self):
        self.fallback_calls.append(True)

    def _make_watcher(self, helper=None):
        return RAltStopWatcher(self._fake_fallback, helper)

    # ── 1: arm / disarm lifecycle ──────────────────────────────────

    def test_arm_disarm_no_leak(self):
        """arm() creates a daemon thread, disarm() joins it cleanly."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        self.assertFalse(w.is_armed)

        w.arm(total_emitted=0)
        self.assertTrue(w.is_armed)
        self.assertIsNotNone(w._thread)
        self.assertTrue(w._thread.is_alive())
        self.assertTrue(w._thread.daemon)

        w.disarm()
        self.assertFalse(w.is_armed)
        self.assertIsNone(w._thread)

    def test_disarm_not_armed_no_error(self):
        """disarm() on a never-armed watcher is a no-op."""
        w = self._make_watcher()
        try:
            w.disarm()
        except Exception as e:
            self.fail(f"disarm on unarmed watcher raised: {e}")
        self.assertFalse(w.is_armed)

    def test_double_disarm_no_error(self):
        """disarm() called twice does not raise."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w.arm(total_emitted=0)
        w.disarm()
        try:
            w.disarm()
        except Exception as e:
            self.fail(f"second disarm raised: {e}")
        self.assertFalse(w.is_armed)

    def test_arm_after_disarm_creates_new_thread(self):
        """Watcher can be re-armed after disarm — fresh thread each time."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 0

        w.arm(total_emitted=0)
        thread1 = w._thread
        time.sleep(0.03)
        w.disarm()

        w.arm(total_emitted=0)
        thread2 = w._thread
        self.assertIsNotNone(thread2)
        self.assertIsNot(thread1, thread2,
                         "re-arm should create a fresh thread")
        w.disarm()

    # ── 2: Hook miss → fallback fires ──────────────────────────────

    def test_hook_miss_fires_fallback(self):
        """When emitted count stays same during RAlt cycle, fallback IS called."""
        w = self._make_watcher()
        w._test_ralt_pressed = False    # Phase 1: RAlt already released
        w._test_emitted_override = 0     # initial emitted
        w.arm(total_emitted=0)
        time.sleep(0.07)                 # wait for Phase 1 + 50ms stabilization

        # Simulate RAlt down with NO hook processing (emitted unchanged)
        w._test_ralt_pressed = True
        time.sleep(0.03)

        # Simulate RAlt up → cycle complete
        w._test_ralt_pressed = False
        time.sleep(0.05)                 # wait for detection

        self.assertEqual(w.fallback_stops, 1,
                         "fallback must fire when hook missed the event")
        self.assertEqual(w.hook_misses, 1)
        self.assertEqual(len(self.fallback_calls), 1,
                         "fallback callback must have been invoked")

    def test_normal_hook_does_not_fire_fallback(self):
        """When emitted count increases during RAlt cycle, fallback is NOT called."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 0
        w.arm(total_emitted=0)
        time.sleep(0.07)

        # Simulate RAlt down → hook ALSO processes it → emitted increases
        w._test_emitted_override = 1    # hook processed the toggle
        w._test_ralt_pressed = True
        time.sleep(0.03)

        # RAlt up → complete cycle
        w._test_ralt_pressed = False
        time.sleep(0.05)

        self.assertEqual(w.fallback_stops, 0,
                         "fallback must NOT fire when hook handled the event")
        self.assertEqual(len(self.fallback_calls), 0,
                         "fallback callback must NOT be invoked")

    def test_hook_miss_increments_counters(self):
        """hook_misses and fallback_stops counters are consistent."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 0

        # First miss
        w.arm(total_emitted=0)
        time.sleep(0.07)
        w._test_ralt_pressed = True
        time.sleep(0.03)
        w._test_ralt_pressed = False
        time.sleep(0.05)
        self.assertEqual(w.hook_misses, 1)
        self.assertEqual(w.fallback_stops, 1)

        # Second arm → another miss
        w.arm(total_emitted=1)
        time.sleep(0.07)
        w._test_ralt_pressed = True
        time.sleep(0.03)
        w._test_ralt_pressed = False
        time.sleep(0.05)
        self.assertEqual(w.hook_misses, 2)
        self.assertEqual(w.fallback_stops, 2)

        w.disarm()

    # ── 3: Edge cases ──────────────────────────────────────────────

    def test_disarm_while_phase1_exits_cleanly(self):
        """disarm() during Phase 1 (RAlt held) exits without fallback."""
        w = self._make_watcher()
        w._test_ralt_pressed = True     # RAlt held → Phase 1 loops
        w.arm(total_emitted=0)
        time.sleep(0.03)                 # thread is in Phase 1 loop

        w.disarm()                       # should stop the thread
        self.assertFalse(w.is_armed)
        self.assertEqual(w.fallback_stops, 0,
                         "Phase 1 disarm must not trigger fallback")
        self.assertEqual(len(self.fallback_calls), 0)

    def test_disarm_while_phase2_exits_cleanly(self):
        """disarm() during Phase 2 (waiting for down) exits without fallback."""
        w = self._make_watcher()
        w._test_ralt_pressed = False    # Phase 1 exits immediately
        w.arm(total_emitted=0)
        time.sleep(0.07)                 # now in Phase 2, waiting for down

        w.disarm()
        self.assertFalse(w.is_armed)
        self.assertEqual(w.fallback_stops, 0)

    def test_arm_without_helper_no_crash(self):
        """arm() with helper=None and emitted=-1 does not crash on cycle."""
        w = self._make_watcher(helper=None)
        w._test_ralt_pressed = False
        w.arm(total_emitted=-1)          # no emitted tracking
        time.sleep(0.07)

        w._test_ralt_pressed = True
        time.sleep(0.03)
        w._test_ralt_pressed = False
        time.sleep(0.05)

        # emitted=-1, no helper → post=-1, -1 > -1 is False → hook miss
        self.assertEqual(w.fallback_stops, 1,
                         "fallback fires when emitted is unknown")
        w.disarm()

    def test_disarm_after_auto_disarm_safe(self):
        """disarm() after watcher auto-disarmed by cycle completion is idempotent."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 0
        w.arm(total_emitted=0)
        time.sleep(0.07)

        # Complete a cycle (hook miss → auto-disarm)
        w._test_emitted_override = 0
        w._test_ralt_pressed = True
        time.sleep(0.03)
        w._test_ralt_pressed = False
        time.sleep(0.05)                # watcher auto-disarmed by _on_complete_cycle

        try:
            w.disarm()                   # safety-net disarm (like pipeline.finally)
        except Exception as e:
            self.fail(f"disarm after auto-disarm raised: {e}")

        self.assertFalse(w.is_armed)

    # ── 4: Diagnostics ─────────────────────────────────────────────

    def test_diagnostics_returns_all_counters(self):
        """diagnostics() returns all expected fields, no personal data."""
        w = self._make_watcher()
        d = w.diagnostics()
        expected_keys = {"armed", "hook_misses", "fallback_stops", "initial_emitted"}
        self.assertTrue(expected_keys.issubset(d.keys()),
                        f"diagnostics missing keys: {expected_keys - d.keys()}")
        for k in ("hook_misses", "fallback_stops", "initial_emitted"):
            self.assertIsInstance(d[k], int, f"{k} must be int")


if __name__ == "__main__":
    unittest.main()
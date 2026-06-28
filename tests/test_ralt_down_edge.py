"""RAltStopWatcher down-edge detection tests.

Verifies the watcher improvement from ROUND9_LONG_TASK.md §Phase 4:

  - Watcher fires fallback stop on RAlt down edge (not full down→up)
  - Still tracks up edge for diagnostics
  - Does NOT fire on the initial recording-start RAlt press
  - Does NOT double-fire with hook and fallback

Test approach
-------------
Same as test_ralt_stop_watcher.py: use _test_ralt_pressed and
_test_emitted_override to simulate key state deterministically.
"""
from __future__ import annotations
import time
import unittest

from infrastructure.ralt_stop_watcher import RAltStopWatcher


class RAltStopWatcherDownEdgeTests(unittest.TestCase):
    """Test down-edge detection in RAltStopWatcher."""

    def setUp(self):
        self.fallback_calls = []

    def _fake_fallback(self):
        self.fallback_calls.append(True)

    def _make_watcher(self, helper=None):
        return RAltStopWatcher(self._fake_fallback, helper)

    # ── 1: Down-edge fires fallback (NEW behavior) ──────────────

    def test_down_edge_fires_fallback(self):
        """RAlt down edge alone triggers fallback stop (no need for up)."""
        w = self._make_watcher()
        w._test_ralt_pressed = False     # Phase 1: RAlt already released
        w._test_emitted_override = 0
        w.arm(total_emitted=0)
        time.sleep(0.07)                 # Phase 1 + stabilization

        # RAlt goes down — this alone should trigger fallback
        w._test_ralt_pressed = True
        time.sleep(0.05)                 # wait for detection

        self.assertEqual(w.fallback_stops, 1,
                         "fallback must fire on down edge")
        self.assertEqual(len(self.fallback_calls), 1)

    def test_down_edge_before_hook_emit_fires_fallback(self):
        """Down edge fires fallback even if hook later emits on up."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 0
        w.arm(total_emitted=0)
        time.sleep(0.07)

        # Down — watcher fires fallback after grace period
        w._test_emitted_override = 0     # hook hasn't processed yet
        w._test_ralt_pressed = True
        # Need: poll interval (~10ms) + grace period (40ms) + slack
        time.sleep(0.10)

        self.assertEqual(w.fallback_stops, 1,
                         "fallback fires on down edge after grace")

        # Later the hook processes the up — emitted increases
        w._test_emitted_override = 1
        w._test_ralt_pressed = False     # up
        time.sleep(0.05)

        # No second fallback — watcher auto-disarmed after first down edge
        self.assertEqual(w.fallback_stops, 1,
                         "no second fallback after hook processes up")

    def test_down_edge_normal_hook_does_not_fire_fallback(self):
        """If hook already emitted before down edge is detected, no fallback.

        This simulates the case where the hook processed the RAlt so fast
        that get_total_emitted increased before the watcher could observe
        the down edge.
        """
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 1     # hook already emitted
        w.arm(total_emitted=0)
        time.sleep(0.07)

        # After arm, emitted is already > initial_emitted
        # RAlt down should check emitted BEFORE deciding to fire
        w._test_ralt_pressed = True
        time.sleep(0.05)

        self.assertEqual(w.fallback_stops, 0,
                         "no fallback if emitted already increased")
        self.assertEqual(len(self.fallback_calls), 0)
        w.disarm()

    def test_down_edge_after_hook_emit_during_phase1(self):
        """If hook emitted during Phase 1 (start key), watcher disarms safely."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 1     # emitted increased already
        w.arm(total_emitted=0)
        time.sleep(0.07)

        # RAlt down — emitted already higher
        w._test_ralt_pressed = True
        time.sleep(0.05)

        self.assertEqual(w.fallback_stops, 0)
        w.disarm()

    # ── 2: Initial start key is NOT mistaken for stop ───────────

    def test_no_fire_on_start_key(self):
        """The same RAlt press that started recording does NOT fire fallback."""
        w = self._make_watcher()
        # Phase 1 waits for RAlt to release.
        # If RAlt is initially held (start key still down), Phase 1 loops.
        w._test_ralt_pressed = True     # start key still held
        w.arm(total_emitted=0)
        time.sleep(0.05)

        # RAlt still held — Phase 1 should not fire
        self.assertEqual(w.fallback_stops, 0)

        # RAlt released — Phase 1 exits, enters Phase 2
        w._test_ralt_pressed = False
        time.sleep(0.10)                # Phase 1 exits → stabilization → Phase 2

        # No fallback yet — we're just waiting for the next press
        self.assertEqual(w.fallback_stops, 0)

        w.disarm()

    # ── 3: Edge cases ───────────────────────────────────────────

    def test_down_edge_auto_disarm_stops_watching(self):
        """After down-edge detection and fallback, watcher disarms."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 0
        w.arm(total_emitted=0)
        time.sleep(0.07)

        w._test_ralt_pressed = True
        # Wait for: poll interval (~10ms) + grace period (40ms) + slack
        time.sleep(0.12)

        self.assertFalse(w.is_armed,
                         "watcher must disarm after down-edge detection")

    def test_up_edge_after_down_edge_does_not_double_fire(self):
        """Up edge after down-edge fire does NOT trigger second fallback."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 0
        w.arm(total_emitted=0)
        time.sleep(0.07)

        # Down edge fires fallback
        w._test_ralt_pressed = True
        time.sleep(0.05)
        self.assertEqual(w.fallback_stops, 1)

        # Up edge comes later
        w._test_ralt_pressed = False
        time.sleep(0.05)

        self.assertEqual(w.fallback_stops, 1)

        # Manually check disarm state
        w.disarm()
        self.assertEqual(w.fallback_stops, 1)

    def test_double_down_still_one_fire(self):
        """A single down→still down event fires exactly one fallback."""
        w = self._make_watcher()
        w._test_ralt_pressed = False
        w._test_emitted_override = 0
        w.arm(total_emitted=0)
        time.sleep(0.07)

        # Down edge
        w._test_ralt_pressed = True
        time.sleep(0.03)
        # Still down (e.g., holding the key)
        time.sleep(0.05)

        self.assertEqual(w.fallback_stops, 1,
                         "only one fallback per arm cycle even while held")
        w.disarm()


if __name__ == "__main__":
    unittest.main()
"""Tests for the single-consumer ordered dispatcher and runtime diagnostics.

These tests cover §B3 and §B4 of CURRENT_TASK.md:
  - native_emit → python_receive → orchestrator_action must be ordered
  - second toggle's action must execute BEFORE the third toggle's
  - no unbounded daemon thread per toggle
  - `helper_version` / `helper_build_id` / `dll_path` are exposed
  - diagnostic ring records only seq/timestamps/thread ids (no text)
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

os.environ.setdefault("SAYIT_TEST_MODE", "1")

from infrastructure.keyboard_helper_dll import (
    KeyboardHelperDll,
    MIN_HELPER_VERSION,
)


def _dll_ready() -> bool:
    h = KeyboardHelperDll()
    if not h.is_available:
        return False
    try:
        getattr(h.lib, "__test_trigger_toggle")
    except AttributeError:
        return False
    return True


@unittest.skipUnless(_dll_ready(),
                     "sayit_keyboard_helper.dll missing or older ABI")
class OrderedDispatcherTests(unittest.TestCase):

    def setUp(self):
        self.helper = KeyboardHelperDll()
        try:
            self.helper.uninstall()
        except Exception:
            pass

    def tearDown(self):
        try:
            self.helper.uninstall()
        except Exception:
            pass

    def test_callbacks_execute_in_arrival_order(self):
        """N back-to-back toggles produce callbacks 1..N in strict order."""
        observed = []
        lock = threading.Lock()

        def cb():
            with lock:
                # Snapshot the dispatch counter at the moment we are
                # invoked. Because the consumer is single-threaded, these
                # numbers must be strictly monotonic.
                observed.append(self.helper.diagnostics()["dispatched"])

        self.assertTrue(self.helper.install(cb))
        N = 200
        for _ in range(N):
            self.helper.test_trigger_toggle()
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            with lock:
                if len(observed) == N:
                    break
            time.sleep(0.01)
        with lock:
            self.assertEqual(len(observed), N)
            self.assertEqual(observed, sorted(observed))
            self.assertEqual(observed[0], 1)
            self.assertEqual(observed[-1], N)

    def test_consumer_thread_persists_no_new_threads_per_toggle(self):
        """Each toggle MUST NOT spawn a new daemon thread.

        We snapshot threading.active_count() before and after a burst of
        toggles. The consumer thread is created once at install time, so
        the count must stay within a tight bound regardless of toggle
        count. (Pipeline threads spawned by the business callback are a
        separate concern — we use a no-op callback here.)
        """
        # No-op callback: business work is none, so no pipeline threads.
        self.assertTrue(self.helper.install(lambda: None))
        time.sleep(0.05)
        baseline = threading.active_count()
        for _ in range(500):
            self.helper.test_trigger_toggle()
        # Drain
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self.helper.diagnostics()["dispatched"] >= 500:
                break
            time.sleep(0.01)
        peak = threading.active_count()
        # Allow a couple of slack threads for jitter; the important
        # invariant is that we do NOT see ~500 extra daemon threads.
        self.assertLessEqual(peak - baseline, 3,
                             f"thread count grew by {peak - baseline} for "
                             f"500 toggles — per-toggle thread leak?")

    def test_consumer_recovers_from_callback_exceptions(self):
        """An exception in one callback must not stop later toggles."""
        observed = []
        raised = [0]

        def cb():
            observed.append(1)
            if raised[0] < 2:
                raised[0] += 1
                raise RuntimeError("synthetic")

        self.assertTrue(self.helper.install(cb))
        for _ in range(5):
            self.helper.test_trigger_toggle()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if len(observed) == 5:
                break
            time.sleep(0.01)
        self.assertEqual(len(observed), 5,
                         "consumer stopped after callback raised")

    def test_recent_events_redacts_text(self):
        """Diagnostic ring contains only sequence/timestamp/thread ids."""
        self.assertTrue(self.helper.install(lambda: None))
        for _ in range(3):
            self.helper.test_trigger_toggle()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            events = self.helper.recent_events()
            if len(events) >= 3:
                break
            time.sleep(0.02)
        events = self.helper.recent_events()
        self.assertGreaterEqual(len(events), 3)
        # The set of keys MUST be exactly this — nothing else (no user
        # text leaks into diagnostics).
        expected_keys = {
            "seq", "native_seq", "recv_ms", "dispatch_ms",
            "latency_ms", "thread_id",
        }
        for ev in events:
            self.assertEqual(set(ev.keys()), expected_keys,
                             f"unexpected diagnostic keys: {set(ev.keys())}")

    def test_recent_events_is_bounded(self):
        """Ring is bounded to its capacity (cannot grow without limit)."""
        from infrastructure.keyboard_helper_dll import DIAG_RING_SIZE
        self.assertTrue(self.helper.install(lambda: None))
        N = DIAG_RING_SIZE * 2 + 7
        for _ in range(N):
            self.helper.test_trigger_toggle()
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self.helper.diagnostics()["dispatched"] >= N:
                break
            time.sleep(0.01)
        # Asking for a huge limit must still cap at DIAG_RING_SIZE.
        events = self.helper.recent_events(limit=10000)
        self.assertLessEqual(len(events), DIAG_RING_SIZE)


@unittest.skipUnless(_dll_ready(),
                     "sayit_keyboard_helper.dll missing or older ABI")
class HelperIdentityTests(unittest.TestCase):
    """Runtime identity of the loaded DLL is queryable from Python (§B1)."""

    def setUp(self):
        self.helper = KeyboardHelperDll()

    def test_helper_version_meets_minimum(self):
        v = self.helper.helper_version()
        self.assertGreaterEqual(v, MIN_HELPER_VERSION,
                                f"helper_version {v} < required {MIN_HELPER_VERSION}")

    def test_helper_build_id_is_nonempty(self):
        b = self.helper.helper_build_id()
        self.assertTrue(b, "helper_build_id is empty")
        # Build id is a short ASCII tag — must NOT contain personal paths.
        self.assertNotIn(os.sep, b)
        self.assertNotIn("/", b)

    def test_dll_path_is_realpath_and_exists(self):
        path = self.helper.dll_path
        self.assertTrue(path)
        self.assertTrue(os.path.isabs(path))
        self.assertTrue(os.path.exists(path))
        # Sanity: name must be the keyboard helper, not another DLL.
        self.assertIn("sayit_keyboard_helper", os.path.basename(path).lower())

    def test_diagnostics_snapshot_shape(self):
        diag = self.helper.diagnostics()
        # Must contain the documented keys.
        for key in (
            "dll_path", "helper_version", "helper_build_id", "pid",
            "is_installed", "total_emitted", "total_consumed", "pending",
            "dispatched", "queue_depth",
        ):
            self.assertIn(key, diag)


if __name__ == "__main__":
    unittest.main()

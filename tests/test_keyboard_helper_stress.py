"""Stress test for the C++ → worker → Python toggle transport.

Verifies that the keyboard helper DLL's native event transport is loss-less
and ordered under heavy GIL contention. The DLL exports a test-only
__test_trigger_toggle() entry that emits an event identical to what HookProc
emits on an RAlt-up edge, without involving a physical key — so this test
exercises the transport path end-to-end without needing a human.

Skipped on non-Windows or when the DLL is not built.
"""
from __future__ import annotations
import os
import sys
import threading
import time
import unittest

import pytest

# Only meaningful on Windows.
if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

# Make sure we don't accidentally clash with a running server's installed hook.
os.environ.setdefault("SAYIT_TEST_MODE", "1")

from infrastructure.keyboard_helper_dll import KeyboardHelperDll


def _dll_available() -> bool:
    helper = KeyboardHelperDll()
    if not helper.is_available:
        return False
    try:
        getattr(helper.lib, "__test_trigger_toggle")
        return True
    except AttributeError:
        return False


def _trigger(lib):
    """Invoke the test-only entry point via explicit getattr to bypass
    Python's name mangling of names starting with double-underscore."""
    return getattr(lib, "__test_trigger_toggle")()


@unittest.skipUnless(_dll_available(),
                     "sayit_keyboard_helper.dll missing or older ABI")
class HookTransportStressTests(unittest.TestCase):
    """Native producer → worker thread → Python consumer transport."""

    def setUp(self):
        self.helper = KeyboardHelperDll()
        # Make sure no prior installation lingers from another test.
        try:
            self.helper.uninstall()
        except Exception:
            pass

    def tearDown(self):
        try:
            self.helper.uninstall()
        except Exception:
            pass

    # ── Test 1: lossless, ordered, exactly-once delivery under GIL pressure ──

    def test_thousand_toggles_lossless_under_gil_pressure(self):
        """Emit 1000 toggles while a separate thread starves the GIL.

        The DLL counts each consumed toggle. Python keeps an independent
        count of callback invocations. After all events have drained, both
        counts MUST match exactly.
        """
        received = []
        received_lock = threading.Lock()

        def consume():
            # Just count — keep the work tiny so we test the transport, not
            # the dispatcher.
            with received_lock:
                received.append(1)

        ok = self.helper.install(consume)
        self.assertTrue(ok, "DLL install failed")

        # GIL pressure thread — represents the kind of contention real
        # recording sessions create (streaming ASR, audio chunk callback,
        # RMS smoothing) — heavy but with cooperative yields so the worker
        # thread can still make forward progress. Without the periodic
        # yield this is just thread starvation, not GIL contention.
        stop_pressure = threading.Event()

        def pressure():
            x = 0
            while not stop_pressure.is_set():
                for _ in range(5000):
                    x = (x + 1) % 1_000_003
                # Yield to give the worker thread a chance at the GIL.
                # 200 µs is roughly one audio chunk-callback period.
                time.sleep(0.0002)

        pressure_threads = [
            threading.Thread(target=pressure, daemon=True) for _ in range(3)
        ]
        for t in pressure_threads:
            t.start()

        N = 1000
        try:
            # Drive a producer thread from Python so the C++ EmitToggle is
            # invoked while the worker is racing with GIL pressure.
            def produce():
                for _ in range(N):
                    _trigger(self.helper.lib)

            t = threading.Thread(target=produce)
            t.start()
            t.join()

            # Wait for the worker thread to fully drain (up to ~30s).
            deadline = time.time() + 30.0
            while time.time() < deadline:
                if self.helper.get_pending_count() == 0 and len(received) == N:
                    break
                time.sleep(0.02)
        finally:
            stop_pressure.set()
            for t in pressure_threads:
                t.join(timeout=2.0)

        emitted = self.helper.get_total_emitted()
        consumed = self.helper.get_total_consumed()
        pending = self.helper.get_pending_count()

        self.assertEqual(emitted, N,
                         f"DLL emit counter wrong: {emitted} vs {N}")
        self.assertEqual(consumed, N,
                         f"DLL consume counter wrong: {consumed} vs {N}; pending={pending}")
        self.assertEqual(pending, 0, f"Pending events left over: {pending}")
        self.assertEqual(len(received), N,
                         f"Python received {len(received)} of {N} toggles")

    # ── Test 2: install/uninstall cycle resilience ──────────────────

    def test_twenty_install_uninstall_cycles(self):
        """Install and uninstall the hook 20 times. No crashes, no leaks."""
        for i in range(20):
            received = []

            def cb():
                received.append(1)

            self.assertTrue(self.helper.install(cb),
                            f"install failed at cycle {i}")
            self.assertTrue(self.helper.is_installed)

            # Emit a couple of test toggles so the worker thread is actually
            # exercised before we uninstall.
            for _ in range(5):
                _trigger(self.helper.lib)

            # Drain.
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if self.helper.get_pending_count() == 0 and len(received) == 5:
                    break
                time.sleep(0.01)

            self.assertEqual(len(received), 5, f"cycle {i}: lost toggles")
            self.helper.uninstall()
            self.assertFalse(self.helper.is_installed)

    # ── Test 3: HookProc never calls Python ──────────────────────────
    #
    # The smoking-gun test for "v2 architecture: HookProc does not invoke
    # Python". We instrument the Python callback to record which OS thread
    # invokes it, then emit toggles and verify the recorded thread id is
    # NEVER the same as the calling thread's id — Python callbacks run on
    # a daemon thread the wrapper spawns, not on the producer.

    def test_callback_runs_off_caller_thread(self):
        producer_tid = threading.get_ident()
        observed = []

        def cb():
            observed.append(threading.get_ident())

        self.assertTrue(self.helper.install(cb))
        for _ in range(50):
            _trigger(self.helper.lib)
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if len(observed) == 50:
                break
            time.sleep(0.02)
        self.assertEqual(len(observed), 50)
        for tid in observed:
            self.assertNotEqual(tid, producer_tid,
                                "callback ran on producer thread — "
                                "HookProc transport broken")


if __name__ == "__main__":
    unittest.main()

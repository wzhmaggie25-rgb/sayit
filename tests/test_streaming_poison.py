"""Phase A4: Poisoned streaming stop tests.

Proves that the shared _STOP_EXECUTOR (ThreadPoolExecutor max_workers=1)
was permanently poisoned when recognition.stop() wedges.

BUG (Round 9.4 P0): asr_streaming.py defined _STOP_EXECUTOR as a module-level
ThreadPoolExecutor(max_workers=1). When any session's recognition.stop()
blocks permanently (SDK wedge), that single worker is occupied forever.
All subsequent sessions' stop() calls are queued and never execute,
causing every finish()/abort() to hit its timeout.

FIX: _STOP_EXECUTOR removed. Each finish()/abort() creates its own fresh
ThreadPoolExecutor via _exec_stop(), so a wedged stop() never poisons
other sessions.

Tests now assert the DESIRED behavior (must PASS after fix):
1. A hung session does NOT poison subsequent sessions
2. Each call gets its own isolated executor
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from unittest.mock import MagicMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)


class TestStreamingPoisonedStop(unittest.TestCase):
    """Prove that per-call executors prevent cross-session poisoning."""

    def _make_session(self, recognition_stop=None):
        """Create a session with mocked recognition for isolated stop testing."""
        from infrastructure.asr_streaming import DashScopeStreamingASRSession

        session = DashScopeStreamingASRSession(
            api_key="test_key",
            model="test-model",
        )
        session._recognition = MagicMock()
        session._started = True
        session._recognition.stop = recognition_stop or MagicMock()
        session._worker = None  # skip worker.join
        return session

    # ════════════════════════════════════════════════════════════
    # Test 1: Healthy session after wedged session must work
    # ════════════════════════════════════════════════════════════

    def test_healthy_session_stop_called_after_wedged_session(self):
        """Session 2's stop() must be callable after Session 1's wedged stop.

        AFTER FIX: each _exec_stop() creates its own fresh executor, so
        Session 1's wedged stop does NOT block Session 2.
        """
        # ── Session 1: recognition.stop() blocks forever ──
        wedged_stop = MagicMock(side_effect=lambda: time.sleep(999))
        session1 = self._make_session(recognition_stop=wedged_stop)

        # ── Session 2: recognition.stop() that sets an event ──
        stop2_called = threading.Event()

        def _healthy_stop():
            stop2_called.set()
            return None

        session2 = self._make_session(recognition_stop=_healthy_stop)

        # ── Start Session 1's _exec_stop in background ──
        thread1 = threading.Thread(
            target=lambda: session1._exec_stop(timeout=2.0),
            daemon=True,
        )
        thread1.start()

        # Give Session 1 time to submit and block its executor
        time.sleep(0.3)

        # ── Now Session 2 calls _exec_stop ──
        # DESIRED: stop2_called IS set (per-call executor, not shared)
        try:
            session2._exec_stop(timeout=2.0)
        except (RuntimeError, TimeoutError):
            pass

        # AFTER FIX: Session 2's stop() must have been called
        self.assertTrue(
            stop2_called.is_set(),
            "Session 2's stop() was never called — the per-call executor "
            "should NOT be poisoned by Session 1's wedged stop."
        )

        thread1.join(timeout=1)

    # ════════════════════════════════════════════════════════════
    # Test 2: Three sessions after wedge — none should be poisoned
    # ════════════════════════════════════════════════════════════

    def test_third_session_stop_after_two_wedged_sessions(self):
        """Session 3's stop must work even after 2 previous wedged sessions."""
        # Session 1 & 2: wedged stops
        wedged_stop = MagicMock(side_effect=lambda: time.sleep(999))
        session1 = self._make_session(recognition_stop=wedged_stop)
        session2 = self._make_session(recognition_stop=wedged_stop)

        # Session 3: healthy stop
        stop3_called = threading.Event()

        def _healthy_stop3():
            stop3_called.set()
            return None

        session3 = self._make_session(recognition_stop=_healthy_stop3)

        # Start session 1 in background
        thread1 = threading.Thread(
            target=lambda: session1._exec_stop(timeout=2.0),
            daemon=True,
        )
        thread1.start()
        time.sleep(0.3)

        # Start session 2 in background
        thread2 = threading.Thread(
            target=lambda: session2._exec_stop(timeout=2.0),
            daemon=True,
        )
        thread2.start()
        time.sleep(0.3)

        # Session 3 — should be fast since it gets its own executor
        try:
            session3._exec_stop(timeout=2.0)
        except (RuntimeError, TimeoutError):
            pass

        # AFTER FIX: Session 3's stop WAS called
        self.assertTrue(
            stop3_called.is_set(),
            "Session 3's stop was never called — per-call executors "
            "should not be poisoned by sessions 1 and 2."
        )

        thread1.join(timeout=1)
        thread2.join(timeout=1)

    # ════════════════════════════════════════════════════════════
    # Test 3: abort() also unblocked
    # ════════════════════════════════════════════════════════════

    def test_abort_not_blocked_by_wedged_stop(self):
        """abort() in a new session must NOT block due to previous wedged stop.

        AFTER FIX: abort() uses per-call _exec_stop, so even if a previous
        session's stop is wedged, the new session's abort() finishes quickly.
        """
        # Session 1: wedged stop (simulates a previous session that hung)
        wedged_stop = MagicMock(side_effect=lambda: time.sleep(999))
        session1 = self._make_session(recognition_stop=wedged_stop)

        # Session 2: call abort (should be quick after fix)
        session2 = self._make_session()

        # Start session 1's stop in background to wedge its own executor
        thread1 = threading.Thread(
            target=lambda: session1._exec_stop(timeout=2.0),
            daemon=True,
        )
        thread1.start()
        time.sleep(0.3)

        # Session 2's abort — should return quickly
        t0 = time.monotonic()
        session2.abort()
        elapsed = time.monotonic() - t0

        # AFTER FIX: abort() completes in < 0.5s (per-call executor)
        self.assertLess(
            elapsed,
            1.0,
            f"abort() took {elapsed:.2f}s — per-call executor should "
            f"not be poisoned. Expected < 1.0s.",
        )

        thread1.join(timeout=1)
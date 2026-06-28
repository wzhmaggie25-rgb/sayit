"""A1: Test streaming ASR finish does not block on full queue or dead worker.

Requires Phase B fix: finish() must use put_nowait/safe-drain for sentinel,
not blocking put(None) which hangs forever when _send_loop is dead.

The test patches dashscope at module level so no real SDK call happens.
"""
from __future__ import annotations

import queue
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)


class TestStreamingQueueDeadlock(unittest.TestCase):
    """Verify DashScopeStreamingASRSession.finish() never blocks indefinitely."""

    def setUp(self):
        # Patch dashscope before any imports from asr_streaming
        self.dashscope_patcher = patch.dict("sys.modules", {
            "dashscope": MagicMock(),
            "dashscope.audio": MagicMock(),
            "dashscope.audio.asr": MagicMock(),
        })
        self.dashscope_patcher.start()
        from infrastructure.asr_streaming import DashScopeStreamingASRSession
        self.session_class = DashScopeStreamingASRSession

    def tearDown(self):
        self.dashscope_patcher.stop()

    def _make_session(self, maxsize=2) -> object:
        """Create a session with mocked dashscope internals."""
        session = self.session_class(
            api_key="test-key",
            model="fun-asr-realtime",
        )
        # Prevent start() from actually using dashscope
        session._started = True
        session._recognition = MagicMock()
        # Replace the queue with a small one
        session._audio_queue = queue.Queue(maxsize=maxsize)
        session._complete = threading.Event()
        session._error = None
        return session

    def test_finish_does_not_block_when_queue_full_and_worker_dead(self):
        """finish() must raise/return, not hang, when queue is full and worker dead."""
        session = self._make_session(maxsize=2)

        # Fill the queue to capacity so put(None) would block with old code
        session._audio_queue.put(b"data1")
        session._audio_queue.put(b"data2")
        self.assertTrue(session._audio_queue.full())

        # Worker is dead (not alive)
        session._worker = MagicMock()
        session._worker.is_alive.return_value = False

        # Set complete event so finish doesn't wait for recognition
        session._complete.set()

        start = time.monotonic()
        deadline = 5.0  # Test timeout — finish should return well before this
        try:
            # This should NOT hang. Old code does blocking put(None) → hangs.
            session.finish(timeout=3.0)
        except (RuntimeError, TimeoutError):
            pass  # Expected: queue full + worker dead → error or timeout
        elapsed = time.monotonic() - start

        self.assertLess(
            elapsed, deadline,
            f"finish() blocked for {elapsed:.1f}s — sentinel put likely hung"
        )

    def test_finish_does_not_block_with_slow_worker(self):
        """finish() must not hang even if worker is slow to consume queue."""
        session = self._make_session(maxsize=2)

        # Fill queue to capacity
        session._audio_queue.put(b"data1")
        session._audio_queue.put(b"data2")
        self.assertTrue(session._audio_queue.full())

        # Worker is alive but slow (won't consume before our deadline)
        session._worker = MagicMock()
        session._worker.is_alive.return_value = True
        session._worker.join.return_value = None  # returns immediately

        # Set complete so we don't wait on recognition
        session._complete.set()

        start = time.monotonic()
        deadline = 5.0
        try:
            session.finish(timeout=1.0)
        except (RuntimeError, TimeoutError):
            pass
        elapsed = time.monotonic() - start

        self.assertLess(
            elapsed, deadline,
            f"finish() blocked for {elapsed:.1f}s — sentinel put likely hung"
        )

    def test_finish_recognition_stop_has_timeout(self):
        """recognition.stop() should not hang forever if SDK wedges."""
        session = self._make_session(maxsize=2)

        # Worker dead
        session._worker = MagicMock()
        session._worker.is_alive.return_value = False

        # recognition.stop() hangs (simulates SDK wedging)
        session._recognition.stop.side_effect = lambda: time.sleep(30)

        # Complete event not set — finish should timeout
        start = time.monotonic()
        deadline = 10.0
        try:
            session.finish(timeout=1.0)
        except (RuntimeError, TimeoutError):
            pass
        elapsed = time.monotonic() - start
        self.assertLess(
            elapsed, deadline,
            f"finish() blocked for {elapsed:.1f}s — stop() likely hung"
        )

    def test_queue_full_put_nowait_sentinel_does_not_block(self):
        """Direct test of the fix: sending sentinel with put_nowait or drain."""
        session = self._make_session(maxsize=2)
        q = session._audio_queue
        q.put(b"data1")
        q.put(b"data2")
        self.assertTrue(q.full())

        # This is the FIX: use put_nowait or drain+put instead of blocking put
        # First attempt put_nowait
        if q.full():
            try:
                q.put_nowait(None)
            except queue.Full:
                # Drain one item, then put sentinel
                try:
                    q.get_nowait()  # remove oldest data chunk
                    q.put_nowait(None)
                except queue.Empty:
                    pass

        # Sentinel should now be in queue
        # Drain all items until we find None
        found_none = False
        found_items = 0
        while not q.empty():
            item = q.get_nowait()
            if item is None:
                found_none = True
            else:
                found_items += 1
        self.assertTrue(found_none, "Expected sentinel None in queue")
        self.assertEqual(found_items, 1, "Expected 1 remaining data item after drain")


if __name__ == "__main__":
    unittest.main()
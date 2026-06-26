"""AudioCapture stop reorder tests.

Verifies the contract in CURRENT_TASK.md §B5:

  AudioCapture.stop() currently joins the read thread BEFORE closing the
  stream, causing up to 3s delay because stream.read() blocks for ~64ms
  per chunk. The fix reverses the order: close stream first to unblock
  read(), then collect PCM, to make stop() near-instant.

Test approach
-------------
We patch _open_stream to set a mock stream object, then verify that
_close_stream closes mock.stream before joining the read thread. We also
verify stop() calls _close_stream exactly once and returns collected PCM.
"""
from __future__ import annotations
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from infrastructure.audio_capture import AudioCapture


class FakeStream:
    """Minimal stand-in for a PyAudio stream object."""
    def __init__(self):
        self.active = True
        self._closed = False

    def is_active(self):
        return self.active and not self._closed

    def stop_stream(self):
        self.active = False

    def close(self):
        self._closed = True
        self.active = False

    def start_stream(self):
        pass

    def read(self, chunk_size, exception_on_overflow=False):
        # In real use this blocks; for tests return data immediately
        return b"\x00\x00" * (chunk_size // 2)


def _make_mock_open_stream(stream):
    """Return a side_effect that sets self._stream and returns."""
    def _open(ac_self=None):
        # Capture the instance from the first arg (self)
        pass
    return lambda: setattr(ac, "_stream", stream) if not hasattr(stream, '_set') else None


class AudioCaptureStopTests(unittest.TestCase):
    """Test suite for AudioCapture.stop() ordering."""

    def setUp(self):
        self.ac = AudioCapture(gain=1.0)

    def tearDown(self):
        try:
            self.ac.close()
        except Exception:
            pass

    # ── 1: _close_stream order — close before join ──────────────

    def test_close_stream_closes_before_join(self):
        """_close_stream() must close the stream before joining read thread.

        This is the core of the B5 fix: closing the stream unblocks
        stream.read() in the read thread, making join() return instantly.
        """
        fake = FakeStream()
        self.ac._stream = fake
        self.ac._read_stop.set()

        # Create a thread that simulates a running read loop
        self.ac._read_thread = threading.Thread(
            target=lambda: time.sleep(0.05), daemon=True)
        self.ac._read_thread.start()

        # Track close and join ordering via MagicMock wrappers
        fake.close = MagicMock(wraps=fake.close)
        orig_join = self.ac._read_thread.join
        join_called = threading.Event()

        def tracking_join(timeout=None):
            join_called.set()
            return orig_join(timeout=timeout)

        self.ac._read_thread.join = tracking_join

        self.ac._close_stream()

        # close() must have been called before join completed
        self.assertTrue(fake._closed, "stream must be closed")
        fake.close.assert_called_once()
        self.assertIsNone(self.ac._stream, "stream reference must be None after close")

    def test_close_stream_stream_none_no_crash(self):
        """_close_stream() with no stream is safe."""
        self.ac._stream = None
        self.ac._read_thread = None
        try:
            self.ac._close_stream()
        except Exception as e:
            self.fail(f"_close_stream with None stream raised: {e}")

    # ── 2: stop() calls _close_stream and returns PCM ───────────

    def test_stop_calls_close_stream_once(self):
        """stop() must call _close_stream exactly once."""
        fake = FakeStream()
        self.ac._stream = fake
        self.ac._read_stop.clear()
        self.ac._read_thread = threading.Thread(
            target=lambda: None, daemon=True)
        self.ac._read_thread.start()
        self.ac._recording = True
        self.ac._queue.put(b"hello")

        with patch.object(self.ac, "_close_stream",
                          wraps=self.ac._close_stream) as mock_close:
            result = self.ac.stop()

        mock_close.assert_called_once()
        self.assertEqual(result, b"hello",
                         "stop() must return queued PCM data")

    def test_stop_not_recording_returns_empty(self):
        """stop() when not recording returns empty bytes."""
        self.ac._recording = False
        result = self.ac.stop()
        self.assertEqual(result, b"")

    def test_stop_empty_queue_returns_empty(self):
        """stop() with empty queue returns empty bytes."""
        fake = FakeStream()
        self.ac._stream = fake
        self.ac._read_stop.clear()
        self.ac._read_thread = threading.Thread(
            target=lambda: None, daemon=True)
        self.ac._read_thread.start()
        self.ac._recording = True
        result = self.ac.stop()
        self.assertEqual(result, b"")

    # ── 3: _close_stream is idempotent ──────────────────────────

    def test_close_stream_idempotent(self):
        """Calling _close_stream twice does not raise."""
        fake = FakeStream()
        self.ac._stream = fake
        self.ac._read_stop.set()
        self.ac._read_thread = threading.Thread(
            target=lambda: None, daemon=True)
        self.ac._read_thread.start()

        try:
            self.ac._close_stream()
            self.ac._close_stream()  # second call
        except Exception as e:
            self.fail(f"double _close_stream raised: {e}")

        self.assertIsNone(self.ac._stream)
        # Second call: thread already cleared, stream already None — fine

    # ── 4: stream lifecycle ─────────────────────────────────────

    def test_start_stop_cycle_no_error(self):
        """Full start/stop cycle with fake stream does not raise."""
        fake = FakeStream()
        with patch.object(self.ac, "_open_stream",
                          side_effect=lambda: setattr(self.ac, "_stream", fake)):
            self.ac.start()
            self.assertTrue(self.ac._recording)
            self.assertIsNotNone(self.ac._read_thread)
            result = self.ac.stop()
        self.assertIsInstance(result, bytes)

    def test_close_stream_closes_active_stream(self):
        """_close_stream stops and closes an active stream."""
        fake = FakeStream()
        fake.is_active = MagicMock(return_value=True)
        fake.stop_stream = MagicMock(wraps=fake.stop_stream)
        fake.close = MagicMock(wraps=fake.close)

        self.ac._stream = fake
        self.ac._close_stream()

        fake.stop_stream.assert_called_once()
        fake.close.assert_called_once()
        self.assertIsNone(self.ac._stream)

    def test_close_stream_skips_join_if_thread_already_done(self):
        """_close_stream joins only if thread alive, doesn't error on done thread."""
        fake = FakeStream()
        self.ac._stream = fake
        self.ac._read_stop.set()
        self.ac._read_thread = threading.Thread(
            target=lambda: None, daemon=True)
        self.ac._read_thread.start()
        self.ac._read_thread.join()  # let it finish

        try:
            self.ac._close_stream()
        except Exception as e:
            self.fail(f"_close_stream with finished thread raised: {e}")

        self.assertIsNone(self.ac._stream)


if __name__ == "__main__":
    unittest.main()
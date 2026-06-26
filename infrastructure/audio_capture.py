"""Audio capture using PyAudio — raw PCM, gain processing, RMS level callback.

Uses blocking (read) mode instead of callback mode to avoid PortAudio heap
corruption (0xC0000374) on Windows/WASAPI. Callback mode creates a C→Python
callback thread that, after repeated start/stop cycles, corrupts PortAudio's
internal heap.

Blocking mode: each start() opens a fresh stream, reads in a loop on the
pipeline thread, stop() closes the stream. No background callback thread,
no heap corruption.
"""
from __future__ import annotations
import array
import logging
import pyaudio
import queue
import threading
from typing import Callable, Optional

CHUNK = 1024
RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
INT16_MAX = 32767
CLIP_LEVEL = int(INT16_MAX * 0.95)
MAX_GAIN = 12.0
MIN_PCM_LENGTH = 9600  # ~0.3s @ 16kHz — discard shorter recordings

logger = logging.getLogger(__name__)

# PortAudio heap corruption guard: once PortAudio has been initialized and used
# (via AudioCapture.start()), loading UIAutomationCore.dll in a new thread can
# trigger STATUS_DLL_INIT_FAILED (0xC0000142). Infrastructure that calls into
# UIA from a background thread (e.g. focus_context's in-process DLL) should
# check this flag and skip the risky path.
_portaudio_was_used = False


def was_portaudio_used() -> bool:
    return _portaudio_was_used


class AudioCapture:
    def __init__(self, gain: float = 2.0):
        self._pa = pyaudio.PyAudio()
        self._queue: queue.Queue = queue.Queue()
        self._level_cb: Optional[Callable[[float], None]] = None
        self._chunk_cb: Optional[Callable[[bytes], None]] = None
        self._gain = max(1.0, min(float(gain), MAX_GAIN))
        self._clip_samples = 0
        self._total_samples = 0
        self._gain_reduced = False
        self._noise_gate: float = 0.0
        self._recording = False
        self._stream = None
        self._read_thread = None
        self._read_stop = threading.Event()
        self._capture_stopped = threading.Event()

    def set_gain(self, gain: float):
        self._gain = max(1.0, min(float(gain), MAX_GAIN))

    def get_gain(self) -> float:
        return self._gain

    @property
    def gain_was_reduced(self) -> bool:
        return self._gain_reduced

    def set_level_callback(self, callback: Optional[Callable[[float], None]]):
        self._level_cb = callback

    def set_chunk_callback(self, callback: Optional[Callable[[bytes], None]]):
        self._chunk_cb = callback

    def reset_clip_stats(self):
        self._clip_samples = 0
        self._total_samples = 0

    def clip_fraction(self) -> float:
        if self._total_samples == 0:
            return 0.0
        return self._clip_samples / self._total_samples

    def _process_chunk(self, in_data: bytes):
        """Process a raw PCM chunk: apply gain, noise gate, callbacks."""
        gain = self._gain
        if gain != 1.0:
            arr = array.array("h")
            arr.frombytes(in_data)
            n = len(arr)

            # Peak-normalizing soft limiter
            peak = 0.0
            for i in range(n):
                v = abs(arr[i] / 32768.0 * gain)
                if v > peak:
                    peak = v

            clip_hits = 0
            scale = 0.95 / peak if peak > 0.95 else 1.0
            if peak > 0.95:
                clip_hits = sum(1 for i in range(n) if abs(arr[i] / 32768.0 * gain) > 0.95)

            for i in range(n):
                v = arr[i] / 32768.0 * gain * scale
                if v > 1.0:
                    v = 1.0
                elif v < -1.0:
                    v = -1.0
                arr[i] = int(v * 32767.0)

            self._clip_samples += clip_hits
            self._total_samples += n
            gained = arr.tobytes()
        else:
            gained = in_data

        # Noise gate
        ng = self._noise_gate
        if ng > 0.0 and len(gained) >= 64:
            arr2 = array.array("h")
            arr2.frombytes(gained)
            sq = sum(arr2[i] * arr2[i] for i in range(len(arr2)))
            rms = (sq / len(arr2)) ** 0.5 / 32768.0
            if rms < ng:
                gained = b"\x00" * len(gained)

        self._queue.put(gained)
        chunk_cb = self._chunk_cb
        if chunk_cb is not None:
            try:
                chunk_cb(gained)
            except Exception:
                logger.debug("AudioCapture: chunk callback failed", exc_info=True)
        cb = self._level_cb
        if cb is not None:
            try:
                arr = array.array("h")
                arr.frombytes(gained)
                n = len(arr)
                if n > 0:
                    sq = sum(arr[i] * arr[i] for i in range(0, n, 2))
                    rms = min(1.0, (sq / max(n // 2, 1)) ** 0.5 / 32768.0)
                    cb(rms)
            except Exception:
                pass

    def _read_loop(self):
        """Blocking read loop — runs on dedicated thread while recording."""
        stream = self._stream
        if stream is None:
            return
        try:
            last_log = 0
            while not self._read_stop.is_set() and self._recording:
                try:
                    in_data = stream.read(CHUNK, exception_on_overflow=False)
                    self._process_chunk(in_data)
                except Exception as e:
                    # Log first error, then keep trying
                    if last_log < 10:
                        logger.debug("AudioCapture: read error: %s", e)
                        last_log += 1
        except Exception:
            pass

    def _open_stream(self):
        """Open a fresh input stream for this recording session."""
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        try:
            dev_info = self._pa.get_default_input_device_info()
            logger.info(
                "[AUDIO-DEVICE] name=%r defaultSampleRate=%s maxInputCh=%s "
                "requested_rate=%d CHUNK=%d FORMAT=paInt16",
                dev_info.get("name", "?"),
                dev_info.get("defaultSampleRate", "?"),
                dev_info.get("maxInputChannels", "?"),
                RATE, CHUNK)
        except Exception:
            logger.info(
                "[AUDIO-DEVICE] requested_rate=%d CHUNK=%d (device info unavailable)",
                RATE, CHUNK)
        self._stream = self._pa.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK,
            stream_callback=None)  # blocking mode — no callback

    def _close_stream(self):
        """Close the stream. Safe to call even if already closed."""
        self._read_stop.set()
        # Close the stream FIRST to unblock stream.read() in the read
        # thread (blocking read waits ~64ms per chunk). Only then join
        # the thread. This prevents multi-second stop delays.
        if self._stream is not None:
            try:
                if self._stream.is_active():
                    self._stream.stop_stream()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)
            self._read_thread = None

    def start(self):
        # Reset gain from config
        try:
            from infrastructure.config_store import ConfigStore
            store = ConfigStore()
            configured_gain = store.get("audio", "gain_multiplier", 2.0)
            self._gain = max(1.0, min(float(configured_gain), MAX_GAIN))
            self._noise_gate = max(0.0, float(store.get("audio", "noise_gate_threshold", 0.015)))
        except Exception:
            self._noise_gate = 0.0
        if self._noise_gate > 0.0:
            logger.info("AudioCapture: noise_gate=%.4f", self._noise_gate)
        self.reset_clip_stats()
        self._read_stop.clear()
        self._capture_stopped.clear()

        # Open a fresh stream for each recording session
        self._open_stream()
        if self._stream is None:
            logger.error("AudioCapture: stream creation failed, cannot start")
            raise RuntimeError("Audio stream creation failed")

        self._stream.start_stream()

        # Fresh queue
        self._queue = queue.Queue()
        self._recording = True

        # Start blocking read thread
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

        global _portaudio_was_used
        _portaudio_was_used = True
        logger.info("AudioCapture: started gain=%.1fx blocking_read", self._gain)

    def stop(self) -> bytes:
        if not self._recording:
            return b""

        # Signal read thread to stop
        self._recording = False
        self._read_stop.set()

        # Close the stream FIRST to unblock stream.read() in the read
        # thread immediately (blocking read waits ~64ms per chunk).
        # Only then join the thread; this reduces stop latency from
        # up to 3.0s to near-instant.
        self._close_stream()

        # Collect PCM from queue
        chunks = []
        while not self._queue.empty():
            chunks.append(self._queue.get())
        pcm = b"".join(chunks)

        # Auto-reduce gain if clipping exceeded 10%
        if self.clip_fraction() > 0.10:
            new_gain = max(1.0, self._gain / 2.0)
            logger.warning("AudioCapture: clipping %.1f%%, reducing gain %.1f→%.1f",
                           self.clip_fraction() * 100, self._gain, new_gain)
            self._gain = new_gain
            self._gain_reduced = True
        logger.info("AudioCapture: stopped %d bytes, clip=%.2f%%",
                     len(pcm), self.clip_fraction() * 100)

        self._capture_stopped.set()

        return pcm

    def wait_for_stop(self, timeout: float = 3.0) -> bool:
        """Wait for the capture to fully stop (read thread exited, stream closed).

        Returns True if stopped within timeout, False if timed out.
        Used by orchestrator._on_hotkey_stop() to safely detach the pipeline
        before a new recording can start.
        """
        if not self._recording and not self._read_stop.is_set():
            return True  # already stopped
        return self._capture_stopped.wait(timeout=timeout)

    def close(self):
        self._recording = False
        self._read_stop.set()
        self._close_stream()
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    @staticmethod
    def detect_devices() -> list[str]:
        devices = []
        dedup = set()
        default_name = None
        try:
            p = pyaudio.PyAudio()
            try:
                default_info = p.get_default_input_device_info()
                default_name = default_info.get("name", "")
            except Exception:
                pass
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    name = info.get("name", "")
                    if not name:
                        continue
                    key = (name, info.get("maxInputChannels", 0))
                    if key not in dedup:
                        dedup.add(key)
                        devices.append(name)
            p.terminate()
        except Exception:
            pass
        if default_name and default_name in devices:
            devices.remove(default_name)
            devices.insert(0, default_name)
        return devices if devices else ["系统默认麦克风"]

    @staticmethod
    def is_pcm_too_short(pcm: bytes) -> bool:
        return len(pcm) < MIN_PCM_LENGTH
"""Audio capture using PyAudio — raw PCM, gain processing, RMS level callback."""
from __future__ import annotations
import array
import logging
import pyaudio
import queue
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


class AudioCapture:
    def __init__(self, gain: float = 2.0):
        self._pa = pyaudio.PyAudio()
        self._stream = None
        self._queue: queue.Queue = queue.Queue()
        self._level_cb: Optional[Callable[[float], None]] = None
        self._chunk_cb: Optional[Callable[[bytes], None]] = None
        self._gain = max(1.0, min(float(gain), MAX_GAIN))
        self._clip_samples = 0
        self._total_samples = 0
        self._gain_reduced = False  # True if stop() auto-reduced gain
        self._noise_gate: float = 0.0   # 0 = disabled

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

    def _cb(self, in_data, frame_count, time_info, status):
        gain = self._gain
        if gain != 1.0:
            arr = array.array("h")
            arr.frombytes(in_data)
            n = len(arr)

            # ── Peak-normalizing soft limiter ──
            # 1st pass: find absolute peak after gain
            peak = 0.0
            for i in range(n):
                v = abs(arr[i] / 32768.0 * gain)
                if v > peak:
                    peak = v

            # 2nd pass: apply gain with proportional scaling if peak > 0.95
            clip_hits = 0
            scale = 0.95 / peak if peak > 0.95 else 1.0
            if peak > 0.95:
                clip_hits = sum(1 for i in range(n) if abs(arr[i] / 32768.0 * gain) > 0.95)

            for i in range(n):
                v = arr[i] / 32768.0 * gain * scale
                # Safety clamp (should rarely trigger with soft limiter active)
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

        # ── Noise gate: replace low-energy frames with silence ──
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
        return (None, pyaudio.paContinue)

    def start(self):
        # ── Reset gain to user-configured value on each new recording ──
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
        while not self._queue.empty():
            self._queue.get()
        # ── [AUDIO-DEVICE] diagnostic — log device native rate vs requested rate ──
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
            input=True, frames_per_buffer=CHUNK, stream_callback=self._cb)
        self._stream.start_stream()
        logger.info("AudioCapture: started gain=%.1fx", self._gain)

    def stop(self) -> bytes:
        if self._stream is None:
            return b""
        self._stream.stop_stream()
        self._stream.close()
        self._stream = None
        chunks = []
        while not self._queue.empty():
            chunks.append(self._queue.get())
        pcm = b"".join(chunks)
        # Auto-reduce gain if clipping exceeded 10% (runtime only, NOT persisted)
        if self.clip_fraction() > 0.10:
            new_gain = max(1.0, self._gain / 2.0)
            logger.warning("AudioCapture: clipping %.1f%%, reducing gain %.1f→%.1f",
                           self.clip_fraction() * 100, self._gain, new_gain)
            self._gain = new_gain
            self._gain_reduced = True
        logger.info("AudioCapture: stopped %d bytes, clip=%.2f%%",
                     len(pcm), self.clip_fraction() * 100)
        return pcm

    def close(self):
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        self._pa.terminate()

    @staticmethod
    def detect_devices() -> list[str]:
        """Detect available audio input devices. Returns list with default device first."""
        devices = []
        dedup = set()
        default_name = None
        try:
            p = pyaudio.PyAudio()
            # Try to get system default input device name
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
                    # Dedup: use (name, maxInputChannels) tuple to catch cross-host-API duplicates
                    key = (name, info.get("maxInputChannels", 0))
                    if key not in dedup:
                        dedup.add(key)
                        devices.append(name)
            p.terminate()
        except Exception:
            pass
        # Move default device to front
        if default_name and default_name in devices:
            devices.remove(default_name)
            devices.insert(0, default_name)
        return devices if devices else ["系统默认麦克风"]

    @staticmethod
    def is_pcm_too_short(pcm: bytes) -> bool:
        return len(pcm) < MIN_PCM_LENGTH

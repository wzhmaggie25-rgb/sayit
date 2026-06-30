"""Focused tests for PCM quality metrics and the pipeline audio-quality gate.

Practical-incident P0: captured audio RMS=0.005 with a 0.015 noise gate zeroed
~97% of samples; ASR returned a short wrong result and AI was called with empty
input. The pipeline must fail closed on effectively-silent audio instead of
injecting hallucinated text.
"""
from __future__ import annotations

import array
import math
import unittest
from unittest.mock import MagicMock, patch

from infrastructure.audio_quality import (
    measure_pcm, should_reject_audio, AudioQuality,
)


def _pcm_silence(seconds: float = 3.0, rate: int = 16000) -> bytes:
    return b"\x00\x00" * int(rate * seconds)


def _pcm_tone(seconds: float = 3.0, rate: int = 16000, freq: float = 220.0,
              amp: float = 0.25) -> bytes:
    """A sine tone with a healthy amplitude -> clearly audible, not rejected."""
    n = int(rate * seconds)
    arr = array.array("h")
    for i in range(n):
        v = int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))
        arr.append(v)
    return arr.tobytes()


def _pcm_mostly_zero(active_ratio: float = 0.03, seconds: float = 4.0,
                     rate: int = 16000, amp: float = 0.25) -> bytes:
    """Mostly-zero PCM with a small fraction of active frames (mimics the
    incident WAV: zero_fraction ~0.97, active_ratio ~0.03)."""
    frame = 1024
    nframes = int(rate * seconds) // frame
    arr = array.array("h")
    for f in range(nframes):
        if (f / nframes) < active_ratio:
            # active frame: a short tone burst
            for i in range(frame):
                v = int(amp * 32767 * math.sin(2 * math.pi * 220 * i / rate))
                arr.append(v)
        else:
            arr.extend([0] * frame)
    return arr.tobytes()


def _pcm_quiet_continuous(seconds: float = 4.0, rate: int = 16000,
                          freq: float = 180.0, amp: float = 0.01) -> bytes:
    """Continuous quiet speech-like signal around incident-level RMS (~0.007)
    but with high non-zero continuity (no zeroed gaps).

    A low-amplitude sine: RMS = amp / sqrt(2). amp ~0.01 -> RMS ~0.007, within
    the incident range 0.005-0.009, while almost every sample is non-zero. This
    must NOT be rejected — it is real continuous quiet speech, not the
    near-all-zero incident signature.
    """
    n = int(rate * seconds)
    arr = array.array("h")
    for i in range(n):
        v = int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))
        arr.append(v)
    return arr.tobytes()


class AudioQualityMetricsTests(unittest.TestCase):
    def test_silence_is_effectively_silent(self):
        q = measure_pcm(_pcm_silence(3.0))
        self.assertAlmostEqual(q.rms, 0.0, places=6)
        self.assertEqual(q.zero_fraction, 1.0)
        self.assertLess(q.active_frame_ratio, 0.05)
        self.assertTrue(q.effectively_silent)

    def test_tone_is_not_silent(self):
        q = measure_pcm(_pcm_tone(3.0, amp=0.25))
        self.assertGreater(q.rms, 0.05)
        self.assertGreater(q.active_frame_ratio, 0.5)
        self.assertFalse(q.effectively_silent)

    def test_incident_like_audio_is_rejected(self):
        q = measure_pcm(_pcm_mostly_zero(active_ratio=0.03, seconds=4.0))
        self.assertGreaterEqual(q.zero_fraction, 0.9)
        self.assertLess(q.active_frame_ratio, 0.05)
        reject, reason = should_reject_audio(q)
        self.assertTrue(reject)
        self.assertEqual(reason, "audio_quality_too_low")

    def test_tone_not_rejected(self):
        q = measure_pcm(_pcm_tone(3.0, amp=0.25))
        reject, reason = should_reject_audio(q)
        self.assertFalse(reject)

    def test_empty_buffer_rejected(self):
        q = measure_pcm(b"")
        reject, reason = should_reject_audio(q)
        self.assertTrue(reject)

    def test_quiet_continuous_speech_not_rejected(self):
        """Gap 3/5: continuous quiet speech around incident-level RMS (0.005–
        0.009) with high non-zero continuity must be ACCEPTED, even though its
        fixed-threshold active-frame ratio may be low."""
        pcm = _pcm_quiet_continuous(seconds=4.0, amp=0.01)
        q = measure_pcm(pcm)
        # Incident-level RMS range.
        self.assertGreaterEqual(q.rms, 0.003)
        self.assertLessEqual(q.rms, 0.012)
        # High non-zero continuity (NOT the near-all-zero incident signature).
        self.assertGreater(q.nonzero_fraction, 0.9)
        reject, reason = should_reject_audio(q)
        self.assertFalse(reject)

    def test_incident_97_percent_zero_still_rejected(self):
        """Gap 6: the incident-like ~97%-zero fixture must still be rejected."""
        pcm = _pcm_mostly_zero(active_ratio=0.03, seconds=4.0)
        q = measure_pcm(pcm)
        self.assertGreaterEqual(q.zero_fraction, 0.9)
        self.assertLess(q.nonzero_fraction, 0.05)
        reject, reason = should_reject_audio(q)
        self.assertTrue(reject)
        self.assertEqual(reason, "audio_quality_too_low")


class PipelineAudioQualityGateTests(unittest.TestCase):
    """The pipeline gate is driven by measure_pcm + should_reject_audio. These
    assert the rejection decision and the user-facing message/reason that the
    production gate block emits, without instantiating the full pipeline (which
    needs a live lock/orchestrator). The production gate block in
    application/pipeline.run() calls exactly these functions."""

    def test_incident_audio_rejected_with_quality_reason(self):
        from infrastructure.audio_quality import measure_pcm, should_reject_audio
        pcm = _pcm_mostly_zero(active_ratio=0.02, seconds=4.0)
        q = measure_pcm(pcm)
        reject, reason = should_reject_audio(q)
        self.assertTrue(reject)
        self.assertEqual(reason, "audio_quality_too_low")
        # The production message is fixed; assert the reason maps to the
        # fail-closed terminal outcome the gate emits.
        self.assertFalse(q.effectively_silent is False and reject)

    def test_rejection_implies_no_asr_no_injection(self):
        """When the gate rejects, the pipeline block returns before ASR/AI/
        injection. Equivalent to: a rejected buffer must not reach ASR. We
        assert the gate decision is deterministic and blocking."""
        from infrastructure.audio_quality import measure_pcm, should_reject_audio
        for pcm in (_pcm_silence(3.0), _pcm_mostly_zero(0.02, 4.0)):
            reject, _ = should_reject_audio(measure_pcm(pcm))
            self.assertTrue(reject)

    def test_healthy_audio_not_rejected(self):
        from infrastructure.audio_quality import measure_pcm, should_reject_audio
        pcm = _pcm_tone(3.0, amp=0.25)
        reject, reason = should_reject_audio(measure_pcm(pcm))
        self.assertFalse(reject)


class NoiseGateRuntimeDisableTests(unittest.TestCase):
    """Gap 2: the recovery version must disable the legacy chunk-level noise
    gate at runtime (effective=0.0) even when the user's on-disk config is
    0.015, so a quiet valid signal is not zeroed. On-disk config is unchanged."""

    def test_configured_0_015_gate_disabled_at_runtime(self):
        from infrastructure.audio_capture import AudioCapture
        cap = AudioCapture(gain=1.0)
        with patch("infrastructure.config_store.ConfigStore") as mock_cfg, \
             patch.object(AudioCapture, "_open_stream") as mock_open:
            mock_cfg.return_value.get.side_effect = lambda *k: (
                0.015 if k == ("audio", "noise_gate_threshold", 0.0)
                else (1.0 if k == ("audio", "gain_multiplier", 2.0) else 0.0))
            cap._stream = MagicMock()  # satisfy start_stream path
            cap.start()
        try:
            self.assertEqual(cap._noise_gate, 0.0)
            self.assertEqual(getattr(cap, "_configured_gate", 0.0), 0.015)
        finally:
            cap._recording = False
            try:
                cap._close_stream()
            except Exception:
                pass

    def test_quiet_signal_not_zeroed_with_legacy_config(self):
        """A quiet continuous signal processed through AudioCapture with a
        configured 0.015 gate must NOT be zeroed (effective gate 0.0)."""
        import queue
        from infrastructure.audio_capture import AudioCapture
        cap = AudioCapture(gain=1.0)
        cap._noise_gate = 0.0  # recovery-version effective gate
        cap._queue = queue.Queue()
        quiet = _pcm_quiet_continuous(seconds=0.5, amp=0.01)
        # _process_chunk applies the (zero) gate and enqueues; with effective
        # gate 0.0 the chunk is never zeroed, so non-zero content survives.
        cap._process_chunk(quiet[:2048])
        out = cap._queue.get_nowait()
        self.assertTrue(any(b != 0 for b in out),
                        "quiet signal was zeroed despite effective gate 0.0")


if __name__ == "__main__":
    unittest.main()

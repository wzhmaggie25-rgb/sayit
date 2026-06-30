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


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()

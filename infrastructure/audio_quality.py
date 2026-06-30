"""Reusable PCM audio-quality metrics and a conservative fail-closed gate.

Round 9.5A practical-acceptance incident: a captured session had overall
RMS=0.005 while the runtime noise gate was 0.015, which zeroed ~97% of samples
(sayit_last.wav: zero_fraction=0.968, active_ratio@0.010=0.032). ASR then
returned a short wrong result and the AI layer was called with empty normalized
input. Output character length alone cannot catch this — the audio must be
measured directly.

This module provides pure-Python PCM metrics (no third-party deps) and a
conservative quality decision reusable by the pipeline and by tests.
"""
from __future__ import annotations

import array
from dataclasses import dataclass

# 16-bit signed PCM assumption (SayIt's configured audio format is pcm_s16le,
# 16k mono). Sample width is fixed here for simplicity and matches the capture
# path (array "h"). If multi-byte/float PCM is ever introduced, extend here.
_SAMPLE_WIDTH = 2  # bytes per sample, signed 16-bit
_MAX_SAMPLE = 32768.0


@dataclass(frozen=True)
class AudioQuality:
    """Quality metrics for a 16-bit PCM buffer."""
    rms: float                 # normalized RMS in [0, 1]
    peak: float                # normalized peak amplitude in [0, 1]
    zero_fraction: float       # fraction of samples that are exactly 0
    nonzero_fraction: float
    active_frame_ratio: float  # fraction of frames above the active threshold
    duration_s: float
    sample_count: int

    @property
    def effectively_silent(self) -> bool:
        """Conservative combined-evidence test for effectively-silent audio.

        Do NOT reject merely because the fixed-threshold active-frame ratio is
        low — a continuous quiet voice signal around RMS 0.005–0.009 can sit
        below the 0.010 frame threshold yet still be real speech. Reject only on
        combined conservative evidence: near-all-zero samples (the incident
        signature, ~97% zeros) OR extremely low RMS *and* peak together.
        """
        near_all_zero = self.nonzero_fraction < 0.05
        extremely_low = self.rms < 0.003 and self.peak < 0.02
        return near_all_zero or extremely_low


# Frame size used for active-frame measurement (matches AudioCapture's CHUNK).
_FRAME_SAMPLES = 1024

# Conservative active-frame RMS threshold. The incident WAV had active_ratio
# 0.032 at this threshold; clearly audible speech is typically >= ~0.10. A frame
# must exceed this normalized RMS to count as "active".
ACTIVE_FRAME_RMS = 0.010

# A recording shorter than this is treated as too-short by AudioCapture already;
# we keep a parallel floor so the quality gate has a stable duration to reason
# about even if MIN_PCM_LENGTH changes.
MIN_DURATION_S = 0.3


def measure_pcm(pcm: bytes, sample_rate: int = 16000,
                frame_samples: int = _FRAME_SAMPLES,
                active_rms: float = ACTIVE_FRAME_RMS) -> AudioQuality:
    """Compute quality metrics for a 16-bit signed PCM byte buffer."""
    if not pcm:
        return AudioQuality(0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0)
    samples = array.array("h")
    # Truncate any trailing partial sample so frombytes does not raise.
    usable = len(pcm) - (len(pcm) % _SAMPLE_WIDTH)
    samples.frombytes(pcm[:usable])
    n = len(samples)
    if n == 0:
        return AudioQuality(0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0)

    sq = 0
    peak = 0
    nonzero = 0
    for s in samples:
        sq += s * s
        a = s if s >= 0 else -s
        if a > peak:
            peak = a
        if s != 0:
            nonzero += 1
    rms = (sq / n) ** 0.5 / _MAX_SAMPLE
    peak_norm = peak / _MAX_SAMPLE
    nonzero_fraction = nonzero / n

    nframes = max(1, n // frame_samples)
    active = 0
    for i in range(nframes):
        seg = samples[i * frame_samples:(i + 1) * frame_samples]
        if not seg:
            continue
        seg_sq = 0
        for x in seg:
            seg_sq += x * x
        seg_rms = (seg_sq / len(seg)) ** 0.5 / _MAX_SAMPLE
        if seg_rms >= active_rms:
            active += 1
    active_frame_ratio = active / nframes

    duration_s = n / sample_rate
    return AudioQuality(
        rms=rms,
        peak=peak_norm,
        zero_fraction=1.0 - nonzero_fraction,
        nonzero_fraction=nonzero_fraction,
        active_frame_ratio=active_frame_ratio,
        duration_s=duration_s,
        sample_count=n,
    )


def should_reject_audio(quality: AudioQuality) -> tuple[bool, str]:
    """Return (reject, reason). Conservative fail-closed for ASR.

    Rejects when the buffer is effectively silent (near-all-zero samples or too
    few active frames). This catches the low-RMS / over-gated incident without
    relying on output character length.
    """
    if quality.sample_count == 0:
        return True, "empty_audio"
    if quality.duration_s < MIN_DURATION_S:
        return True, "audio_too_short"
    if quality.effectively_silent:
        return True, "audio_quality_too_low"
    return False, "ok"

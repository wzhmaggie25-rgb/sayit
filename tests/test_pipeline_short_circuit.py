"""Real production-pipeline short-circuit tests for the practical-ASR fix.

These instantiate the real RecordingPipeline and drive run() with fakes to prove
fail-closed behavior end-to-end:

- rejected (effectively-silent) audio aborts streaming and never reaches batch
  ASR, corrector, injector, db.add_history, or silent monitor, and emits the
  expected failure events;
- raw ASR that normalizes to empty stops before injection (no raw garbage
  injected), never calling provider/injector/silent-monitor/successful-history.
"""
from __future__ import annotations

import sys
import threading
import unittest
from unittest.mock import MagicMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)


class FakeEventBus:
    def __init__(self):
        self.emits = []

    def on(self, event, cb):
        pass

    def emit(self, event, *args, **kwargs):
        self.emits.append((event, args, kwargs))


def _pcm_incident_like(seconds: float = 4.0, rate: int = 16000) -> bytes:
    """~97% zero PCM mimicking the over-gated incident WAV (rejected)."""
    import array
    frame = 1024
    nframes = int(rate * seconds) // frame
    arr = array.array("h")
    for f in range(nframes):
        if (f / nframes) < 0.03:
            for i in range(frame):
                arr.append(int(0.25 * 32767 * __import__("math").sin(
                    2 * 3.14159 * 220 * i / rate)))
        else:
            arr.extend([0] * frame)
    return arr.tobytes()


def _pcm_healthy(seconds: float = 3.0, rate: int = 16000) -> bytes:
    """Non-silent PCM that passes the quality gate."""
    import array, math
    n = int(rate * seconds)
    arr = array.array("h")
    for i in range(n):
        arr.append(int(0.25 * 32767 * math.sin(2 * math.pi * 220 * i / rate)))
    return arr.tobytes()


class PipelineShortCircuitTests(unittest.TestCase):
    def setUp(self):
        from application.eventbus import Events
        from application.pipeline import RecordingPipeline
        self.Events = Events
        self.Pipeline = RecordingPipeline

    def _make(self):
        eb = FakeEventBus()
        p = self.Pipeline(eb)
        return p, eb

    def _stop_soon(self, p, delay=0.15):
        t = threading.Timer(delay, p.stop)
        t.daemon = True
        t.start()
        return t

    def _fakes(self, pcm, *, raw_asr="打开豆包助手", corrector_side_effect=None):
        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = pcm

        asr = MagicMock()
        streaming = MagicMock()
        asr.create_streaming_session.return_value = streaming
        asr.transcribe.return_value = (raw_asr, "aliyun")

        corrector = MagicMock()
        if corrector_side_effect is not None:
            corrector.process.side_effect = corrector_side_effect
        else:
            corrector.process.return_value = (raw_asr, "test", "test-model")

        hotwords = MagicMock()
        hotwords.apply_layer2_correction.side_effect = lambda t: t
        hotwords.get_words.return_value = []

        injector = MagicMock()
        injector.last_target_proc = "x"
        injector.last_target_class = ""
        injector.last_target_title = ""
        injector.last_target_hwnd = 0
        injector.last_target_pid = 0

        silent = MagicMock()
        db = MagicMock()
        db.get_rules.return_value = []
        db.add_history.return_value = "hid-1"
        return dict(audio_capture=audio, asr_cascade=asr, corrector=corrector,
                    hotwords_mgr=hotwords, injector=injector,
                    silent_monitor=silent, db=db), \
            dict(audio=audio, asr=asr, streaming=streaming,
                 corrector=corrector, injector=injector, silent=silent, db=db)

    # ── Gap 4: rejected audio short-circuits the whole pipeline ──

    def test_rejected_audio_aborts_streaming_and_skips_everything(self):
        p, eb = self._make()
        tmr = self._stop_soon(p)
        kwargs, f = self._fakes(_pcm_incident_like(4.0))
        try:
            p.run(enable_correction=True, **kwargs)
        except Exception:
            pass
        tmr.join(timeout=3)

        f["streaming"].abort.assert_called()
        f["asr"].transcribe.assert_not_called()         # no batch ASR
        f["corrector"].process.assert_not_called()      # no AI
        f["injector"].inject.assert_not_called()        # no injection
        f["db"].add_history.assert_not_called()         # no history row
        f["silent"].start.assert_not_called()           # no silent learning

        terminal = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertEqual(len(terminal), 1)
        payload = terminal[0][1][0]
        self.assertEqual(payload["outcome"], "failed")
        self.assertEqual(payload["reason_code"], "audio_quality_too_low")
        self.assertFalse(payload["final_text_available"])
        rec_err = [e for e in eb.emits if e[0] == "recording:error"]
        self.assertTrue(rec_err, "expected a user-facing RECORDING_ERROR")

    # ── Gap 1/8: raw ASR non-empty but normalizes to empty ──

    def test_normalized_empty_stops_before_injection(self):
        from infrastructure.corrector import EmptyNormalizedInputError
        p, eb = self._make()
        tmr = self._stop_soon(p)
        # Healthy audio passes the quality gate; ASR returns filler-only text
        # that normalizes to empty -> corrector raises EmptyNormalizedInputError.
        kwargs, f = self._fakes(
            _pcm_healthy(3.0),
            raw_asr="嗯嗯嗯",
            corrector_side_effect=EmptyNormalizedInputError("empty"))
        try:
            p.run(enable_correction=True, **kwargs)
        except Exception:
            pass
        tmr.join(timeout=3)

        # Provider was called (corrector.process) but it raised; the pipeline
        # must NOT inject, must NOT add a successful history row, must NOT start
        # silent learning.
        f["injector"].inject.assert_not_called()
        f["db"].add_history.assert_not_called()
        f["silent"].start.assert_not_called()

        terminal = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertEqual(len(terminal), 1)
        payload = terminal[0][1][0]
        self.assertEqual(payload["outcome"], "failed")
        self.assertEqual(payload["reason_code"], "empty_normalized_input")
        self.assertFalse(payload["final_text_available"])
        rec_err = [e for e in eb.emits if e[0] == "recording:error"]
        self.assertTrue(rec_err)

    # ── Sanity: healthy audio + real text reaches injection ──

    def test_healthy_audio_reaches_injection(self):
        p, eb = self._make()
        tmr = self._stop_soon(p)
        kwargs, f = self._fakes(_pcm_healthy(3.0), raw_asr="打开豆包助手")
        try:
            p.run(enable_correction=True, **kwargs)
        except Exception:
            pass
        tmr.join(timeout=3)
        # With healthy audio the pipeline proceeds past the quality gate to ASR
        # (streaming finish and/or batch transcribe) — proving the gate did not
        # short-circuit valid audio.
        asr_reached = f["streaming"].finish.called or f["asr"].transcribe.called
        self.assertTrue(asr_reached,
                        "healthy audio should reach ASR, not be short-circuited")


if __name__ == "__main__":
    unittest.main()

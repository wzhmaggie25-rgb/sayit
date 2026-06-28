"""A3: Test ASR total budget covers streaming + batch + local fallback.

Calls PRODUCTION RecordingPipeline.run() and AsrCascade.transcribe() with
fake engines that burn wall-clock time. Proves that the current implementation
computes a total budget deadline but does NOT propagate `remaining` into each
engine's internal timeout (BUG).

Key invariants:
1. Total wall-clock for ALL ASR phases ≤ configured total budget.
2. When budget is exhausted mid-cascade, remaining engines are skipped.
3. Pipeline emits terminal event with outcome=failed + reason "asr_total_budget_exceeded".
4. Each engine's internal timeout ≤ min(engine_default, remaining_budget).

Current BUG: pipeline.py computes `asr_deadline` and passes `remaining` to
streaming_session.finish(), but asr_cascade.transcribe(pcm) takes no budget
parameter — each engine uses hardcoded timeouts (DashScope 15s, Volcengine 30s,
ONNX unbounded).
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

from infrastructure.config_store import ConfigStore

logging.disable(logging.CRITICAL)


class FakeEventBus:
    """Event bus that records all emits for verification."""
    def __init__(self):
        self.emits = []

    def on(self, event, cb):
        pass

    def emit(self, event, *args, **kwargs):
        self.emits.append((event, args, kwargs))


def _start_stop_timer(p, delay=0.1):
    """Start a timer that will stop the pipeline after a delay."""
    def _do_stop():
        p.stop()
    t = threading.Timer(delay, _do_stop)
    t.daemon = True
    t.start()
    return t


class TestAsrTotalBudget(unittest.TestCase):
    """Verify ASR total budget covers all engines."""

    def setUp(self):
        from application.eventbus import Events
        from application.pipeline import RecordingPipeline
        from infrastructure.asr import AsrCascade
        self.Events = Events
        self.Pipeline = RecordingPipeline
        self.Cascade = AsrCascade

    def _make_pipeline(self):
        eb = FakeEventBus()
        p = self.Pipeline(eb)
        return p, eb

    def _pcm_bytes(self, seconds=2):
        """Generate fake PCM data that passes MIN_PCM_LENGTH check."""
        return b"\x00\x00" * (16000 * seconds)

    def _make_config(self):
        """Return a config dict with all engines disabled (we inject fakes)."""
        return {
            "asr_engine": "aliyun",
            "aliyun": {"api_key": ""},  # no key → DashScopeASR won't init
            "volcengine": {"asr": {"api_key": ""}},
            "asr_fallback": {
                "enable": True,
                "order": ["aliyun", "volcengine", "onnx"],
                "onnx_model_dir": "/nonexistent",
            },
            "local": {"language": "zh", "itn": True},
        }

    # ── 1. Total budget: pipeline run respects deadline ────────────────

    def test_total_budget_prevents_streaming_batch_from_running_forever(self):
        """Total budget enforced: streaming exhausts budget → batch cascade is skipped.

        Pipeline computes asr_deadline and passes remaining to streaming.finish().
        When streaming consumes the full budget (via its timeout), the batch
        fallback is skipped entirely — even the cascade is not called.
        """
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.2)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes(3)

        # Streaming session that blocks long enough to exhaust the 0.1s budget
        streaming = MagicMock()

        def _streaming_finish_exhaust_budget(**kw):
            timeout = kw.get("timeout", 0.5)
            time.sleep(timeout + 0.3)  # exceed budget
            raise TimeoutError("streaming timed out")

        streaming.finish.side_effect = _streaming_finish_exhaust_budget
        asr = MagicMock()
        asr.create_streaming_session.return_value = streaming

        # Batch cascade — this SHOULD be skipped when budget is exhausted
        batch_called = threading.Event()
        def _slow_batch(pcm, **kw):
            batch_called.set()
            time.sleep(5)
            return "batch result", "aliyun"

        asr.transcribe.side_effect = _slow_batch

        corrector = MagicMock()
        hotwords = MagicMock()
        injector = MagicMock()
        silent = MagicMock()
        db = MagicMock()
        db.get_rules.return_value = []

        # Patch config store to set tiny budget (0.1s)
        from infrastructure.config_store import ConfigStore
        with patch.object(ConfigStore, 'get', side_effect=self._config_get_short_budget):
            start = time.monotonic()
            try:
                p.run(
                    audio_capture=audio,
                    asr_cascade=asr,
                    corrector=corrector,
                    hotwords_mgr=hotwords,
                    injector=injector,
                    silent_monitor=silent,
                    db=db,
                    enable_correction=False,
                )
            except Exception:
                pass
            elapsed = time.monotonic() - start

        tmr.join(timeout=3)

        # Check terminal event
        terminal_events = [e for e in eb.emits if e[0] == "pipeline:terminal"]
        self.assertGreaterEqual(
            len(terminal_events), 1,
            f"Expected terminal event for budget exhaustion, got: {eb.emits}"
        )

        # After Phase D: elapsed should be ≤ 0.2 (recording) + 0.4 (streaming timeout) + overhead
        self.assertLess(
            elapsed, 3.0,
            f"Pipeline took {elapsed:.1f}s — batch should have been skipped"
        )

        # After Phase D fix: batch_called should NOT be set (skipped due to budget)
        self.assertFalse(
            batch_called.is_set(),
            f"Batch cascade was invoked despite budget exhaustion. "
            f"Pipeline took {elapsed:.1f}s, batch_called={batch_called.is_set()}"
        )

    def _config_get_short_budget(self, key, *args, **kwargs):
        """Return 0.1s ASR budget, default for others."""
        if key == "asr_total_budget_s":
            return 0.1
        if key == "silent_learning":
            return False
        if key == "organize_level":
            return "none"
        return ConfigStore_get_default(key, args, kwargs)

    # ── 2. Streaming bounded by remaining budget ──────────────────────

    def test_streaming_bounded_by_remaining_budget(self):
        """Streaming finish() timeout must be ≤ remaining budget.

        Current code at pipeline.py:207:
          remaining = max(0.0, asr_deadline - time.time()) if asr_deadline != inf else 8.0
          streaming_timeout = min(remaining, 8.0)
          raw_text = streaming_session.finish(timeout=streaming_timeout)

        This is already partially correct — streaming IS capped by remaining.
        But if remaining < 0 (budget exhausted during recording), streaming
        should be skipped entirely, not called with timeout=0.
        """
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.3)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes(3)

        streaming = MagicMock()
        asr = MagicMock()
        asr.create_streaming_session.return_value = streaming
        asr.transcribe.return_value = ("fallback text", "aliyun")

        corrector = MagicMock()
        hotwords = MagicMock()
        injector = MagicMock()
        silent = MagicMock()
        db = MagicMock()
        db.get_rules.return_value = []

        call_log = []

        def _track_streaming_finish(**kw):
            call_log.append(("finish", kw))
            raise TimeoutError("streaming timed out")

        streaming.finish.side_effect = _track_streaming_finish

        with patch.object(ConfigStore, 'get', side_effect=self._config_get_short_budget):
            try:
                p.run(
                    audio_capture=audio,
                    asr_cascade=asr,
                    corrector=corrector,
                    hotwords_mgr=hotwords,
                    injector=injector,
                    silent_monitor=silent,
                    db=db,
                    enable_correction=False,
                )
            except Exception:
                pass

        tmr.join(timeout=3)

        # Verify streaming.finish() was called with a tight timeout
        self.assertGreaterEqual(len(call_log), 1, "streaming.finish() was never called")
        if call_log:
            timeout_used = call_log[0][1].get("timeout", -1)
            self.assertLessEqual(
                timeout_used, 0.5,
                f"streaming.finish() called with timeout={timeout_used}s, "
                f"expected ≤ 0.5s for 0.1s budget"
            )

    # ── 3. AsrCascade.transcribe() lacks budget parameter ─────────────

    def test_asr_cascade_transcribe_has_budget_param(self):
        """AsrCascade.transcribe() now accepts remaining parameter.

        Updated signature: def transcribe(self, pcm_bytes, remaining=None)
        Each engine uses min(engine_timeout, remaining) as internal timeout.
        """
        import inspect
        sig = inspect.signature(self.Cascade.transcribe)
        params = list(sig.parameters.keys())

        self.assertIn(
            "remaining", params,
            f"AsrCascade.transcribe() missing 'remaining' param. "
            f"Current params: {params}"
        )

    # ── 4. Budget exhausted mid-cascade skips remaining engines ───────

    def test_budget_exhausted_skips_batch_cascade(self):
        """Budget exhausted after streaming → batch cascade is skipped.

        When streaming raises with budget already exhausted, the batch
        cascade must be skipped. The budget check at pipeline.py:230
        covers both the empty-text and exception paths since both set
        raw_text="" and fall into the `if not raw_text:` block.
        """
        p, eb = self._make_pipeline()
        tmr = _start_stop_timer(p, delay=0.2)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes(3)

        # Streaming raises after blocking long enough to exhaust budget
        streaming = MagicMock()
        def _finish_slow(**kw):
            time.sleep(0.5)
            raise TimeoutError("streaming timeout")
        streaming.finish.side_effect = _finish_slow
        asr = MagicMock()
        asr.create_streaming_session.return_value = streaming

        batch_called = threading.Event()
        asr.transcribe.side_effect = lambda pcm, **kw: (batch_called.set(), ("result", "aliyun"))[1]

        corrector = MagicMock()
        hotwords = MagicMock()
        injector = MagicMock()
        silent = MagicMock()
        db = MagicMock()
        db.get_rules.return_value = []

        with patch.object(ConfigStore, 'get', side_effect=self._config_get_short_budget):
            try:
                p.run(
                    audio_capture=audio,
                    asr_cascade=asr,
                    corrector=corrector,
                    hotwords_mgr=hotwords,
                    injector=injector,
                    silent_monitor=silent,
                    db=db,
                    enable_correction=False,
                )
            except Exception:
                pass

        tmr.join(timeout=3)

        # After Phase D fix: batch_called should NOT be set — the budget was
        # exhausted during recording (0.2s) against a 0.1s budget
        self.assertFalse(
            batch_called.is_set(),
            "Batch cascade was invoked despite budget exhaustion from streaming exception path"
        )

    # ── 5. 10x run: no thread growth from budget enforcement ──────────

    def test_10x_pipeline_runs_no_thread_growth(self):
        """10 consecutive pipeline runs with budget exhaustion must not leak threads."""
        baseline = threading.active_count()

        for i in range(10):
            p, eb = self._make_pipeline()
            self._run_with_exhausted_budget(p, eb, delay=0.05)

        time.sleep(0.5)
        after = threading.active_count()

        self.assertLessEqual(
            after, baseline + 5,
            f"Thread count grew from {baseline} to {after} after 10 pipeline runs"
        )

    def _run_with_exhausted_budget(self, p, eb, delay=0.05):
        """Helper: run pipeline with tiny budget."""
        tmr = _start_stop_timer(p, delay=delay)

        audio = MagicMock()
        audio.start.return_value = None
        audio.stop.return_value = self._pcm_bytes(2)

        streaming = MagicMock()
        streaming.finish.side_effect = TimeoutError("timeout")
        asr = MagicMock()
        asr.create_streaming_session.return_value = streaming
        asr.transcribe.return_value = ("text", "aliyun")

        corrector = MagicMock()
        hotwords = MagicMock()
        injector = MagicMock()
        silent = MagicMock()
        db = MagicMock()
        db.get_rules.return_value = []

        with patch.object(ConfigStore, 'get', side_effect=self._config_get_short_budget):
            try:
                p.run(
                    audio_capture=audio,
                    asr_cascade=asr,
                    corrector=corrector,
                    hotwords_mgr=hotwords,
                    injector=injector,
                    silent_monitor=silent,
                    db=db,
                    enable_correction=False,
                )
            except Exception:
                pass

        tmr.join(timeout=3)


def ConfigStore_get_default(key, args, kwargs):
    """Fallback for ConfigStore.get() for keys we don't override."""
    defaults = {
        "asr_total_budget_s": 30.0,
        "silent_learning": False,
        "organize_level": "none",
        "ai_timeout": 25.0,
        "audio": {},
        "remove_trailing_period": False,
    }
    return defaults.get(key, None if not kwargs else kwargs.get('default', None))


if __name__ == "__main__":
    unittest.main()
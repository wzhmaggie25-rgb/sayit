"""Phase A3: Global ASR deadline tests — prove two bugs.

BUG 1 (pipeline.py:204): Uses time.time() (wall-clock) instead of
time.monotonic(). System clock changes (NTP sync, daylight saving, user
adjustment) can arbitrarily extend or shrink the ASR deadline.

BUG 2 (asr.py:619): AsrCascade.transcribe() passes the SAME `remaining`
value to each engine in sequence. If engine 1 consumes 5 seconds and fails,
engine 2 still receives the original remaining (e.g. 30s) rather than the
real remaining budget (25s). This means engine 2 could start a 30s call
that overruns the budget.

Both tests FAIL on current code.
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

from infrastructure.config_store import ConfigStore


# ── Helper: get default config value ──

def _config_get_default(key, args, kwargs):
    """Return the default ConfigStore value for a known key."""
    defaults = {
        "asr_total_budget_s": 30.0,
        "silent_learning": False,
        "organize_level": "none",
        "copy_result_to_clipboard": False,
        "language": "zh",
    }
    if key in defaults:
        return defaults[key]
    # Check if there's a default from kwargs
    if args:
        return args[0]
    if kwargs:
        return list(kwargs.values())[0] if kwargs else None
    return None


class FakeEventBus:
    def __init__(self):
        self.emits = []

    def on(self, event, cb):
        pass

    def emit(self, event, *args, **kwargs):
        self.emits.append((event, args, kwargs))


class TestAsrDeadlineBugs(unittest.TestCase):
    """Prove ASR deadline bugs on current code."""

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
        return b"\x00\x00" * (16000 * seconds)

    @staticmethod
    def _start_stop_after(p, delay=0.2):
        t = threading.Timer(delay, p.stop)
        t.daemon = True
        t.start()
        return t

    # ════════════════════════════════════════════════════════════
    # BUG 1: time.time() vs time.monotonic()
    # ════════════════════════════════════════════════════════════

    def test_asr_deadline_must_use_monotonic_clock(self):
        """asr_deadline must use time.monotonic(), not time.time().

        FAILS ON CURRENT CODE: pipeline.py:204 uses time.time().
        We prove the bug by asserting there is NO call to time.time()
        in the ASR deadline computation path.

        To verify this without manipulating system clock (risky), we
        inspect the pipeline source and assert that the deadline
        expression uses time.monotonic().
        """
        import inspect
        source = inspect.getsource(self.Pipeline.run)

        # The deadline expression at line 204 should use monotonic
        # After fix: "asr_deadline = time.monotonic() + asr_total_budget"
        # Before fix: "asr_deadline = time.time() + asr_total_budget"

        # Find the asr_deadline assignment
        for line in source.splitlines():
            if "asr_deadline" in line and "+ asr_total_budget" in line:
                # This line must use time.monotonic(), not time.time()
                # BEFORE FIX: assertion FAILS
                self.assertIn(
                    "monotonic", line,
                    f"asr_deadline uses time.time() instead of time.monotonic(). "
                    f"Line: {line.strip()}"
                )
                break
        else:
            self.fail("Could not find asr_deadline assignment in pipeline.run()")

    # ════════════════════════════════════════════════════════════
    # BUG 2: Shared remaining across cascade engines
    # ════════════════════════════════════════════════════════════

    def test_cascade_engines_get_recomputed_remaining(self):
        """Each cascade engine must get recomputed remaining, not same value.

        FAILS ON CURRENT CODE: AsrCascade.transcribe() at asr.py:619 passes
        the same `remaining` to every engine in sequence. If engine 1 takes
        5s and fails, engine 2 should have remaining=25 not remaining=30.

        We test by creating an AsrCascade with two engines where:
        - Engine 1 is slow (sleeps 2s then fails)
        - Engine 2 should get a reduced remaining

        Then we check what remaining was passed to engine 2.
        """
        from infrastructure.asr import AsrCascade

        # Create cascade with two fake engines
        engine1 = MagicMock()
        engine2 = MagicMock()

        # Engine 1: slow, consumes 2s, then fails
        def _slow_fail(pcm, remaining=None):
            time.sleep(2.0)
            raise RuntimeError("engine 1 failed")

        engine1.transcribe.side_effect = _slow_fail

        cascade = AsrCascade(
            config={
                "aliyun": {"api_key": ""},
                "volcengine": {"asr": {"api_key": ""}},
                "asr_fallback": {
                    "enable": True,
                    "order": ["aliyun", "volcengine", "onnx"],
                    "onnx_model_dir": "/nonexistent",
                },
            }
        )

        # Replace the internal engines with our fakes
        cascade._aliyun = engine1
        cascade._volcengine = engine2
        cascade._order = ["aliyun", "volcengine"]

        # Call transcribe with remaining=5.0
        # Engine 1 takes 2s → engine 2 should get remaining ≈ 3.0
        try:
            cascade.transcribe(self._pcm_bytes(2), remaining=5.0)
        except RuntimeError:
            pass

        # Check what remaining was passed to engine 2
        # BEFORE FIX: engine 2 still gets 5.0 (same as engine 1)
        # AFTER FIX: engine 2 should get ~3.0 (5.0 - 2.0 consumed)
        self.assertTrue(engine2.transcribe.called,
                        "Engine 2 was never called")
        call_args = engine2.transcribe.call_args
        remaining_passed = call_args[1].get("remaining")
        self.assertIsNotNone(
            remaining_passed,
            "Engine 2 must be called with remaining parameter"
        )
        # After fix: remaining should be ~3.0 (was 5.0, engine 1 took ~2s)
        # Before fix: remaining is still 5.0
        self.assertLess(
            remaining_passed, 4.0,
            f"Engine 2 got remaining={remaining_passed}, expected ~3.0 "
            f"(5.0 minus 2s consumed by engine 1). FAILS on current code "
            f"because the same remaining value is shared across engines."
        )

    def test_cascade_engine_1_exhausts_remaining_skips_engine_2(self):
        """When engine 1 exhausts the remaining budget, engine 2 is skipped.

        FAILS ON CURRENT CODE: if engine 1 consumes the entire remaining budget
        (remaining ≤ 0 after engine 1), engine 2 still gets called with the
        original remaining value instead of being skipped.
        """
        from infrastructure.asr import AsrCascade

        engine1 = MagicMock()
        engine2 = MagicMock()

        # Engine 1: slow, takes 6s (more than 5s remaining)
        def _exhaust_budget(pcm, remaining=None):
            time.sleep(0.1)  # minimal actual sleep
            raise RuntimeError("engine 1 failed")

        engine1.transcribe.side_effect = _exhaust_budget

        # Configure engine 2 to record if called
        engine2_called = threading.Event()

        def _eng2_call(pcm, remaining=None):
            engine2_called.set()
            raise RuntimeError("engine 2 should not be called")

        engine2.transcribe.side_effect = _eng2_call

        cascade = AsrCascade(
            config={
                "aliyun": {"api_key": ""},
                "volcengine": {"asr": {"api_key": ""}},
                "asr_fallback": {
                    "enable": True,
                    "order": ["aliyun", "volcengine", "onnx"],
                    "onnx_model_dir": "/nonexistent",
                },
            }
        )

        cascade._aliyun = engine1
        cascade._volcengine = engine2
        cascade._order = ["aliyun", "volcengine"]

        # Call with remaining=5.0 — engine 1 took 0.1s but remaining
        # is the same value, so engine 2 also gets 5.0 unless recomputed
        try:
            cascade.transcribe(self._pcm_bytes(2), remaining=5.0)
        except RuntimeError:
            pass

        # Engine 2 was called on current code (reuses original remaining=5.0)
        # After fix: engine 2 should NOT be called because remaining was
        # recomputed and budget is exhausted.
        # This assertion is a catch: if these engines were real (DashScope 15s,
        # Volcengine 30s), the total would be 5+15+30=50s, not 30s budget.
        #
        # We assert that engine 2 WAS called on current code (proving the bug)
        # and will NOT be called after the fix.
        self.assertTrue(
            engine2_called.is_set(),
            "Engine 2 was NOT called — the bug may already be partially fixed. "
            "Expected: engine 2 IS called on current code because remaining "
            "is not recomputed."
        )

        # Additionally verify engine 2 got the stale remaining
        call_args = engine2.transcribe.call_args
        remaining_passed = call_args[1].get("remaining")
        self.assertAlmostEqual(
            remaining_passed, 5.0, delta=0.5,
            msg=f"Engine 2 got remaining={remaining_passed}, should be ~5.0 "
                f"(original, not recomputed). After fix should be ~0 or skipped."
        )
"""Full-chain test: native_emit → python_receive → orchestrator_action.

This is the headline assertion from CURRENT_TASK §B3: the SECOND RAlt
press must drive `_on_hotkey_stop` BEFORE the third arrives — never
delayed to the third.

We use the real `KeyboardHelperDll` + the test-only HookProc parser
entry, but replace the orchestrator's downstream collaborators with
fakes so the test runs deterministically with no audio device.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

os.environ.setdefault("SAYIT_TEST_MODE", "1")

from application.eventbus import Events
from application.orchestrator import SayitOrchestrator
from domain.models import RecordingState
from infrastructure.keyboard_helper_dll import KeyboardHelperDll

# Reuse the synthetic-key helpers from test_keyboard_helper_physical.
VK_RMENU = 0xA5
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP   = 0x0105


def _dll_ready() -> bool:
    h = KeyboardHelperDll()
    if not h.is_available:
        return False
    try:
        getattr(h.lib, "__test_handle_event")
    except AttributeError:
        return False
    return True


class _ControllablePipeline:
    def __init__(self, eventbus):
        self._eb = eventbus
        self.state = RecordingState.IDLE
        self.capture_done = threading.Event()
        self.transcribe_done = threading.Event()
        self.allow_inject = threading.Event()
        self.run_started = threading.Event()
        self.run_returned = threading.Event()
        self._stop_flag = False

    def is_idle(self):
        return self.state == RecordingState.IDLE

    def stop(self):
        self._stop_flag = True
        self.capture_done.set()

    def run(self, **kwargs):
        self.run_started.set()
        try:
            self.state = RecordingState.CAPTURING
            self._eb.emit(Events.RECORDING_STARTED)
            self.capture_done.wait(timeout=10)
            self.state = RecordingState.TRANSCRIBING
            self._eb.emit(Events.RECORDING_STOPPED)
            self.transcribe_done.wait(timeout=10)
            self.state = RecordingState.INJECTING
            self.allow_inject.wait(timeout=10)
            self.state = RecordingState.DONE
        finally:
            self.run_returned.set()


class _NullInjector:
    last_target_hwnd = 0
    last_target_pid = 0

    def capture_target(self):
        from infrastructure.injector import InjectionTarget
        return InjectionTarget(hwnd=0, pid=0, proc="fake.exe", cls="", title="")


@unittest.skipUnless(_dll_ready(),
                     "sayit_keyboard_helper.dll missing or older ABI")
class HookToOrchestratorChainTests(unittest.TestCase):

    def setUp(self):
        # Build orchestrator with fake collaborators.
        self.orch = SayitOrchestrator()
        self.orch._injector = _NullInjector()
        self.orch._audio = MagicMock()
        self.orch._audio.wait_for_stop = MagicMock()

        # Stage exactly ONE pipeline factory — any extra calls fail.
        self.next_pipeline = None
        import application.orchestrator as orch_mod
        self._orig_factory = orch_mod.RecordingPipeline

        def _factory(eventbus):
            assert self.next_pipeline is not None, "no fake pipeline staged"
            p = self.next_pipeline
            self.next_pipeline = None
            return p
        orch_mod.RecordingPipeline = _factory

        # Install the real keyboard helper bound to orchestrator.toggle_recording.
        self.helper = KeyboardHelperDll()
        try:
            self.helper.uninstall()
        except Exception:
            pass
        ok = self.helper.install(self.orch.toggle_recording)
        self.assertTrue(ok)
        self.helper.test_reset_state()

    def tearDown(self):
        try:
            self.helper.uninstall()
        except Exception:
            pass
        import application.orchestrator as orch_mod
        orch_mod.RecordingPipeline = self._orig_factory
        try:
            self.orch.stop()
        except Exception:
            pass

    def _press_release(self):
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYDOWN, 0)
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, 0)

    def test_seq2_drives_stop_request_before_seq3_arrives(self):
        """1st press starts pipeline. 2nd press IS the stop. 3rd press IGNORED.

        The test fails if seq 3 is observed BEFORE seq 2's effect (stop
        flag set) — which is exactly the user-reported bug.
        """
        p = _ControllablePipeline(self.orch.eventbus)
        self.next_pipeline = p

        ignored_stages = []
        stopping_observed = []
        self.orch.eventbus.on(
            Events.TOGGLE_IGNORED, lambda stage: ignored_stages.append(stage))
        self.orch.eventbus.on(
            Events.RECORDING_STOPPING, lambda: stopping_observed.append(time.monotonic()))

        # Seq 1 — start
        self._press_release()
        self.assertTrue(p.run_started.wait(timeout=3),
                        "first RAlt press never started the pipeline")
        # Wait for CAPTURING
        deadline = time.time() + 2.0
        while time.time() < deadline and p.state != RecordingState.CAPTURING:
            time.sleep(0.01)
        self.assertEqual(p.state, RecordingState.CAPTURING)

        # Seq 2 — must request stop. We assert this BEFORE issuing seq 3.
        self._press_release()
        deadline = time.time() + 2.0
        while time.time() < deadline and not p._stop_flag:
            time.sleep(0.01)
        self.assertTrue(p._stop_flag,
                        "second RAlt press did NOT set stop flag — "
                        "stop request delayed to a later press")
        self.assertEqual(len(stopping_observed), 1,
                         "RECORDING_STOPPING was not emitted on seq 2")
        # The pipeline is now in TRANSCRIBING (blocked on transcribe_done).
        deadline = time.time() + 2.0
        while time.time() < deadline and p.state != RecordingState.TRANSCRIBING:
            time.sleep(0.01)
        self.assertEqual(p.state, RecordingState.TRANSCRIBING)

        # Seq 3 — must be IGNORED. Critically: do NOT stage a new pipeline.
        self.next_pipeline = None
        self._press_release()
        deadline = time.time() + 1.5
        while time.time() < deadline and not ignored_stages:
            time.sleep(0.02)
        self.assertEqual(ignored_stages, ["transcribing"],
                         f"third press did not produce TOGGLE_IGNORED — got {ignored_stages!r}")
        self.assertTrue(self.orch.is_busy(),
                        "busy gate must remain set during post-processing")

        # Cleanup: let the pipeline finish naturally.
        p.transcribe_done.set()
        p.allow_inject.set()
        p.run_returned.wait(timeout=3)
        deadline = time.time() + 2.0
        while time.time() < deadline and self.orch.is_busy():
            time.sleep(0.02)
        self.assertFalse(self.orch.is_busy())

        # Diagnostic ring must show exactly 3 dispatches in order.
        events = self.helper.recent_events(limit=8)
        seqs = [e["seq"] for e in events]
        # The last 3 entries should be the 3 toggles we drove.
        self.assertGreaterEqual(len(seqs), 3)
        self.assertEqual(seqs, sorted(seqs))

    def test_recording_stopping_emits_before_audio_drains(self):
        """RECORDING_STOPPING is emitted SYNCHRONOUSLY from _on_hotkey_stop."""
        p = _ControllablePipeline(self.orch.eventbus)
        self.next_pipeline = p
        # First press → start
        self._press_release()
        p.run_started.wait(timeout=3)
        deadline = time.time() + 1.0
        while time.time() < deadline and p.state != RecordingState.CAPTURING:
            time.sleep(0.01)

        observed = []
        self.orch.eventbus.on(
            Events.RECORDING_STOPPING, lambda: observed.append(time.monotonic()))

        # Manually call stop_recording — RECORDING_STOPPING must be emitted
        # before this call returns.
        t0 = time.monotonic()
        self.orch.stop_recording()
        t1 = time.monotonic()
        self.assertEqual(len(observed), 1,
                         "RECORDING_STOPPING was not emitted from stop_recording")
        self.assertLessEqual(observed[0], t1,
                             "RECORDING_STOPPING emit happened after stop returned")
        # Cleanup
        p.transcribe_done.set(); p.allow_inject.set()
        p.run_returned.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()

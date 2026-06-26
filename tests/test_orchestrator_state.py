"""State-machine tests for SayitOrchestrator.

Covers the gating contract described in CURRENT_TASK.md:
- 1st toggle starts a pipeline
- 2nd toggle (while CAPTURING) signals stop
- 3rd toggle (while TRANSCRIBING / CORRECTING / INJECTING) is ignored —
  must NOT start a parallel pipeline
- Only after the pipeline's _pipeline_wrapper.finally clears state does
  the next toggle start a fresh pipeline
- Errors anywhere must still release the gate

These tests use fakes for every collaborator so they run on any OS.
"""
from __future__ import annotations
import threading
import time
import unittest
from unittest.mock import MagicMock

from application.eventbus import Events
from application.orchestrator import SayitOrchestrator
from application.pipeline import RecordingPipeline
from domain.models import RecordingState


class _ControllablePipeline:
    """A fake RecordingPipeline whose run() blocks until we let it advance.

    Mirrors the public surface that SayitOrchestrator touches:
      - state property
      - is_idle()
      - run(...) (long-running)
      - stop()
    """
    def __init__(self, eventbus):
        self._eb = eventbus
        self.state = RecordingState.IDLE
        # Gates the pipeline can wait on, one per phase the test wants to drive.
        self.capture_done = threading.Event()
        self.transcribe_done = threading.Event()
        self.allow_inject = threading.Event()
        self.run_started = threading.Event()
        self.run_returned = threading.Event()
        self._stop_flag = False
        self.crashed = False

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
            # Wait until stop() (or test) signals capture is done.
            self.capture_done.wait(timeout=10)
            self.state = RecordingState.TRANSCRIBING
            self._eb.emit(Events.RECORDING_STOPPED)
            self.transcribe_done.wait(timeout=10)
            self.state = RecordingState.INJECTING
            self.allow_inject.wait(timeout=10)
            self.state = RecordingState.DONE
            self._eb.emit(Events.PIPELINE_DONE, "fake-final")
        except Exception:
            self.crashed = True
            self.state = RecordingState.ERROR
            raise
        finally:
            self.run_returned.set()


class _CrashingPipeline(_ControllablePipeline):
    """Pipeline that raises after capture so we exercise the error path."""
    def __init__(self, eventbus, where: str = "transcribe"):
        super().__init__(eventbus)
        self.where = where

    def run(self, **kwargs):
        self.run_started.set()
        try:
            self.state = RecordingState.CAPTURING
            self._eb.emit(Events.RECORDING_STARTED)
            self.capture_done.wait(timeout=10)
            self.state = RecordingState.TRANSCRIBING
            if self.where == "transcribe":
                raise RuntimeError("synthetic ASR failure")
        finally:
            self.run_returned.set()


class _NullInjector:
    def capture_target(self):
        from infrastructure.injector import InjectionTarget
        return InjectionTarget(hwnd=0, pid=0, proc="fake.exe", cls="", title="")


class OrchestratorStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.orch = SayitOrchestrator()
        # Replace expensive collaborators with fakes — we only test the gate.
        self.orch._injector = _NullInjector()
        # Audio.wait_for_stop must return promptly during fake pipeline finish.
        self.orch._audio = MagicMock()
        self.orch._audio.wait_for_stop = MagicMock()
        self.fake_pipeline = None

        def _factory(eventbus):
            # Each call returns the next prepared fake pipeline.
            assert self.fake_pipeline is not None, "no fake pipeline staged"
            p = self.fake_pipeline
            self.fake_pipeline = None
            return p

        # Monkey-patch the orchestrator module's RecordingPipeline constructor.
        import application.orchestrator as orch_mod
        self._orig_recording_pipeline = orch_mod.RecordingPipeline
        orch_mod.RecordingPipeline = _factory

    def tearDown(self):
        import application.orchestrator as orch_mod
        orch_mod.RecordingPipeline = self._orig_recording_pipeline
        # Best-effort cleanup
        try:
            self.orch.stop()
        except Exception:
            pass

    def _stage(self, pipeline):
        """Stage a pipeline to be returned by the next RecordingPipeline()."""
        self.fake_pipeline = pipeline

    # ── 1: first toggle starts a pipeline ───────────────────────

    def test_first_toggle_starts_pipeline(self):
        p = _ControllablePipeline(self.orch.eventbus)
        self._stage(p)

        self.orch.toggle_recording()
        self.assertTrue(p.run_started.wait(timeout=2),
                        "pipeline.run was never called")
        self.assertTrue(self.orch.is_busy())
        # Cleanup
        p.capture_done.set(); p.transcribe_done.set(); p.allow_inject.set()
        p.run_returned.wait(timeout=2)

    # ── 2: second toggle while CAPTURING signals stop ───────────

    def test_second_toggle_during_capture_signals_stop(self):
        p = _ControllablePipeline(self.orch.eventbus)
        self._stage(p)
        self.orch.toggle_recording()
        p.run_started.wait(timeout=2)
        # Wait for state to be CAPTURING
        deadline = time.time() + 1
        while time.time() < deadline:
            if p.state == RecordingState.CAPTURING:
                break
            time.sleep(0.01)

        self.orch.toggle_recording()
        self.assertTrue(p._stop_flag, "stop_flag was not set on second toggle")
        # Cleanup
        p.transcribe_done.set(); p.allow_inject.set()
        p.run_returned.wait(timeout=2)

    # ── 3: third toggle during post-processing is IGNORED ───────

    def test_third_toggle_during_post_processing_is_ignored(self):
        p = _ControllablePipeline(self.orch.eventbus)
        self._stage(p)
        self.orch.toggle_recording()
        p.run_started.wait(timeout=2)

        ignored_events = []
        self.orch.eventbus.on(Events.TOGGLE_IGNORED, lambda stage: ignored_events.append(stage))

        # Move into capturing → stop → transcribing
        # Wait until CAPTURING
        deadline = time.time() + 1
        while time.time() < deadline and p.state != RecordingState.CAPTURING:
            time.sleep(0.01)
        self.orch.toggle_recording()  # signals stop
        # Pipeline now blocks in transcribe_done.wait
        deadline = time.time() + 1
        while time.time() < deadline and p.state != RecordingState.TRANSCRIBING:
            time.sleep(0.01)
        self.assertEqual(p.state, RecordingState.TRANSCRIBING)

        # NOTHING ELSE STAGED — if the orchestrator tried to start a 2nd
        # pipeline, our factory would raise AssertionError.
        self.fake_pipeline = None
        result = self.orch.toggle_recording()
        self.assertFalse(result, "third toggle started a new pipeline")
        self.assertEqual(ignored_events, ["transcribing"],
                         f"expected TOGGLE_IGNORED('transcribing'), got {ignored_events!r}")
        self.assertTrue(self.orch.is_busy(),
                        "busy flag must remain set during post-processing")

        # Now let pipeline finish. After finish, the next toggle should
        # succeed because the gate has been released.
        p.transcribe_done.set(); p.allow_inject.set()
        p.run_returned.wait(timeout=3)

        # Wait for wrapper finally to release state.
        deadline = time.time() + 2
        while time.time() < deadline and self.orch.is_busy():
            time.sleep(0.02)
        self.assertFalse(self.orch.is_busy(),
                         "busy flag was not cleared after pipeline finished")

        # Now a fresh pipeline should be acceptable.
        p2 = _ControllablePipeline(self.orch.eventbus)
        self._stage(p2)
        self.assertTrue(self.orch.toggle_recording(),
                        "third pipeline rejected after first finished")
        p2.run_started.wait(timeout=2)
        p2.capture_done.set(); p2.transcribe_done.set(); p2.allow_inject.set()
        p2.run_returned.wait(timeout=2)

    # ── 4: exception path still releases the gate ───────────────

    def test_exception_path_releases_gate(self):
        p = _CrashingPipeline(self.orch.eventbus)
        self._stage(p)
        self.orch.toggle_recording()
        p.run_started.wait(timeout=2)
        # Let it crash in transcribe.
        p.capture_done.set()
        p.run_returned.wait(timeout=3)
        # Wait for wrapper finally
        deadline = time.time() + 2
        while time.time() < deadline and self.orch.is_busy():
            time.sleep(0.02)
        self.assertFalse(self.orch.is_busy(),
                         "busy flag was not cleared after pipeline crashed")

    # ── 5: rapid double-press during IDLE only starts one pipeline ──

    def test_rapid_double_press_starts_one_pipeline(self):
        """Two RAlt toggles in the same millisecond — only one pipeline runs."""
        p = _ControllablePipeline(self.orch.eventbus)
        self._stage(p)
        # Both toggles arrive in tight succession. Second one must either be
        # a stop-signal (if CAPTURING by then) or a no-op (if pipeline not yet
        # in CAPTURING — toggle_recording sees active=True but state != CAPTURING,
        # so it ignores). Either way: NO second pipeline.
        self.fake_pipeline_secondary = None
        self.orch.toggle_recording()
        # Do NOT stage another pipeline. If the orchestrator tries to start
        # one, the factory will assert.
        self.orch.toggle_recording()
        # Cleanup
        p.capture_done.set(); p.transcribe_done.set(); p.allow_inject.set()
        p.run_returned.wait(timeout=3)
        deadline = time.time() + 2
        while time.time() < deadline and self.orch.is_busy():
            time.sleep(0.02)
        self.assertFalse(self.orch.is_busy())


if __name__ == "__main__":
    unittest.main()

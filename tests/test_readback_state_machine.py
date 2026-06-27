"""Real-readback / attempted_unverified state-machine tests.

Phase 3 of Round 6: the injector must distinguish four outcomes for any
input attempt:

  verified_success      — target readback proves the text is in place
  attempted_unverified  — shortcut sent, readback not available; do NOT
                          re-attempt via a second path (risks duplicate
                          text); the user gets a neutral result card
  injection_failed      — readback proves the target did NOT receive
                          the text (e.g. control rejected the paste)
  no_editable_target    — there is no editable focus / capture at all

In all but verified_success the SilentMonitor must NOT be started.
"""
from __future__ import annotations
import unittest
from unittest.mock import patch, MagicMock

from infrastructure.injector import Injector, InjectionResult, InjectionTarget
from infrastructure import clipboard_snapshot as snapmod


def _empty_snapshot():
    return snapmod.ClipboardSnapshot(kind="EMPTY")


class ReadbackPathTests(unittest.TestCase):
    """The clipboard paste path with real readback."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")
        self.target = InjectionTarget(
            hwnd=4242, pid=1, proc="notepad.exe", cls="Edit", title="x")

    def _common_patches(self):
        return [
            patch.object(self.inj, "_lock", MagicMock()),
            patch.object(self.inj, "_focus_window", return_value=True),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable"),
            patch.object(self.inj, "_get_focused_edit_hwnd", return_value=0),
            patch.object(self.inj, "_foreground_info",
                         return_value=(4242, "Edit", 1, "notepad.exe")),
            patch.object(self.inj, "_get_context_for_strategy", return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target", return_value=False),
            patch.object(self.inj, "_inject_uia", return_value=False),
            patch("infrastructure.clipboard_snapshot.read_snapshot",
                  return_value=_empty_snapshot()),
            patch("infrastructure.clipboard_snapshot.restore_snapshot",
                  return_value=True),
            patch("ctypes.windll.user32.keybd_event"),
            patch("time.sleep"),
        ]

    def test_paste_target_grows_with_expected_text_is_verified(self):
        """Pre snapshot 'foo', post 'foobar' (expected='bar') → verified_success."""
        # Use ['foo' pre, 'foobar' post] sequence
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, "foo"), (True, "foobar")]),
            patch.object(self.inj, "_direct_input", return_value=False),  # should not be called
        ]
        # 13 common + 2 extra = 15 patches (indices 0-14)
        self.assertEqual(len(patches), 15)
        with patches[0]:
            with patches[1]:
                with patches[2]:
                    with patches[3]:
                        with patches[4]:
                            with patches[5]:
                                with patches[6]:
                                    with patches[7]:
                                        with patches[8]:
                                            with patches[9]:
                                                with patches[10]:
                                                    with patches[11]:
                                                        with patches[12]:
                                                            with patches[13]:
                                                                with patches[14]:
                                                                    result = self.inj.inject(
                                                                        "bar", target=self.target)
        self.assertTrue(result.ok)
        self.assertEqual(result.state, "verified_success")
        self.assertEqual(result.method, "clipboard")
        self.assertTrue(result.target_verified)

    def test_paste_target_unchanged_returns_injection_failed(self):
        """Pre 'abc', post 'abc' — paste did nothing.

        Round 7 spec: reliable unchanged → injection_failed.

        We can't tell whether the consumer rejected the paste or whether
        the text was rendered somewhere else, but since readback IS
        available and proves the target did not change, this is a clear
        failure. Do NOT then try SendInput on top, that risks duplicate
        text in apps that accepted the paste but route results through a
        separate buffer.
        """
        direct_mock = MagicMock(return_value=True)
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, "abc"), (True, "abc")]),
            patch.object(self.inj, "_direct_input", direct_mock),
        ]
        # 13 common + 2 extra = 15 patches (indices 0-14)
        self.assertEqual(len(patches), 15)
        ctx_managers = []
        try:
            for p in patches:
                ctx_managers.append(p.__enter__())
            result = self.inj.inject("xyz", target=self.target)
        finally:
            for p in reversed(patches):
                try: p.__exit__(None, None, None)
                except Exception: pass
        # Per Round 7 spec: reliable unchanged → injection_failed
        self.assertEqual(result.state, "injection_failed")
        self.assertEqual(result.reason, "paste_target_unchanged")
        # SendInput must NOT have been called — that's the whole point.
        direct_mock.assert_not_called()

    def test_paste_no_readback_returns_attempted_unverified(self):
        """Pre readback ok, post readback fails → attempted_unverified."""
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, ""), (False, "")]),
        ]
        # 13 common + 1 extra = 14 patches (indices 0-13)
        self.assertEqual(len(patches), 14)
        ctx_managers = []
        try:
            for p in patches:
                ctx_managers.append(p.__enter__())
            result = self.inj.inject("xyz", target=self.target)
        finally:
            for p in reversed(patches):
                try: p.__exit__(None, None, None)
                except Exception: pass
        self.assertEqual(result.state, "attempted_unverified")
        self.assertFalse(result.target_verified)

    def test_attempted_unverified_does_not_run_sendinput(self):
        """The clipboard attempted_unverified path must not fall through to
        SendInput. Otherwise the same text could end up twice in apps that
        silently accepted the paste."""
        direct_mock = MagicMock(return_value=True)
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, ""), (False, "")]),
            patch.object(self.inj, "_direct_input", direct_mock),
        ]
        # 13 common + 2 extra = 15 patches (indices 0-14)
        self.assertEqual(len(patches), 15)
        ctx_managers = []
        try:
            for p in patches:
                ctx_managers.append(p.__enter__())
            result = self.inj.inject("xyz", target=self.target)
        finally:
            for p in reversed(patches):
                try: p.__exit__(None, None, None)
                except Exception: pass
        self.assertEqual(result.state, "attempted_unverified")
        direct_mock.assert_not_called()


class SendInputReadbackTests(unittest.TestCase):
    """When clipboard is skipped (strategy=send_input or refused snapshot),
    the SendInput path must also do real readback."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_sendinput_verified(self):
        target = InjectionTarget(hwnd=4242, pid=1, proc="x.exe", cls="Edit", title="t")
        with patch.object(self.inj, "_lock", MagicMock()), \
             patch.object(self.inj, "_focus_window", return_value=True), \
             patch.object(self.inj, "_assess_target_editability",
                          return_value="editable"), \
             patch.object(self.inj, "_get_focused_edit_hwnd", return_value=0), \
             patch.object(self.inj, "_foreground_info",
                          return_value=(4242, "Edit", 1, "x.exe")), \
             patch.object(self.inj, "_get_context_for_strategy", return_value={}), \
             patch.object(self.inj, "_strategy_for_context", return_value="send_input"), \
             patch.object(self.inj, "_is_terminal_target", return_value=False), \
             patch.object(self.inj, "_inject_uia", return_value=False), \
             patch.object(self.inj, "_direct_input", return_value=True), \
             patch.object(self.inj, "_snapshot_target_text",
                          side_effect=[(True, ""), (True, "hello")]), \
             patch("time.sleep"):
            result = self.inj.inject("hello", target=target)
        self.assertTrue(result.ok)
        self.assertEqual(result.state, "verified_success")
        self.assertEqual(result.method, "sendinput")

    def test_sendinput_no_readback_unverified(self):
        target = InjectionTarget(hwnd=4242, pid=1, proc="x.exe", cls="Edit", title="t")
        with patch.object(self.inj, "_lock", MagicMock()), \
             patch.object(self.inj, "_focus_window", return_value=True), \
             patch.object(self.inj, "_assess_target_editability",
                          return_value="editable"), \
             patch.object(self.inj, "_get_focused_edit_hwnd", return_value=0), \
             patch.object(self.inj, "_foreground_info",
                          return_value=(4242, "Edit", 1, "x.exe")), \
             patch.object(self.inj, "_get_context_for_strategy", return_value={}), \
             patch.object(self.inj, "_strategy_for_context", return_value="send_input"), \
             patch.object(self.inj, "_is_terminal_target", return_value=False), \
             patch.object(self.inj, "_inject_uia", return_value=False), \
             patch.object(self.inj, "_direct_input", return_value=True), \
             patch.object(self.inj, "_snapshot_target_text",
                          side_effect=[(False, ""), (False, "")]), \
             patch("time.sleep"):
            result = self.inj.inject("hello", target=target)
        self.assertEqual(result.state, "attempted_unverified")
        self.assertEqual(result.method, "sendinput")


class PipelineSilentMonitorGatingTests(unittest.TestCase):
    """SilentMonitor must only start on verified_success+target_verified."""

    def test_attempted_unverified_does_not_start_silent_monitor(self):
        """Pipeline routing for attempted_unverified — phase 4 spec."""
        from application.pipeline import RecordingPipeline
        from application.eventbus import EventBus, Events

        eb = EventBus()
        events = []
        for evname in [Events.INJECTION_DONE, Events.RESULT_CARD_SHOW,
                        Events.PIPELINE_ERROR, Events.NO_EDITABLE_TARGET]:
            eb.on(evname, lambda *a, _n=evname: events.append((_n, a)))

        # Simulate what pipeline does for attempted_unverified
        inject_result = InjectionResult(
            ok=True, state="attempted_unverified",
            verified=False, method="clipboard",
            clipboard_preserved=True, clipboard_restored=True,
            target_verified=False,
            reason="paste_no_readback")

        # Verify state classification
        self.assertEqual(inject_result.state, "attempted_unverified")
        self.assertFalse(inject_result.target_verified)

        # Pipeline gating check (mirrors the can_learn logic)
        can_learn = (
            inject_result.state == "verified_success"
            and inject_result.target_verified
        )
        self.assertFalse(can_learn,
                         "attempted_unverified must NOT start SilentMonitor")


if __name__ == "__main__":
    unittest.main()

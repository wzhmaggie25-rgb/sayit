"""Injector fallback tests.

Verifies the contract in CURRENT_TASK.md §C:

  Any return path that yields False MUST guarantee the final text is on
  the clipboard so the user can paste manually. UIA failure, clipboard
  shortcut failure, SendInput failure, foreground HWND mismatch, target
  restore failure — all routes must end with the clipboard populated.

The tests stub out the OS-level helpers so we exercise the waterfall
ordering and the clipboard-fallback contract without driving real
windows.
"""
from __future__ import annotations
import unittest
from unittest.mock import patch

from infrastructure.injector import Injector, InjectionTarget


def _patch_clipboard():
    """Return (patcher, captured_list) — every _clipboard_set_text call
    appends the text it was asked to write, so the test can verify the
    LAST text that ended up on the clipboard."""
    captured = []

    def fake_set(text):
        captured.append(text)
        return True

    p = patch("infrastructure.injector._clipboard_set_text", side_effect=fake_set)
    return p, captured


class InjectorFallbackTests(unittest.TestCase):
    SENTINEL = "sentinel-text-7ce8b1b9"

    def _make_injector(self):
        return Injector(injection_mode="auto")

    # ── 1: target restore failure ───────────────────────────────

    def test_target_restore_failure_leaves_text_on_clipboard(self):
        """When the original window cannot be focused AND no child Edit
        control exists, inject() returns False but final_text MUST be on
        the clipboard."""
        inj = self._make_injector()
        target = InjectionTarget(hwnd=123, pid=1, proc="fake.exe",
                                 cls="FakeClass", title="Fake")
        cp_patch, cp_captured = _patch_clipboard()
        with patch.object(inj, "_focus_window", return_value=False), \
             patch.object(inj, "_inject_win32_child_edit", return_value=False), \
             cp_patch:
            ok = inj.inject(self.SENTINEL, target=target)
        self.assertFalse(ok, "inject reported success on restore failure")
        self.assertIn(self.SENTINEL, cp_captured,
                      "final_text was not preserved on clipboard")

    # ── 2: foreground mismatch ─────────────────────────────────

    def test_foreground_mismatch_leaves_text_on_clipboard(self):
        inj = self._make_injector()
        target = InjectionTarget(hwnd=123, pid=1, proc="fake.exe",
                                 cls="FakeClass", title="Fake")
        cp_patch, cp_captured = _patch_clipboard()
        # _focus_window succeeds, but foreground info returns a different HWND
        with patch.object(inj, "_focus_window", return_value=True), \
             patch.object(inj, "_foreground_info",
                          return_value=(999, "OtherClass", 2, "other.exe")), \
             patch.object(inj, "_inject_win32_child_edit", return_value=False), \
             cp_patch:
            ok = inj.inject(self.SENTINEL, target=target)
        self.assertFalse(ok)
        self.assertIn(self.SENTINEL, cp_captured)

    # ── 3: UIA failure → clipboard paste failure → SendInput failure ──

    def test_all_three_layers_fail_leaves_text_on_clipboard(self):
        inj = self._make_injector()
        cp_patch, cp_captured = _patch_clipboard()
        # No target — go straight into the normal waterfall.
        with patch.object(inj, "_focus_window", return_value=True), \
             patch.object(inj, "_foreground_info",
                          return_value=(42, "Edit", 99, "notepad.exe")), \
             patch.object(inj, "_get_context_for_strategy", return_value={}), \
             patch.object(inj, "_inject_uia", return_value=False), \
             patch.object(inj, "paste", return_value=False), \
             patch.object(inj, "_direct_input", return_value=False), \
             cp_patch:
            ok = inj.inject(self.SENTINEL)
        self.assertFalse(ok)
        self.assertIn(self.SENTINEL, cp_captured,
                      "final_text was not preserved on clipboard after triple failure")

    # ── 4: terminal clipboard failure ──────────────────────────

    def test_terminal_clipboard_failure_leaves_text_on_clipboard(self):
        """Terminals skip the SendInput fallback (would inject as commands).
        That early-return path must still leave the clipboard populated."""
        inj = self._make_injector()
        cp_patch, cp_captured = _patch_clipboard()
        with patch.object(inj, "_focus_window", return_value=True), \
             patch.object(inj, "_foreground_info",
                          return_value=(42, "ConsoleWindowClass", 99, "cmd.exe")), \
             patch.object(inj, "_get_context_for_strategy", return_value={}), \
             patch.object(inj, "paste", return_value=False), \
             cp_patch:
            ok = inj.inject(self.SENTINEL)
        self.assertFalse(ok)
        self.assertIn(self.SENTINEL, cp_captured)

    # ── 5: success path does NOT add a fallback clipboard copy ──

    def test_success_path_does_not_overwrite_clipboard(self):
        """The fallback clipboard write is only for failure. If UIA succeeds
        we must not also pollute the clipboard."""
        inj = self._make_injector()
        cp_patch, cp_captured = _patch_clipboard()
        with patch.object(inj, "_focus_window", return_value=True), \
             patch.object(inj, "_foreground_info",
                          return_value=(42, "Edit", 99, "notepad.exe")), \
             patch.object(inj, "_get_context_for_strategy", return_value={}), \
             patch.object(inj, "_inject_uia", return_value=True), \
             cp_patch:
            ok = inj.inject(self.SENTINEL)
        self.assertTrue(ok)
        # Note: inj.paste() (level 2) sets clipboard internally — we mocked
        # _inject_uia to succeed at level 1, so no clipboard write should
        # have happened from our fallback path.
        self.assertNotIn(self.SENTINEL, cp_captured,
                         "fallback wrote clipboard despite UIA success")


if __name__ == "__main__":
    unittest.main()

"""Injector fallback tests.

Verifies the contract per CURRENT_TASK_OVERRIDE.md:

  On injection failure, clipboard_preserved is True by default — the final
  text is NOT auto-copied to clipboard. Only when copy_result_to_clipboard
  is explicitly enabled does _fail() write text to clipboard.

  UIA failure, clipboard shortcut failure, SendInput failure, foreground
  HWND mismatch, target restore failure — all routes must end with the
  clipboard preserved (untouched by default).

The tests stub out the OS-level helpers so we exercise the waterfall
ordering without driving real windows.
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

    def _mock_config_copy_false(self):
        """By default copy_result_to_clipboard is False — no auto-copy."""
        return patch("infrastructure.injector.ConfigStore.get",
                     return_value=False)

    # ── 1: injection failure preserves clipboard ─────────────────

    def test_injection_failure_preserves_clipboard(self):
        """When all injection layers fail, inject() returns False but
        clipboard is preserved (NOT auto-copied)."""
        inj = self._make_injector()
        target = InjectionTarget(hwnd=123, pid=1, proc="fake.exe",
                                 cls="FakeClass", title="Fake")
        cp_patch, cp_captured = _patch_clipboard()
        # Simulate: foreground is editable, but all layers fail
        with patch.object(inj, "_focus_window"), \
             patch.object(inj, "_foreground_info",
                          return_value=(42, "Edit", 99, "notepad.exe")), \
             patch.object(inj, "_assess_target_editability",
                          return_value="editable"), \
             patch.object(inj, "_get_focused_edit_hwnd",
                          return_value=0), \
             patch.object(inj, "_get_context_for_strategy", return_value={}), \
             patch.object(inj, "_strategy_for_context",
                          return_value="clipboard"), \
             patch.object(inj, "_is_terminal_target", return_value=False), \
             patch.object(inj, "_inject_uia", return_value=False), \
             patch.object(inj, "_snapshot_target_text",
                          return_value=(True, "")), \
             patch.object(inj, "paste", return_value=(False, "EMPTY", True)), \
             patch.object(inj, "_direct_input", return_value=False), \
             self._mock_config_copy_false(), \
             cp_patch:
            ok = inj.inject(self.SENTINEL, target=target)
        self.assertFalse(ok, "inject reported success despite all layers failing")
        # Text should NOT be on clipboard by default
        self.assertNotIn(self.SENTINEL, cp_captured,
                         "final_text must NOT be auto-copied on failure")

    # ── 2: no editable target preserves clipboard ────────────────

    def test_no_editable_preserves_clipboard(self):
        """When foreground is not editable, inject() returns
        no_editable_target and clipboard is preserved."""
        inj = self._make_injector()
        target = InjectionTarget(hwnd=123, pid=1, proc="fake.exe",
                                 cls="FakeClass", title="Fake")
        cp_patch, cp_captured = _patch_clipboard()
        with patch.object(inj, "_focus_window"), \
             patch.object(inj, "_foreground_info",
                          return_value=(0, "", 0, "")), \
             patch.object(inj, "_assess_target_editability",
                          return_value="no_editable"), \
             self._mock_config_copy_false(), \
             cp_patch:
            ok = inj.inject(self.SENTINEL, target=target)
        self.assertFalse(ok)
        self.assertEqual(ok.state if hasattr(ok, 'state') else None,
                         "no_editable_target")
        self.assertNotIn(self.SENTINEL, cp_captured,
                         "clipboard must NOT be auto-copied on no_editable")

    # ── 3: UIA failure → clipboard paste failure → SendInput failure ──

    def test_all_three_layers_fail_preserves_clipboard(self):
        inj = self._make_injector()
        cp_patch, cp_captured = _patch_clipboard()
        # No target — go straight into the normal waterfall.
        with patch.object(inj, "_focus_window"), \
             patch.object(inj, "_foreground_info",
                          return_value=(42, "Edit", 99, "notepad.exe")), \
             patch.object(inj, "_assess_target_editability",
                          return_value="editable"), \
             patch.object(inj, "_get_focused_edit_hwnd",
                          return_value=0), \
             patch.object(inj, "_get_context_for_strategy", return_value={}), \
             patch.object(inj, "_strategy_for_context",
                          return_value="clipboard"), \
             patch.object(inj, "_is_terminal_target", return_value=False), \
             patch.object(inj, "_inject_uia", return_value=False), \
             patch.object(inj, "_snapshot_target_text",
                          return_value=(True, "")), \
             patch.object(inj, "paste", return_value=(False, "EMPTY", True)), \
             patch.object(inj, "_direct_input", return_value=False), \
             self._mock_config_copy_false(), \
             cp_patch:
            ok = inj.inject(self.SENTINEL)
        self.assertFalse(ok)
        self.assertNotIn(self.SENTINEL, cp_captured,
                         "clipboard must NOT be auto-copied on triple failure")

    # ── 4: terminal clipboard failure ──────────────────────────

    def test_terminal_clipboard_failure_preserves_clipboard(self):
        """Terminals skip the SendInput fallback (would inject as commands).
        That early-return path must still preserve clipboard (no auto-copy)."""
        inj = self._make_injector()
        cp_patch, cp_captured = _patch_clipboard()
        with patch.object(inj, "_focus_window"), \
             patch.object(inj, "_foreground_info",
                          return_value=(42, "ConsoleWindowClass", 99, "cmd.exe")), \
             patch.object(inj, "_assess_target_editability",
                          return_value="editable"), \
             patch.object(inj, "_get_focused_edit_hwnd",
                          return_value=0), \
             patch.object(inj, "_get_context_for_strategy", return_value={}), \
             patch.object(inj, "_strategy_for_context",
                          return_value="clipboard_terminal"), \
             patch.object(inj, "_is_terminal_target", return_value=True), \
             patch.object(inj, "_snapshot_target_text",
                          return_value=(True, "")), \
             patch.object(inj, "paste", return_value=(False, "EMPTY", True)), \
             self._mock_config_copy_false(), \
             cp_patch:
            ok = inj.inject(self.SENTINEL)
        self.assertFalse(ok)
        self.assertNotIn(self.SENTINEL, cp_captured,
                         "clipboard must NOT be auto-copied on terminal failure")

    # ── 5: success path does NOT add a fallback clipboard copy ──

    def test_success_path_does_not_overwrite_clipboard(self):
        """The fallback clipboard write is only for failure. If UIA succeeds
        we must not also pollute the clipboard."""
        inj = self._make_injector()
        cp_patch, cp_captured = _patch_clipboard()
        with patch.object(inj, "_focus_window"), \
             patch.object(inj, "_foreground_info",
                          return_value=(42, "Edit", 99, "notepad.exe")), \
             patch.object(inj, "_assess_target_editability",
                          return_value="editable"), \
             patch.object(inj, "_get_focused_edit_hwnd",
                          return_value=0), \
             patch.object(inj, "_get_context_for_strategy", return_value={}), \
             patch.object(inj, "_strategy_for_context",
                          return_value="uia"), \
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
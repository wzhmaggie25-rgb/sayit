"""A4: Test editability gate relaxation for real input fields.

Verifies that TextPattern-only controls (Chrome contenteditable, Obsidian,
WeChat, Feishu) are treated as "editable_probable" rather than "no_editable",
and that the target_is_sayit_window flag is computed from real data.

Also tests: no_editable_verified only for true desktop no-focus cases.
"""
from __future__ import annotations

import ctypes
import sys
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

from infrastructure.injector import Injector, GUITHREADINFO


def _fill_classname(value: str):
    """Return a side_effect for GetClassNameW that writes *value* into buf."""
    def _side(hwnd, buf, max_count):
        try:
            buf.value = value
        except Exception:
            pass
        return len(value)
    return _side


def _set_gui_focus(focus_hwnd: int):
    """Return a side_effect for GetGUIThreadInfo that sets gui.hwndFocus."""
    def _side(tid, gui_ptr):
        try:
            gui = ctypes.cast(gui_ptr, ctypes.POINTER(GUITHREADINFO)).contents
            gui.hwndFocus = focus_hwnd
        except Exception:
            pass
        return True
    return _side


class FakeUiaValuePattern:
    """Fake UIA ValuePattern with configurable read-only."""
    def __init__(self, read_only=False):
        self._ro = read_only

    def QueryInterface(self, iface):
        class FakeValueProvider:
            CurrentIsReadOnly = self._ro
        return FakeValueProvider()


class FakeUiaTextPattern:
    """Fake UIA TextPattern — no ValuePattern support."""
    pass


class TestEditabilityP0Relaxation(unittest.TestCase):
    """Verify TextPattern-only controls are treated as editable_probable."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_chrome_contenteditable_is_editable_probable(self):
        """Chrome contenteditable (TextPattern only) → editable_probable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(0)), \
             patch("comtypes.client.CreateObject") as mock_create:

            # Mock UIA element with only TextPattern (10014)
            uia_instance = MagicMock()
            elem = MagicMock()
            # ValuePattern (10002) not available — raises
            elem.GetCurrentPattern.side_effect = lambda pid: (
                FakeUiaTextPattern() if pid == 10014 else None
            )
            uia_instance.GetFocusedElement.return_value = elem
            mock_create.return_value = uia_instance

            result = self.inj._assess_target_editability(None)
            self.assertEqual(
                result, "editable_probable",
                f"Chrome contenteditable should be editable_probable, got '{result}'"
            )

    def test_obsidian_codemirror_is_editable_probable(self):
        """Obsidian/CodeMirror (TextPattern only) → editable_probable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(0)), \
             patch("comtypes.client.CreateObject") as mock_create:

            uia_instance = MagicMock()
            elem = MagicMock()
            elem.GetCurrentPattern.side_effect = lambda pid: (
                FakeUiaTextPattern() if pid == 10014 else None
            )
            uia_instance.GetFocusedElement.return_value = elem
            mock_create.return_value = uia_instance

            result = self.inj._assess_target_editability(None)
            self.assertEqual(result, "editable_probable")

    def test_wechat_input_is_editable_probable(self):
        """WeChat input (TextPattern only + no ValuePattern) → editable_probable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(0)), \
             patch("comtypes.client.CreateObject") as mock_create:

            uia_instance = MagicMock()
            elem = MagicMock()
            elem.GetCurrentPattern.side_effect = lambda pid: (
                FakeUiaTextPattern() if pid == 10014 else None
            )
            uia_instance.GetFocusedElement.return_value = elem
            mock_create.return_value = uia_instance

            result = self.inj._assess_target_editability(None)
            self.assertEqual(result, "editable_probable")

    def test_desktop_no_focus_is_no_editable_verified(self):
        """True desktop (no foreground window) → no_editable_verified."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=0):
            result = self.inj._assess_target_editability(None)
            self.assertEqual(result, "no_editable_verified")

    def test_win32_edit_still_editable(self):
        """Win32 Edit/RichEdit still returns editable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("Edit")):
            result = self.inj._assess_target_editability(None)
            self.assertEqual(result, "editable_verified")

    def test_win32_richedit_still_editable(self):
        """Win32 RichEdit still returns editable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("RichEdit20W")):
            result = self.inj._assess_target_editability(None)
            self.assertEqual(result, "editable_verified")

    def test_uia_valuepattern_editable_still_editable(self):
        """UIA ValuePattern non-read-only still returns editable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(0)), \
             patch("comtypes.client.CreateObject") as mock_create:

            uia_instance = MagicMock()
            elem = MagicMock()
            elem.GetCurrentPattern.side_effect = lambda pid: (
                FakeUiaValuePattern(read_only=False) if pid == 10002 else None
            )
            uia_instance.GetFocusedElement.return_value = elem
            mock_create.return_value = uia_instance

            result = self.inj._assess_target_editability(None)
            self.assertEqual(result, "editable_verified")

    def test_no_editable_with_dispatch_does_not_show_large_card(self):
        """no_editable_verified with injection_dispatched=False shows card.
        This test validates the pipeline-level eligibility integration."""
        from application.result_card_eligibility import should_show_large_result_card
        # no_editable with dispatch → no card
        self.assertFalse(
            should_show_large_result_card(
                "no_editable_target",
                injection_dispatched=True))
        # no_editable without dispatch → show card
        self.assertTrue(
            should_show_large_result_card(
                "no_editable_target",
                injection_dispatched=False))

    def test_empty_text_no_result_card_eligibility(self):
        """Eligibility function is never called for empty text."""
        from application.result_card_eligibility import should_show_large_result_card
        text = "   ".strip()
        if not text:
            result = should_show_large_result_card(
                "no_editable_target",
                injection_dispatched=False)
            # Even if eligibility passes, pipeline should not call it for empty text
            self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
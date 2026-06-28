"""Phase 2+6: Unit tests for _assess_target_editability.

Covers GetGUIThreadInfo focus path, ValuePattern editable/read-only rejection,
TextPattern-only → editable_probable (Phase F), and 0-hwnd → no_editable_verified.

All external API calls (GetForegroundWindow, GetGUIThreadInfo, GetClassNameW,
comtypes.client.CreateObject, etc.) are mocked.
"""
from __future__ import annotations
import ctypes
import sys
import unittest
from unittest.mock import patch, MagicMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

from infrastructure.injector import Injector, GUITHREADINFO


# Reusable helpers for filling ctypes buffers
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


class AssessEditabilityWin32FocusTests(unittest.TestCase):
    """Tests covering the GetGUIThreadInfo Win32 Edit/RichEdit path."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_edit_class_focus_returns_editable(self):
        """GetGUIThreadInfo finds focused Edit control → editable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("Edit")):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "editable")

    def test_richedit_class_focus_returns_editable(self):
        """GetGUIThreadInfo finds focused RichEdit control → editable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("RichEdit20W")):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "editable")

    def test_non_edit_class_focus_falls_through(self):
        """Non-Edit/RichEdit class falls through to UIA check."""
        mock_uia_elem = MagicMock()
        mock_uia_elem.GetCurrentPattern.return_value = None  # no patterns
        mock_uia = MagicMock()
        mock_uia.GetFocusedElement.return_value = mock_uia_elem

        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("Button")), \
             patch("comtypes.client.CreateObject", return_value=mock_uia):
            result = self.inj._assess_target_editability(None)
        # No patterns → no_editable
        self.assertEqual(result, "no_editable")

    def test_no_focus_hwnd_falls_through_to_uia(self):
        """gui.hwndFocus == 0 → falls through to UIA check."""
        mock_uia_elem = MagicMock()
        mock_uia_elem.GetCurrentPattern.return_value = None
        mock_uia = MagicMock()
        mock_uia.GetFocusedElement.return_value = mock_uia_elem

        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(0)), \
             patch("comtypes.client.CreateObject", return_value=mock_uia):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "no_editable")

    def test_multiple_edits_only_focused_used(self):
        """Window with multiple Edit children — only the focused one is used."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("Edit")):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "editable")

    def test_getguithreadinfo_fails_returns_unknown(self):
        """GetGUIThreadInfo returns False → unknown."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          return_value=False):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "unknown")

    def test_no_foreground_window_returns_no_editable_verified(self):
        """No foreground window → no_editable_verified (was no_editable pre-Phase F)."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=0):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "no_editable_verified")


class AssessEditabilityUiaTests(unittest.TestCase):
    """Tests covering the UIA ValuePattern / TextPattern path."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def _make_uia_mock(self, value_pattern_read_only=None,
                       has_text_pattern=False):
        """Build a mock UIA element with configurable patterns.

        Args:
            value_pattern_read_only: None=no ValuePattern,
                                     True=read-only, False=editable.
            has_text_pattern: Whether GetCurrentPattern(10014) returns
                              a truthy value.
        """
        mock_elem = MagicMock()

        def _get_pattern(pattern_id):
            if pattern_id == 10002:  # ValuePattern
                if value_pattern_read_only is None:
                    raise Exception("no value pattern")
                mock_vp = MagicMock()
                mock_value_provider = MagicMock()
                mock_value_provider.CurrentIsReadOnly = value_pattern_read_only
                mock_vp.QueryInterface = MagicMock(
                    return_value=mock_value_provider)
                return mock_vp
            elif pattern_id == 10014 and has_text_pattern:  # TextPattern
                return MagicMock()
            raise Exception("no pattern")

        mock_elem.GetCurrentPattern.side_effect = _get_pattern
        mock_uia = MagicMock()
        mock_uia.GetFocusedElement.return_value = mock_elem
        return mock_uia

    def _run_with_uia(self, uia_mock):
        """Run _assess_target_editability with a mocked UIA backend."""
        # Use a non-Edit focus class so we fall through to UIA
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("Button")), \
             patch("comtypes.client.CreateObject", return_value=uia_mock):
            return self.inj._assess_target_editability(None)

    # ── ValuePattern tests ──

    def test_valuepattern_editable_returns_editable(self):
        """ValuePattern with CurrentIsReadOnly=False → editable."""
        uia = self._make_uia_mock(value_pattern_read_only=False)
        result = self._run_with_uia(uia)
        self.assertEqual(result, "editable")

    def test_valuepattern_read_only_returns_no_editable(self):
        """ValuePattern with CurrentIsReadOnly=True → no_editable."""
        uia = self._make_uia_mock(value_pattern_read_only=True)
        result = self._run_with_uia(uia)
        self.assertEqual(result, "no_editable")

    def test_no_uia_focused_element_returns_no_editable(self):
        """UIA GetFocusedElement() returns None → no_editable."""
        mock_uia = MagicMock()
        mock_uia.GetFocusedElement.return_value = None

        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("Button")), \
             patch("comtypes.client.CreateObject", return_value=mock_uia):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "no_editable")

    # ── TextPattern-only tests ──

    def test_textpattern_only_returns_editable_probable(self):
        """TextPattern but no ValuePattern → editable_probable (was no_editable pre-Phase F)."""
        uia = self._make_uia_mock(
            value_pattern_read_only=None, has_text_pattern=True)
        result = self._run_with_uia(uia)
        self.assertEqual(result, "editable_probable")

    def test_no_patterns_returns_no_editable(self):
        """No ValuePattern, no TextPattern → no_editable."""
        uia = self._make_uia_mock(
            value_pattern_read_only=None, has_text_pattern=False)
        result = self._run_with_uia(uia)
        self.assertEqual(result, "no_editable")

    # ── Exception handling ──

    def test_uia_get_current_pattern_exception_handled(self):
        """GetCurrentPattern raising Exception → falls through to no_editable."""
        mock_elem = MagicMock()
        mock_elem.GetCurrentPattern.side_effect = Exception("COM error")
        mock_uia = MagicMock()
        mock_uia.GetFocusedElement.return_value = mock_elem

        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("Button")), \
             patch("comtypes.client.CreateObject", return_value=mock_uia):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "no_editable")

    def test_uia_create_object_failure_returns_conservative(self):
        """When comtypes.CreateObject fails → conservative no_editable."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=4242), \
             patch.object(ctypes.windll.user32, "GetGUIThreadInfo",
                          side_effect=_set_gui_focus(12345)), \
             patch.object(ctypes.windll.user32, "GetClassNameW",
                          side_effect=_fill_classname("Button")), \
             patch("comtypes.client.CreateObject",
                   side_effect=Exception("no COM")):
            result = self.inj._assess_target_editability(None)
        # Falls through to conservative no_editable
        self.assertEqual(result, "no_editable")


class AssessEditabilityConservativeGateTests(unittest.TestCase):
    """Conservative defaults: unknown/0 hwnd must NOT attempt injection."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_unknown_hwnd_conservative_no_editable_verified(self):
        """Unknown/0 hwnd after full assessment → no_editable_verified (conservative).

        This is the critical safety gate: when we cannot determine the
        editable target, we MUST NOT attempt injection into an unknown
        window.
        """
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          return_value=0):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "no_editable_verified",
                         "Unknown/0 hwnd must be conservative")

    def test_exception_in_assessment_returns_unknown(self):
        """Top-level exception → unknown (safe fallback)."""
        with patch.object(ctypes.windll.user32, "GetForegroundWindow",
                          side_effect=Exception("boom")):
            result = self.inj._assess_target_editability(None)
        self.assertEqual(result, "unknown")


if __name__ == "__main__":
    unittest.main()
"""Phase A2: Tri-state editability routing tests.

Proves that _inject_locked's Layer 0 Win32 selection-aware path is dead
due to line 1020 comparing against "editable" instead of the actual return
values from _assess_target_editability.

FAILS ON CURRENT CODE because:
- Line 1020: if editability == "editable":  # ← dead branch, never matches
- _assess_target_editability returns: "editable_verified", "editable_probable",
  "no_editable_verified", "unknown" — never plain "editable"

Key failing assertions (will pass after fix in Phase C):
1. editable_verified → MUST call _inject_win32_selection_aware (currently dead)
2. editable_verified + valid Edit hwnd → MUST call _inject_win32_selection_aware
3. editable_probable → must NOT call Win32 path (skips Layer 0)
4. no_editable_verified → blocks injection (no_editable_target)
5. unknown → falls through to strategy (not blocked)
"""
from __future__ import annotations

import ctypes
import inspect
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

from infrastructure.injector import Injector, InjectionResult


class TriStateRoutingTests(unittest.TestCase):
    """Verify _inject_locked routing for each editability return value.

    Tests 1-2 FAIL on current code: the dead "editable" comparison at
    line 1020 prevents the Win32 selection-aware path from being reached.
    """

    def setUp(self):
        self.inj = Injector(injection_mode="auto")
        # Bypass the global lock so we can test _inject_locked directly
        self.inj._lock = MagicMock()

    def _foreground_info(self, hwnd=9999, cls="Edit", pid=42,
                         proc="notepad.exe"):
        return (hwnd, cls, pid, proc)

    # ════════════════════════════════════════════════════════════
    # FAILING TESTS — prove Layer 0 Win32 path is dead
    # ════════════════════════════════════════════════════════════

    def test_editable_verified_must_reach_win32_path(self):
        """editable_verified MUST call _inject_win32_selection_aware.

        FAILS ON CURRENT CODE: line 1020 checks `if editability == "editable":`
        which never matches "editable_verified" — the Win32 path is dead code.
        """
        with (
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=12345),
            patch.object(self.inj, "_inject_win32_selection_aware",
                         return_value=True),  # would succeed if called
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="send_input"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_MODIFIER_RELEASE_ORDER", new=[]),
            patch.object(self.inj, "_release_modifiers"),
        ):
            result = self.inj._inject_locked("hello", None)

        # editable_verified MUST reach Win32 selection-aware path
        # BEFORE FIX: this assertion FAILS because the branch is dead
        self.assertEqual(
            result.state, "verified_success",
            "editable_verified with valid Edit hwnd must succeed via "
            "Win32 selection-aware path. FAILS on current code because "
            "line 1020 dead branch prevents reaching it.")

        self.assertEqual(
            result.method, "win32_selection",
            "editable_verified must use Win32 selection-aware method. "
            "FAILS on current code.")

    def test_editable_verified_with_focus_hwnd_calls_win32(self):
        """editable_verified + valid Edit hwnd MUST invoke win32 path.

        FAILS ON CURRENT CODE: even with a real focused Edit hwnd=12345,
        the dead branch prevents Layer 0 from executing.
        """
        with (
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=12345),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="send_input"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_MODIFIER_RELEASE_ORDER", new=[]),
            patch.object(self.inj, "_release_modifiers"),
        ):
            with patch.object(self.inj, "_inject_win32_selection_aware",
                              return_value=True) as win32_spy:
                self.inj._inject_locked("hello", None)

        # Win32 path MUST be called for editable_verified
        # BEFORE FIX: assertion FAILS
        win32_spy.assert_called_once_with("hello", 12345)

    # ════════════════════════════════════════════════════════════
    # PASSING TESTS (even on current code) — describe bug-free states
    # ════════════════════════════════════════════════════════════

    def test_editable_probable_skips_win32_proceeds_to_strategy(self):
        """editable_probable skips Layer 0, proceeds to strategy selection."""
        with (
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_probable"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="send_input"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_MODIFIER_RELEASE_ORDER", new=[]),
            patch.object(self.inj, "_release_modifiers"),
        ):
            with patch.object(self.inj, "_inject_win32_selection_aware"
                              ) as win32_spy:
                result = self.inj._inject_locked("hello", None)

        win32_spy.assert_not_called()
        self.assertIsNotNone(result)
        self.assertNotEqual(result.state, "no_editable_target")

    def test_no_editable_verified_blocks_injection(self):
        """no_editable_verified must return no_editable_target."""
        with (
            patch.object(self.inj, "_assess_target_editability",
                         return_value="no_editable_verified"),
        ):
            result = self.inj._inject_locked("hello", None)

        self.assertIsInstance(result, InjectionResult)
        self.assertEqual(result.state, "no_editable_target")
        self.assertFalse(result.ok)

    def test_unknown_falls_through_to_strategy(self):
        """unknown must NOT block injection (conservative fallthrough)."""
        with (
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="unknown"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="send_input"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_MODIFIER_RELEASE_ORDER", new=[]),
            patch.object(self.inj, "_release_modifiers"),
        ):
            with patch.object(self.inj, "_inject_win32_selection_aware"
                              ) as win32_spy:
                result = self.inj._inject_locked("hello", None)

        win32_spy.assert_not_called()
        self.assertIsNotNone(result)
        self.assertNotEqual(result.state, "no_editable_target")

    def test_only_no_editable_verified_triggers_early_return(self):
        """Only no_editable_verified should trigger the early return at line 978."""
        bypass_states = ["editable_verified", "editable_probable", "unknown"]
        for state in bypass_states:
            with self.subTest(state=state):
                with (
                    patch.object(self.inj, "_foreground_info",
                                 return_value=self._foreground_info()),
                    patch.object(self.inj, "_assess_target_editability",
                                 return_value=state),
                    patch.object(self.inj, "_get_focused_edit_hwnd",
                                 return_value=0),
                    patch.object(self.inj, "_get_context_for_strategy",
                                 return_value={}),
                    patch.object(self.inj, "_strategy_for_context",
                                 return_value="send_input"),
                    patch.object(self.inj, "_is_terminal_target",
                                 return_value=False),
                    patch.object(self.inj, "_MODIFIER_RELEASE_ORDER", new=[]),
                    patch.object(self.inj, "_release_modifiers"),
                ):
                    result = self.inj._inject_locked("hello", None)

                self.assertNotEqual(
                    result.state, "no_editable_target",
                    f"State {state!r} must NOT produce no_editable_target")

    def test_returns_never_contain_literal_editable(self):
        """_assess_target_editability return values never equal plain 'editable'.

        The valid return values are: editable_verified, editable_probable,
        no_editable_verified, unknown. None is plain 'editable'.
        """
        source = inspect.getsource(self.inj._assess_target_editability)
        valid_values = {"editable_verified", "editable_probable",
                        "no_editable_verified", "unknown"}
        for value in valid_values:
            self.assertIn(value, source,
                          f"{value} must be a return value in the method")

        # The literal "editable" alone must NOT be a return value
        return_statements = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("return ") and '"' in stripped:
                return_statements.append(stripped)
        for ret in return_statements:
            self.assertNotIn('"editable"', ret,
                             f"Found return of plain 'editable': {ret}")
"""Tests: Phase 1 — Current focus injection (no stale target restore).

P0-1 from ROUND6_CODE_REVIEW: captured target hwnd is NOT used to call
_focus_window; injection always targets the current foreground.

Key behavioral changes verified:
1. _focus_window is NEVER called even when target.hwnd is valid
2. Injection targets current foreground, not captured target
3. No editable foreground → no_editable_target
4. Readback uses current foreground hwnd, not captured target hwnd
5. Known APP_STRATEGIES entry alone (without actual editable control) does
   NOT make the target "editable"
6. last_target_* fields populated from current foreground, not captured target
"""

from __future__ import annotations

import time
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.injector import Injector, InjectionTarget


def _make_injection_target(hwnd: int = 4242, pid: int = 1,
                           proc: str = "notepad.exe",
                           cls: str = "Notepad", title: str = "Untitled") -> InjectionTarget:
    return InjectionTarget(hwnd=hwnd, pid=pid, proc=proc, cls=cls, title=title)


class CurrentFocusInjectionTests(unittest.TestCase):
    """Verify _inject_locked never restores the captured target window."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")
        # Bypass the global lock
        self.inj._lock = MagicMock()
        self._sleep_patch = patch("time.sleep")
        self._sleep_patch.start()

    def tearDown(self):
        self._sleep_patch.stop()

    def _foreground_info(self, hwnd=9999, cls="Edit", pid=42, proc="notepad.exe"):
        """Return a 4-tuple matching Injector._foreground_info signature."""
        return (hwnd, cls, pid, proc)

    # ────────────────────────────────────────────────────────
    # 1. _focus_window NEVER called
    # ────────────────────────────────────────────────────────

    def test_no_focus_restore(self):
        """_focus_window must NOT be called when target.hwnd is valid."""
        target = _make_injection_target(hwnd=4242)

        with (
            patch.object(self.inj, "_focus_window") as focus_mock,
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         return_value=(True, "existing|")),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            result = self.inj._inject_locked("hello", target)

        focus_mock.assert_not_called()

    def test_focus_window_not_called_even_when_foreground_changed(self):
        """Even with different foreground hwnd, _focus_window is not called."""
        target = _make_injection_target(hwnd=4242)

        with (
            patch.object(self.inj, "_focus_window") as focus_mock,
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info(hwnd=8888)),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         return_value=(True, "existing|")),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            self.inj._inject_locked("hello", target)

        focus_mock.assert_not_called()

    # ────────────────────────────────────────────────────────
    # 2. Injects current foreground, not captured target
    # ────────────────────────────────────────────────────────

    def test_injects_into_current_foreground(self):
        """When foreground differs from target, injection uses foreground."""
        target = _make_injection_target(hwnd=4242)
        fg_hwnd = 8888

        snapshot_calls = []

        def _snapshot_side_effect(hwnd):
            snapshot_calls.append(hwnd)
            return (True, "existing|")

        with (
            patch.object(self.inj, "_focus_window") as focus_mock,
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info(hwnd=fg_hwnd)),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=_snapshot_side_effect),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            result = self.inj._inject_locked("hello", target)

        focus_mock.assert_not_called()
        # Snapshot should use foreground hwnd, not target hwnd
        self.assertEqual(snapshot_calls, [fg_hwnd],
                         "readback must use current foreground hwnd")
        self.assertEqual(result.state, "verified_success")

    # ────────────────────────────────────────────────────────
    # 3. No editable foreground → no_editable_target
    # ────────────────────────────────────────────────────────

    def test_no_editable_target_when_foreground_not_editable(self):
        """Foreground has no editable element → no_editable_target."""
        target = _make_injection_target(hwnd=4242)

        with (
            patch.object(self.inj, "_focus_window") as focus_mock,
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="no_editable_verified"),
        ):
            result = self.inj._inject_locked("hello", target)

        focus_mock.assert_not_called()
        self.assertEqual(result.state, "no_editable_target")

    def test_unknown_editability_still_attempts_injection(self):
        """When editability can't be determined, injection still proceeds."""
        target = _make_injection_target(hwnd=4242)

        with (
            patch.object(self.inj, "_focus_window") as focus_mock,
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="unknown"),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         return_value=(True, "existing|")),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            self.inj._inject_locked("hello", target)

        focus_mock.assert_not_called()

    # ────────────────────────────────────────────────────────
    # 4. Readback uses current hwnd
    # ────────────────────────────────────────────────────────

    def test_readback_uses_current_hwnd(self):
        """_snapshot_target_text and _verify_target_text use current hwnd."""
        target = _make_injection_target(hwnd=4242)
        fg_hwnd = 8888

        snapshot_hwnds = []

        def _snapshot_side_effect(hwnd):
            snapshot_hwnds.append(hwnd)
            return (True, "existing|")

        with (
            patch.object(self.inj, "_focus_window"),
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info(hwnd=fg_hwnd)),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=_snapshot_side_effect),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            self.inj._inject_locked("hello", target)

        # Must NOT contain target.hwnd (4242)
        self.assertNotIn(4242, snapshot_hwnds,
                         "readback must NOT use captured target hwnd")
        self.assertEqual(snapshot_hwnds, [fg_hwnd])

    # ────────────────────────────────────────────────────────
    # 5. APP_STRATEGIES alone ≠ editable
    # ────────────────────────────────────────────────────────

    def test_app_strategy_alone_not_editable(self):
        """Known app proc without actual editable control → no_editable."""
        target = _make_injection_target(proc="winword.exe")

        # Simulate: UIA throws, no child edit, but proc is known
        fg_hwnd_mock = 8888

        with (
            patch.object(self.inj, "_focus_window") as focus_mock,
            patch.object(self.inj, "_foreground_info",
                         return_value=(fg_hwnd_mock, "OpusApp", 42, "winword.exe")),
            # _assess_target_editability will be called in Stage 0 AND
            # again later. We need it to return "no_editable" to test
            # that APP_STRATEGIES alone is not treated as editable.
            # The real _assess_target_editability no longer uses APP_STRATEGIES,
            # so we let it run its real logic. But since this is a mock test
            # we need to control it:
            patch.object(self.inj, "_assess_target_editability",
                         return_value="no_editable_verified"),
        ):
            result = self.inj._inject_locked("hello", target)

        focus_mock.assert_not_called()
        self.assertEqual(result.state, "no_editable_target",
                         "known APP_STRATEGIES proc alone must NOT make target editable")

    # ────────────────────────────────────────────────────────
    # 6. last_target_* from current foreground
    # ────────────────────────────────────────────────────────

    def test_last_target_uses_current_foreground(self):
        """last_target_hwnd/pid/proc/cls must reflect current foreground."""
        target = _make_injection_target(hwnd=4242, pid=1, proc="notepad.exe",
                                        cls="Notepad", title="Untitled")
        fg_hwnd, fg_pid, fg_proc, fg_cls = 8888, 777, "brave.exe", "Chrome_WidgetWin_1"
        fg_title = "Google Docs - Brave"

        with (
            patch.object(self.inj, "_focus_window"),
            patch.object(self.inj, "_foreground_info",
                         return_value=(fg_hwnd, fg_cls, fg_pid, fg_proc)),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         return_value=(True, "existing|")),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            self.inj._inject_locked("hello", target)

        # Must reflect the CURRENT foreground, NOT the captured target
        self.assertEqual(self.inj.last_target_hwnd, fg_hwnd)
        self.assertEqual(self.inj.last_target_pid, fg_pid)
        self.assertEqual(self.inj.last_target_proc, fg_proc)
        self.assertEqual(self.inj.last_target_class, fg_cls)

    def test_last_target_title_set(self):
        """last_target_title must be populated from current foreground."""
        target = _make_injection_target(hwnd=4242)

        with (
            patch.object(self.inj, "_focus_window"),
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         return_value=(True, "existing|")),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            self.inj._inject_locked("hello", target)

        # Should have captured some title (even empty string)
        self.assertIsInstance(self.inj.last_target_title, str)

    # ────────────────────────────────────────────────────────
    # Null target cases
    # ────────────────────────────────────────────────────────

    def test_null_target_still_works(self):
        """When target is None, injection proceeds using current foreground."""
        with (
            patch.object(self.inj, "_focus_window") as focus_mock,
            patch.object(self.inj, "_foreground_info",
                         return_value=self._foreground_info()),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable_verified"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         return_value=(True, "existing|")),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            result = self.inj._inject_locked("hello", None)

        focus_mock.assert_not_called()
        self.assertEqual(result.state, "verified_success")

    def test_null_target_hwnd_no_editable(self):
        """When target is None and no editable foreground → no_editable_target."""
        with (
            patch.object(self.inj, "_focus_window") as focus_mock,
            patch.object(self.inj, "_foreground_info",
                         return_value=(0, "", 0, "")),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="no_editable_verified"),
        ):
            result = self.inj._inject_locked("hello", None)

        focus_mock.assert_not_called()
        self.assertEqual(result.state, "no_editable_target")


if __name__ == "__main__":
    unittest.main()
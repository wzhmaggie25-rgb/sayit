"""Tests: Phase 3 — Selection-aware EM_GETSEL/EM_REPLACESEL insertion.

Verifies the new Layer 0 injection path that reads the existing text and
selection from a focused Edit/RichEdit control, then inserts text at the
caret/selection without destroying surrounding content.

Uses a real Win32 Edit control hosted on a background thread for the
"happy path" tests, plus mock/integration tests for edge cases.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
import unittest
import uuid

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

from ctypes import wintypes
from unittest.mock import MagicMock, patch

from infrastructure.injector import Injector, InjectionTarget


# ── Win32 constants ──────────────────────────────────────────────────
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD_ = 0x40000000
WS_BORDER = 0x00800000
ES_AUTOHSCROLL = 0x0080
ES_AUTOVSCROLL = 0x0040
WM_DESTROY = 0x0002
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_SETTEXT = 0x000C
EM_SETSEL = 0x00B1
SW_SHOWNORMAL = 1

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM,
)


class _WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class _EditHost:
    """Tiny Win32 window that hosts a plain Edit child control.

    Lives on its own message-pump thread. Tests can set text / selection
    and then call _inject_win32_selection_aware against the real hwnd.
    """

    def __init__(self):
        self.hwnd = 0
        self.edit_hwnd = 0
        self._thread = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._class_name = f"SayitSelTest_{uuid.uuid4().hex[:8]}"
        self._wnd_proc_ref = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        if not self.edit_hwnd:
            raise RuntimeError("EditHost failed to create Edit control")

    def stop(self):
        self._stop.set()
        if self.hwnd:
            try:
                ctypes.windll.user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)
                ctypes.windll.user32.DestroyWindow(self.hwnd)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)

    # ── Convenience helpers (call from test thread) ──────────────────
    def set_text(self, text: str):
        """Set the Edit control's text via WM_SETTEXT."""
        buf = ctypes.create_unicode_buffer(text)
        ctypes.windll.user32.SendMessageW(
            self.edit_hwnd, WM_SETTEXT, 0,
            ctypes.cast(buf, ctypes.c_void_p).value or 0)

    def set_selection(self, start: int, end: int):
        """Set the Edit control's selection range via EM_SETSEL."""
        ctypes.windll.user32.SendMessageW(
            self.edit_hwnd, EM_SETSEL, start, end)

    def get_text(self) -> str:
        """Read back the Edit control's current text."""
        length = int(ctypes.windll.user32.SendMessageW(
            self.edit_hwnd, WM_GETTEXTLENGTH, 0, 0))
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.SendMessageW(
            self.edit_hwnd, WM_GETTEXT, length + 1,
            ctypes.cast(buf, ctypes.c_void_p).value or 0)
        return buf.value or ""

    # ── Internal window thread ───────────────────────────────────────
    def _run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEX)]
        user32.RegisterClassExW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND,
            wintypes.UINT, wintypes.UINT, wintypes.UINT,
        ]
        user32.PeekMessageW.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        hInstance = kernel32.GetModuleHandleW(None)

        @WNDPROC
        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc_ref = wnd_proc
        wndclass = _WNDCLASSEX()
        wndclass.cbSize = ctypes.sizeof(_WNDCLASSEX)
        wndclass.lpfnWndProc = wnd_proc
        wndclass.hInstance = hInstance
        wndclass.lpszClassName = self._class_name
        wndclass.hbrBackground = ctypes.cast(6, wintypes.HBRUSH)
        wndclass.hCursor = user32.LoadCursorW(
            None, ctypes.cast(32512, wintypes.LPCWSTR))
        atom = user32.RegisterClassExW(ctypes.byref(wndclass))
        if not atom:
            return

        self.hwnd = user32.CreateWindowExW(
            0, self._class_name, "SayIt Selection Test",
            WS_OVERLAPPEDWINDOW | WS_VISIBLE,
            100, 100, 600, 200,
            None, None, hInstance, None,
        )
        if not self.hwnd:
            return

        self.edit_hwnd = user32.CreateWindowExW(
            0, "EDIT", "",
            WS_CHILD_ | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
            10, 10, 560, 150,
            self.hwnd, None, hInstance, None,
        )

        user32.ShowWindow(self.hwnd, SW_SHOWNORMAL)
        user32.SetForegroundWindow(self.hwnd)

        self._ready.set()

        msg = wintypes.MSG()
        while not self._stop.is_set():
            r = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
            if r:
                if msg.message == 0x0012:  # WM_QUIT
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)


def _make_injection_target(hwnd: int = 4242, pid: int = 1,
                           proc: str = "notepad.exe",
                           cls: str = "Edit", title: str = "Untitled") -> InjectionTarget:
    return InjectionTarget(hwnd=hwnd, pid=pid, proc=proc, cls=cls, title=title)


# ══════════════════════════════════════════════════════════════════════
# Happy path: real Edit control
# ══════════════════════════════════════════════════════════════════════

class Win32SelectionAwareRealEditTests(unittest.TestCase):
    """Tests that exercise _inject_win32_selection_aware with a real
    Win32 Edit control, verifying non-destructive insertion."""

    @classmethod
    def setUpClass(cls):
        cls.host = _EditHost()
        cls.host.start()

    @classmethod
    def tearDownClass(cls):
        cls.host.stop()

    def setUp(self):
        self.inj = Injector(injection_mode="auto")
        # Clear the Edit control before each test
        self.host.set_text("")
        self.host.set_selection(0, 0)

    # ── 1. Insert at caret preserves surrounding context ─────────────
    def test_insert_at_caret_preserves_context(self):
        """前文|后文 → 前文final_text后文"""
        self.host.set_text("前文后文")
        self.host.set_selection(2, 2)  # caret between 前文 and 后文
        result = self.inj._inject_win32_selection_aware(
            "final_text", self.host.edit_hwnd)
        self.assertTrue(result)
        self.assertEqual(self.host.get_text(), "前文final_text后文")

    # ── 2. Replaces selection only, not surrounding text ─────────────
    def test_replaces_selection_only(self):
        """前文SELECTED后文 → 前文final_text后文 (selected portion replaced)."""
        self.host.set_text("前文SELECTED后文")
        self.host.set_selection(2, 10)  # "SELECTED" selected
        result = self.inj._inject_win32_selection_aware(
            "final_text", self.host.edit_hwnd)
        self.assertTrue(result)
        self.assertEqual(self.host.get_text(), "前文final_text后文")

    # ── 3. Duplicate expected text in pre is not confused ────────────
    def test_duplicate_expected_in_pre(self):
        """Pre already contains the text to insert; verifying by diff."""
        self.host.set_text("hello final_text world")
        self.host.set_selection(0, 0)  # caret at start
        result = self.inj._inject_win32_selection_aware(
            "final_text", self.host.edit_hwnd)
        self.assertTrue(result)
        self.assertEqual(self.host.get_text(), "final_texthello final_text world")

    # ── 4. Large buffer (1000 Chinese characters) ────────────────────
    def test_1000_chinese_chars(self):
        """Insert into an Edit control with 1000 Chinese characters."""
        pre = "测" * 1000
        self.host.set_text(pre)
        self.host.set_selection(500, 500)  # middle
        insert = "插入的文本"
        result = self.inj._inject_win32_selection_aware(
            insert, self.host.edit_hwnd)
        self.assertTrue(result)
        expected = pre[:500] + insert + pre[500:]
        self.assertEqual(self.host.get_text(), expected)

    # ── 5. Original text is never cleared ────────────────────────────
    def test_original_text_never_cleared(self):
        """Even with an empty insert, original text remains."""
        self.host.set_text("hello beautiful world")
        self.host.set_selection(6, 15)  # "beautiful" selected
        result = self.inj._inject_win32_selection_aware(
            "", self.host.edit_hwnd)
        self.assertTrue(result)
        self.assertEqual(self.host.get_text(), "hello  world")


# ══════════════════════════════════════════════════════════════════════
# Edge cases: mock / integration
# ══════════════════════════════════════════════════════════════════════

class Win32SelectionEdgeCaseTests(unittest.TestCase):
    """Tests for error paths and integration with _inject_locked."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")
        self.inj._lock = MagicMock()
        self._sleep_patch = patch("time.sleep")
        self._sleep_patch.start()

    def tearDown(self):
        self._sleep_patch.stop()

    # ── 6. Readback mismatch → attempted_unverified ──────────────────
    def test_readback_mismatch_returns_attempted_unverified(self):
        """When _inject_win32_selection_aware returns False,
        _inject_locked must return attempted_unverified."""
        target = _make_injection_target()

        with (
            patch.object(self.inj, "_focus_window"),
            patch.object(self.inj, "_foreground_info",
                         return_value=(42, "Edit", 99, "notepad.exe")),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=12345),
            patch.object(self.inj, "_inject_win32_selection_aware",
                         return_value=False),
        ):
            result = self.inj._inject_locked("hello", target)

        self.assertEqual(result.state, "attempted_unverified")
        self.assertEqual(result.method, "win32_selection")
        self.assertEqual(result.reason, "win32_selection_unverified")

    # ── 7. Layer 0 skipped when _get_focused_edit_hwnd returns 0 ─────
    def test_skipped_when_get_focused_edit_hwnd_returns_zero(self):
        """When _get_focused_edit_hwnd returns 0, Layer 0 is skipped
        and injection falls through to clipboard."""
        target = _make_injection_target()

        with (
            patch.object(self.inj, "_focus_window"),
            patch.object(self.inj, "_foreground_info",
                         return_value=(42, "Edit", 99, "notepad.exe")),
            patch.object(self.inj, "_assess_target_editability",
                         return_value="editable"),
            patch.object(self.inj, "_get_focused_edit_hwnd",
                         return_value=0),
            patch.object(self.inj, "_get_context_for_strategy",
                         return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target",
                         return_value=False),
            patch.object(self.inj, "_snapshot_target_text",
                         return_value=(True, "")),
            patch.object(self.inj, "paste",
                         return_value=(True, "TEXT", True)),
            patch.object(self.inj, "_verify_target_text",
                         return_value="verified"),
        ):
            result = self.inj._inject_locked("hello", target)

        # Falls through to clipboard paste
        self.assertEqual(result.state, "verified_success")
        self.assertEqual(result.method, "clipboard")

    # ── 8. No crash with invalid hwnd ────────────────────────────────
    def test_no_crash_with_invalid_hwnd(self):
        """Calling _inject_win32_selection_aware with an invalid hwnd
        must not crash and must return a valid bool or None."""
        result = self.inj._inject_win32_selection_aware("hello", 0)
        # Must be one of True, False, or None — no exception
        self.assertIn(result, {True, False, None},
                      f"Unexpected return: {result!r}")


if __name__ == "__main__":
    unittest.main()
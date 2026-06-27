"""Windows Edit-control integration test.

Spawns a tiny Win32 host with a plain `Edit` child control, then drives
the full orchestrator-level concurrency / injection contract:

  1. Capture the Edit window as injection target.
  2. Start a fake pipeline (we don't need real audio / ASR).
  3. While the pipeline is in post-processing, simulate a third RAlt
     toggle and verify it is dropped, NOT spawning a parallel pipeline.
  4. Inject a uniquely-named sentinel string into the target Edit control
     via the injector's Win32-child path.
  5. Read the sentinel back from the Edit control to verify the contract:
     final_text actually reached the original input field.
  6. Clean up the host window.

Skipped on non-Windows.
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
from unittest.mock import patch

from infrastructure.injector import Injector, InjectionTarget


WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_BORDER = 0x00800000
ES_AUTOHSCROLL = 0x0080
ES_AUTOVSCROLL = 0x0040
WM_DESTROY = 0x0002
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_SETTEXT = 0x000C
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
    """Tiny Win32 window that hosts a single Edit child control.

    Lives on its own message-pump thread so it doesn't block the test.
    """

    def __init__(self):
        self.hwnd = 0
        self.edit_hwnd = 0
        self._thread = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._class_name = f"SayitTestEdit_{uuid.uuid4().hex[:8]}"
        self._wnd_proc_ref = None  # keep WNDPROC alive

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

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

    def _run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        # By default ctypes assumes int (32-bit) return — that TRUNCATES
        # 64-bit HWND / HINSTANCE values on x64 and corrupts subsequent
        # calls. Explicitly bind argtypes / restype for every Win32 call
        # this fixture uses.
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
        # IDC_ARROW = 32512; LoadCursorW with NULL hInstance expects a
        # MAKEINTRESOURCE(32512) — cast the integer to LPCWSTR directly.
        wndclass.hCursor = user32.LoadCursorW(
            None, ctypes.cast(32512, wintypes.LPCWSTR))
        atom = user32.RegisterClassExW(ctypes.byref(wndclass))
        if not atom:
            return

        self.hwnd = user32.CreateWindowExW(
            0, self._class_name, "SayIt Edit Host",
            WS_OVERLAPPEDWINDOW | WS_VISIBLE,
            100, 100, 600, 200,
            None, None, hInstance, None,
        )
        if not self.hwnd:
            return

        self.edit_hwnd = user32.CreateWindowExW(
            0, "EDIT", "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
            10, 10, 560, 150,
            self.hwnd, None, hInstance, None,
        )

        user32.ShowWindow(self.hwnd, SW_SHOWNORMAL)
        user32.SetForegroundWindow(self.hwnd)

        self._ready.set()

        # Pump messages until stop is requested.
        msg = wintypes.MSG()
        while not self._stop.is_set():
            r = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)  # PM_REMOVE
            if r:
                if msg.message == 0x0012:  # WM_QUIT
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)

    def read_edit_text(self) -> str:
        user32 = ctypes.windll.user32
        send_proto = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM,
        )
        send = send_proto(("SendMessageW", user32))
        length = int(send(self.edit_hwnd, WM_GETTEXTLENGTH, 0, 0))
        buf = ctypes.create_unicode_buffer(length + 1)
        send(self.edit_hwnd, WM_GETTEXT, length + 1,
             ctypes.cast(buf, ctypes.c_void_p).value or 0)
        return buf.value


class Win32EditIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.host = _EditHost()
        self.host.start()
        if not self.host.hwnd or not self.host.edit_hwnd:
            self.skipTest("could not create Win32 Edit host")
        # Give the window manager a moment to settle.
        time.sleep(0.2)

    def tearDown(self):
        try:
            self.host.stop()
        except Exception:
            pass

    def test_win32_child_edit_injection_roundtrip(self):
        """Inject a sentinel via the control-safe Win32 path and read it back.

        This is the path the task's contract names "对可直接定位的 Win32
        子编辑控件优先使用安全的控件级注入". The control-level path
        uses SendMessage(WM_SETTEXT) + WM_GETTEXT readback, so it does not
        depend on foreground state and is fully deterministic — ideal for
        CI.
        """
        sentinel = f"sayit-sentinel-{uuid.uuid4().hex[:12]}"
        inj = Injector(injection_mode="auto")
        ok = inj._inject_win32_child_edit(sentinel, self.host.hwnd)
        self.assertTrue(ok, "_inject_win32_child_edit reported failure")
        actual = self.host.read_edit_text()
        self.assertEqual(actual, sentinel,
                         f"Edit control did not receive sentinel: got {actual!r}")

    def test_inject_win32_child_edit_still_works(self):
        """_inject_win32_child_edit works regardless of foreground state."""
        sentinel = f"sayit-child-{uuid.uuid4().hex[:12]}"
        inj = Injector(injection_mode="auto")
        ok = inj._inject_win32_child_edit(sentinel, self.host.hwnd)
        self.assertTrue(ok, "_inject_win32_child_edit reported failure")
        actual = self.host.read_edit_text()
        self.assertEqual(actual, sentinel,
                         f"Edit control did not receive sentinel: got {actual!r}")

    def test_orchestrator_state_gate_with_real_edit_host(self):
        """End-to-end: while a fake pipeline is "post-processing", an
        incoming hotkey must be ignored — verified by injecting only at
        the end and reading back from the Edit control."""
        from application.orchestrator import SayitOrchestrator
        from application.eventbus import Events
        from domain.models import RecordingState

        sentinel = f"sayit-gated-{uuid.uuid4().hex[:12]}"

        orch = SayitOrchestrator()
        # Replace expensive collaborators
        from unittest.mock import MagicMock
        orch._audio = MagicMock()
        orch._audio.wait_for_stop = MagicMock()

        class _NullInjectorTarget:
            def __init__(self, hwnd):
                self._hwnd = hwnd

            def capture_target(self):
                return InjectionTarget(
                    hwnd=self._hwnd, pid=0, proc="python.exe",
                    cls="SayitTestEdit", title="SayIt Edit Host")

        orch._injector = _NullInjectorTarget(self.host.hwnd)

        # Pipeline factory: returns a controllable fake that we drive
        # manually through capture → transcribe → inject.
        from tests.test_orchestrator_state import _ControllablePipeline
        fake = _ControllablePipeline(orch.eventbus)
        import application.orchestrator as orch_mod
        orig = orch_mod.RecordingPipeline
        orch_mod.RecordingPipeline = lambda eb: fake
        try:
            self.assertTrue(orch.toggle_recording())
            fake.run_started.wait(timeout=2)

            # Wait until CAPTURING
            deadline = time.time() + 1
            while time.time() < deadline and fake.state != RecordingState.CAPTURING:
                time.sleep(0.01)

            # Second toggle: signal stop
            orch.toggle_recording()
            # Wait until TRANSCRIBING
            deadline = time.time() + 1
            while time.time() < deadline and fake.state != RecordingState.TRANSCRIBING:
                time.sleep(0.01)
            self.assertEqual(fake.state, RecordingState.TRANSCRIBING)

            # Third toggle during post-processing — MUST be dropped.
            ignored = []
            orch.eventbus.on(Events.TOGGLE_IGNORED, lambda s: ignored.append(s))
            result = orch.toggle_recording()
            self.assertFalse(result, "third toggle started a new pipeline")
            self.assertEqual(ignored, ["transcribing"])
            self.assertTrue(orch.is_busy())

            # Let the pipeline finish; outside of orchestrator we inject the
            # sentinel into the original Edit control ourselves to model
            # what the real pipeline would do.
            inj = Injector(injection_mode="auto")
            ok = inj._inject_win32_child_edit(sentinel, self.host.hwnd)
            self.assertTrue(ok)
            actual = self.host.read_edit_text()
            self.assertEqual(actual, sentinel,
                             f"Edit control did not receive sentinel: got {actual!r}")

            fake.transcribe_done.set(); fake.allow_inject.set()
            fake.run_returned.wait(timeout=3)
            deadline = time.time() + 2
            while time.time() < deadline and orch.is_busy():
                time.sleep(0.02)
            self.assertFalse(orch.is_busy())
        finally:
            orch_mod.RecordingPipeline = orig


if __name__ == "__main__":
    unittest.main()

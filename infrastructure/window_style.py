"""Frameless acrylic window styling via DWM / Win32 API.

Applied after the window is created to achieve:
- Rounded corners (Win11) or SetWindowRgn (Win10 fallback)
- Acrylic / Mica backdrop
- Frameless drag support
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes


def apply_rounded_corners():
    """Apply DWM rounded corners to the foreground window (Win11 22H2+)."""
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 2

    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return False
    try:
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(wintypes.DWORD(DWMWCP_ROUND)),
            ctypes.sizeof(wintypes.DWORD),
        )
        return result == 0
    except OSError:
        return False


def apply_acrylic(hwnd: int = None) -> bool:
    """Apply acrylic/frosted glass backdrop via DWM."""
    if hwnd is None:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return False

    # Extend frame into client area first
    MARGINS = ctypes.c_int * 4
    margins = MARGINS(-1, -1, -1, -1)
    try:
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
            wintypes.HWND(hwnd), margins)
    except OSError:
        return False

    # Try DWM system backdrop (Win11)
    DWMWA_SYSTEMBACKDROP_TYPE = 38
    DWMSBT_ACRYLIC = 4
    try:
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
            ctypes.byref(wintypes.DWORD(DWMSBT_ACRYLIC)),
            ctypes.sizeof(wintypes.DWORD),
        )
        if result == 0:
            return True
    except OSError:
        pass

    # Fallback: SetWindowCompositionAttribute (Win10)
    return _apply_accent_policy(hwnd)


def _apply_accent_policy(hwnd: int) -> bool:
    """Win10 fallback: SetWindowCompositionAttribute with acrylic blur."""
    user32 = ctypes.windll.user32

    class ACCENTPOLICY(ctypes.Structure):
        _fields_ = [
            ("AccentState", ctypes.c_int),
            ("AccentFlags", ctypes.c_int),
            ("GradientColor", ctypes.c_int),
            ("AnimationId", ctypes.c_int),
        ]

    class WINCOMPATTRDATA(ctypes.Structure):
        _fields_ = [
            ("Attribute", ctypes.c_int),
            ("Data", ctypes.POINTER(ACCENTPOLICY)),
            ("SizeOfData", ctypes.c_size_t),
        ]

    ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
    policy = ACCENTPOLICY(ACCENT_ENABLE_ACRYLICBLURBEHIND, 2, 0, 0)
    data = WINCOMPATTRDATA(19, ctypes.pointer(policy), ctypes.sizeof(policy))

    try:
        return user32.SetWindowCompositionAttribute(
            wintypes.HWND(hwnd), ctypes.pointer(data)) != 0
    except OSError:
        return False


def apply_window_style():
    """Apply all window styling: rounded corners + acrylic if available."""
    rc = apply_rounded_corners()
    ac = apply_acrylic()
    return {"rounded": rc, "acrylic": ac}

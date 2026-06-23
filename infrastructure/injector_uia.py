"""UIA injection helpers — ValuePattern, TextPattern, and MSAA read-back."""
from __future__ import annotations
import ctypes
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class FocusedElementSnapshot(dict):
    """JSON-friendly focused element metadata."""


def get_focused_element_snapshot(timeout: float = 0.2) -> FocusedElementSnapshot:
    """Return Typeless-style focused control metadata via UIA.

    Reference: focus_context.js getFocusedInputInfo captures element
    capabilities separately from text state before composing input_info.
    """
    result: dict = {}

    def _read():
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            uia = comtypes.client.CreateObject(
                "{ff48dba4-60ef-4201-aa87-54103eef594e}")
            element = uia.GetFocusedElement()
            if element is None:
                result.update({"editable": False})
                return
            role = _safe_uia_property(element, "CurrentControlTypeName")
            if not role:
                role = str(_safe_uia_property(element, "CurrentControlType") or "")
            result.update({
                "editable": _has_pattern(element, 10002) or _has_pattern(element, 10014),
                "role": role,
                "name": _safe_uia_property(element, "CurrentName") or "",
                "automation_id": _safe_uia_property(element, "CurrentAutomationId") or "",
                "class_name": _safe_uia_property(element, "CurrentClassName") or "",
                "bounds": _uia_bounds(element),
            })
        except Exception as e:
            logger.debug("UIA focused element snapshot failed: %s", e)

    thread = threading.Thread(target=_read, daemon=True, name="uia-focus-snapshot")
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        logger.debug("UIA focused element snapshot timed out after %.2fs", timeout)
        return FocusedElementSnapshot()
    return FocusedElementSnapshot(result)


def read_focus_text() -> Optional[str]:
    """Read text from the currently focused control via UIA/MSAA.

    Try three methods in order:
    1. UIA ValuePattern (standard edit controls)
    2. UIA TextPattern (rich text editors)
    3. MSAA get_accValue (legacy controls)
    """
    text = _read_via_uia_value()
    if text is not None:
        return text
    text = _read_via_uia_text()
    if text is not None:
        return text
    return _read_via_msaa()


def _read_via_uia_value() -> Optional[str]:
    """Read via UIA ValuePattern (standard input fields)."""
    try:
        import comtypes.client
        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}")
        element = uia.GetFocusedElement()
        if element is None:
            return None
        pattern = element.GetCurrentPattern(10002)
        if pattern is None:
            return None
        return pattern.CurrentValue
    except Exception:
        return None


def _read_via_uia_text() -> Optional[str]:
    """Read via UIA TextPattern (rich text editors)."""
    try:
        import comtypes.client
        uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}")
        element = uia.GetFocusedElement()
        if element is None:
            return None
        tp = element.GetCurrentPattern(10014)
        if tp is None:
            return None
        return tp.DocumentRange.GetText(500)
    except Exception:
        return None


def _read_via_msaa() -> Optional[str]:
    """Read via MSAA AccessibleObjectFromWindow (legacy fallback)."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        obj = ctypes.c_void_p()
        iid = (ctypes.c_ubyte * 16)(*bytes.fromhex(
            "618e9f8c30d1cf118cb700c04fd4d15f"))
        hr = ctypes.windll.oleacc.AccessibleObjectFromWindow(
            hwnd, 0xFFFFFFFC, ctypes.byref(iid), ctypes.byref(obj))
        if hr != 0 or not obj:
            return None
        import comtypes
        child = obj.QueryInterface(comtypes.gen.Accessibility.IAccessible)
        if child:
            val = child.get_accValue(ctypes.c_ulong(0))
            return str(val) if val else None
    except Exception:
        return None


def _has_pattern(element, pattern_id: int) -> bool:
    try:
        return element.GetCurrentPattern(pattern_id) is not None
    except Exception:
        return False


def _safe_uia_property(element, name: str):
    try:
        return getattr(element, name)
    except Exception:
        return None


def _uia_bounds(element) -> dict:
    try:
        rect = element.CurrentBoundingRectangle
        left = int(getattr(rect, "left", 0))
        top = int(getattr(rect, "top", 0))
        right = int(getattr(rect, "right", left))
        bottom = int(getattr(rect, "bottom", top))
        return {
            "x": left,
            "y": top,
            "width": max(0, right - left),
            "height": max(0, bottom - top),
        }
    except Exception:
        return {"x": 0, "y": 0, "width": 0, "height": 0}

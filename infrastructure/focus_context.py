"""Focused input context for Typeless-style track edit learning."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
from dataclasses import dataclass, asdict
import logging
import os
import re
import threading
import time
from typing import Optional

from infrastructure.context_helper_client import ContextHelperClient
from infrastructure.context_helper_dll import ContextHelperDll
from infrastructure.injector_uia import get_focused_element_snapshot, read_focus_text

# PortAudio heap corruption guard: once PortAudio has been used, loading
# UIAutomationCore in a new thread (e.g. ContextHelperDLL) can trigger
# STATUS_DLL_INIT_FAILED.  See infrastructure/audio_capture.py docstring.
try:
    from infrastructure.audio_capture import was_portaudio_used
except ImportError:
    def was_portaudio_used() -> bool:
        return False

logger = logging.getLogger(__name__)

TERMINAL_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty"}
TERMINAL_PROCS = {
    "windowsterminal.exe", "wt.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "conhost.exe", "mintty.exe", "xshell.exe", "xshellcore.exe", "warp.exe",
}

_last_focused_lock = threading.RLock()
_last_focused_start_time = 0
_last_focused_end_time = 0
_last_focused_context: Optional["FocusContext"] = None


@dataclass
class AppInfo:
    app_name: str = ""
    app_identifier: str = ""
    window_title: str = ""
    window_position: dict = None
    app_type: str = "native_app"
    app_metadata: dict = None
    browser_context: dict = None
    hwnd: int = 0
    process_id: int = 0
    window_class: str = ""

    def __post_init__(self):
        if self.window_position is None:
            self.window_position = {"x": 0, "y": 0, "width": 0, "height": 0}
        if self.app_metadata is None:
            self.app_metadata = {
                "process_id": self.process_id,
                "app_path": "",
                "window_id": self.hwnd,
            }


@dataclass
class InputCapabilities:
    is_editable: bool = False
    supports_markdown: bool = False
    dom_id: str = ""
    dom_classes: str = ""


@dataclass
class CursorState:
    cursor_position: int = -1
    has_text_selected: bool = False
    selected_text: str = ""
    text_before_cursor: str = ""
    text_after_cursor: str = ""
    full_field_content: str = ""


@dataclass
class InputInfo:
    input_area_type: str = "text_field"
    accessibility_role: str = ""
    position_on_screen: dict = None
    input_capabilities: InputCapabilities = None
    cursor_state: CursorState = None
    surrounding_context: dict = None

    def __post_init__(self):
        if self.position_on_screen is None:
            self.position_on_screen = {"x": 0, "y": 0, "width": 0, "height": 0}
        if self.input_capabilities is None:
            self.input_capabilities = InputCapabilities()
        if self.cursor_state is None:
            self.cursor_state = CursorState()
        if self.surrounding_context is None:
            self.surrounding_context = {
                "text_before_input_area": "",
                "text_after_input_area": "",
            }


@dataclass
class FocusContext:
    active_application: AppInfo
    text_insertion_point: InputInfo
    input_box_identifier: str

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_track_text(value: str) -> str:
    return re.sub(r"[\r\n\u200b\u200c\u200d\u200e\u200f\ufeff]", "", value or "")


def normalize_terminal_track_text(value: str) -> str:
    value = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]", "", value or "")
    return re.sub(r"\s+", "", value)


def includes_inserted_text(full_text: str, inserted_text: str) -> bool:
    return normalize_track_text(inserted_text) in normalize_track_text(full_text)


def includes_terminal_inserted_text(full_text: str, inserted_text: str) -> bool:
    full_norm = normalize_terminal_track_text((full_text or "")[-12000:])
    inserted_norm = normalize_terminal_track_text(inserted_text)
    return bool(inserted_norm and inserted_norm in full_norm)


def is_terminal_app(app: AppInfo) -> bool:
    return (app.app_name or "").lower() in TERMINAL_PROCS or app.window_class in TERMINAL_CLASSES


def split_inserted_text(full_text: str, inserted_text: str) -> tuple[str, str] | None:
    """Return text before/after the last occurrence of inserted_text in full_text."""
    full_norm = normalize_track_text(full_text)
    inserted_norm = normalize_track_text(inserted_text)
    if not inserted_norm:
        return None
    idx = full_norm.rfind(inserted_norm)
    if idx < 0:
        return None
    return full_norm[:idx], full_norm[idx + len(inserted_norm):]


def extract_inserted_region(full_text: str, before: str, after: str) -> Optional[str]:
    """Extract the edited inserted region using stable before/after anchors."""
    full_norm = normalize_track_text(full_text)
    before = normalize_track_text(before)
    after = normalize_track_text(after)
    start = 0
    if before:
        before_idx = full_norm.find(before)
        if before_idx < 0:
            return None
        start = before_idx + len(before)
    end = len(full_norm)
    if after:
        after_idx = full_norm.find(after, start)
        if after_idx < 0:
            return None
        end = after_idx
    if end < start:
        return None
    return full_norm[start:end]


def split_terminal_inserted_text(full_text: str, inserted_text: str) -> tuple[str, str] | None:
    full_tail = full_text[-12000:] if full_text else ""
    if not includes_terminal_inserted_text(full_tail, inserted_text):
        return None
    split = split_inserted_text(full_tail, inserted_text)
    if split:
        return split
    return "", ""


def get_focus_context(
    inserted_text: str = "",
    *,
    update_last_focused: bool = True,
) -> Optional[FocusContext]:
    # Reference: reference/focus_context.js lines 6359-6384.
    start_time = _now_ms()

    # ── Path 1: Native exe (JSON-RPC subprocess, process-isolated — Typeless aligned)
    native_context = _get_focus_context_native(inserted_text)
    if native_context is not None:
        if update_last_focused:
            _remember_focus_context(native_context, start_time, _now_ms())
        return native_context

    # ── Path 2: In-process DLL (fallback — may cause heap corruption with PortAudio)
    if not was_portaudio_used():
        dll_context = _get_focus_context_via_dll(0, inserted_text)
        if dll_context is not None:
            if update_last_focused:
                _remember_focus_context(dll_context, start_time, _now_ms())
            return dll_context
    else:
        logger.debug("get_focus_context: PortAudio was used, skipping in-process DLL")

    # ── Path 3: Python UIA + Win32 (pure Python fallback)
    python_context = _get_focus_context_python(inserted_text)
    if update_last_focused:
        _remember_focus_context(python_context, start_time, _now_ms())
    return python_context


def get_focus_context_for_window(
    hwnd: int,
    inserted_text: str = "",
    *,
    update_last_focused: bool = True,
) -> Optional[FocusContext]:
    if not hwnd:
        return None
    start_time = _now_ms()

    # ── Path 1: Win32 child-edit (fast, works for native edit controls)
    win32_context = _get_focus_context_for_window_win32(hwnd, inserted_text)
    if (
        win32_context is not None
        and win32_context.text_insertion_point.input_capabilities.is_editable
    ):
        if update_last_focused:
            _remember_focus_context(win32_context, start_time, _now_ms())
        return win32_context

    # ── Path 2: Native exe (JSON-RPC subprocess, process-isolated — Typeless aligned)
    native_raw = ContextHelperClient().get_full_context_for_window(hwnd)
    native_context = _map_native_context(native_raw, inserted_text)
    if native_context is not None:
        native_text = native_context.text_insertion_point.cursor_state.full_field_content
        native_contains = (
            includes_terminal_inserted_text(native_text, inserted_text)
            if is_terminal_app(native_context.active_application)
            else includes_inserted_text(native_text, inserted_text)
        )
        if not inserted_text or native_contains:
            if update_last_focused:
                _remember_focus_context(native_context, start_time, _now_ms())
            return native_context
        # EXE returned a context but the just-pasted text hasn't rendered in
        # the UIA tree yet (e.g. Electron/Chrome delayed update).  Instead of
        # falling through to the in-process DLL (which can crash with PortAudio),
        # return None — the caller (SilentMonitor._start_track) will retry.
        logger.debug("get_focus_context_for_window: EXE returned context but text not yet visible; "
                     "returning None for retry")
        return None

    # ── Path 3: In-process DLL (fallback — may cause heap corruption with PortAudio)
    # Skip this path entirely once PortAudio has been used, since loading
    # UIAutomationCore in a new thread can trigger STATUS_DLL_INIT_FAILED.
    if not was_portaudio_used():
        dll_context = _get_focus_context_via_dll(hwnd, inserted_text)
        if dll_context is not None:
            if update_last_focused:
                _remember_focus_context(dll_context, start_time, _now_ms())
            return dll_context
    else:
        logger.debug("get_focus_context_for_window: PortAudio was used, skipping in-process DLL")

    # ── Path 4: Win32 context (even if not editable, last resort)
    if update_last_focused:
        _remember_focus_context(win32_context, start_time, _now_ms())
    return win32_context


def execute_last_focused_info_task(inserted_text: str = "") -> dict:
    """Refresh and return cached focus info, matching Typeless' polling task shape."""
    get_focus_context(inserted_text, update_last_focused=True)
    return get_last_focused_info()


def get_last_focus_context() -> Optional[FocusContext]:
    with _last_focused_lock:
        return _last_focused_context


def get_last_focused_info() -> dict:
    # Reference: reference/focus_context.js lines 6409-6415.
    with _last_focused_lock:
        context = _last_focused_context
        app_info = context.active_application if context else AppInfo()
        input_info = context.text_insertion_point if context else InputInfo()
        return {
            "startTime": _last_focused_start_time,
            "endTime": _last_focused_end_time,
            "appInfo": asdict(app_info),
            "inputInfo": asdict(input_info),
        }


def _now_ms() -> int:
    return int(time.time() * 1000)


def _remember_focus_context(
    context: Optional[FocusContext],
    start_time: int,
    end_time: int,
):
    if context is None:
        return
    global _last_focused_start_time, _last_focused_end_time, _last_focused_context
    with _last_focused_lock:
        _last_focused_start_time = int(start_time)
        _last_focused_end_time = int(end_time)
        _last_focused_context = context


def _reset_last_focused_info():
    """Test helper; production code should refresh via execute_last_focused_info_task."""
    global _last_focused_start_time, _last_focused_end_time, _last_focused_context
    with _last_focused_lock:
        _last_focused_start_time = 0
        _last_focused_end_time = 0
        _last_focused_context = None


def _get_focus_context_for_window_win32(hwnd: int, inserted_text: str = "") -> Optional[FocusContext]:
    try:
        if not ctypes.windll.user32.IsWindow(hwnd):
            return None
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title_buf = ctypes.create_unicode_buffer(512)
        class_buf = ctypes.create_unicode_buffer(256)
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 512)
        ctypes.windll.user32.GetClassNameW(hwnd, class_buf, 256)
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))

        proc, proc_path = _process_info(pid.value)
        window_title = title_buf.value or ""
        browser_context = _browser_context(proc, window_title)
        app = AppInfo(
            app_name=proc,
            app_identifier=proc,
            window_title=window_title,
            window_position={
                "x": int(rect.left),
                "y": int(rect.top),
                "width": int(max(0, rect.right - rect.left)),
                "height": int(max(0, rect.bottom - rect.top)),
            },
            app_type="web_browser" if browser_context else "native_app",
            app_metadata={
                "process_id": int(pid.value or 0),
                "app_path": proc_path,
                "window_id": int(hwnd),
            },
            browser_context=browser_context,
            hwnd=int(hwnd),
            process_id=int(pid.value or 0),
            window_class=class_buf.value or "",
        )

        child = _find_child_edit(hwnd)
        full_text = _read_window_text(child) if child else ""
        before = ""
        after = ""
        if inserted_text:
            split = split_inserted_text(full_text, inserted_text)
            if split:
                before, after = split
        child_rect = _window_rect(child) if child else {"x": 0, "y": 0, "width": 0, "height": 0}
        child_class = _class_name(child) if child else ""
        input_info = InputInfo(
            input_area_type="text_field",
            accessibility_role="win32_edit" if child else "",
            position_on_screen=child_rect,
            input_capabilities=InputCapabilities(
                is_editable=bool(child),
                supports_markdown=_supports_markdown(proc, {"class_name": child_class}),
                dom_id="",
                dom_classes=child_class,
            ),
            cursor_state=CursorState(
                cursor_position=-1,
                has_text_selected=False,
                selected_text="",
                text_before_cursor=before,
                text_after_cursor=after,
                full_field_content=full_text,
            ),
        )
        return FocusContext(
            active_application=app,
            text_insertion_point=input_info,
            input_box_identifier=build_input_box_identifier(app, input_info),
        )
    except Exception as e:
        logger.debug("ContextHelper target window context failed hwnd=%s err=%s", hwnd, e)
        return None


def _get_focus_context_via_dll(hwnd: int, inserted_text: str = "") -> Optional[FocusContext]:
    """Try in-process DLL first (Typeless-aligned)."""
    dll = ContextHelperDll()
    if not dll.is_available:
        return None
    raw = dll.get_full_context_for_window(hwnd) if hwnd else dll.get_full_context()
    return _map_native_context(raw, inserted_text)


def _get_focus_context_native(inserted_text: str = "") -> Optional[FocusContext]:
    raw = ContextHelperClient().get_full_context()
    return _map_native_context(raw, inserted_text)


def _map_native_context(raw: Optional[dict], inserted_text: str = "") -> Optional[FocusContext]:
    if not raw:
        return None
    try:
        app_raw = raw.get("active_application") or {}
        input_raw = raw.get("text_insertion_point") or {}
        caps_raw = input_raw.get("input_capabilities") or {}
        cursor_raw = input_raw.get("cursor_state") or {}

        app = AppInfo(
            app_name=str(app_raw.get("app_name") or ""),
            app_identifier=str(app_raw.get("app_identifier") or ""),
            window_title=str(app_raw.get("window_title") or ""),
            window_position=app_raw.get("window_position") or {
                "x": 0, "y": 0, "width": 0, "height": 0,
            },
            app_type=str(app_raw.get("app_type") or "native_app"),
            app_metadata=app_raw.get("app_metadata") or {},
            browser_context=app_raw.get("browser_context"),
            hwnd=_as_int(app_raw.get("hwnd"), _as_int((app_raw.get("app_metadata") or {}).get("window_id"), 0)),
            process_id=_as_int(app_raw.get("process_id"), _as_int((app_raw.get("app_metadata") or {}).get("process_id"), 0)),
            window_class=str(app_raw.get("window_class") or ""),
        )

        full_text = str(cursor_raw.get("full_field_content") or "")
        before = str(cursor_raw.get("text_before_cursor") or "")
        after = str(cursor_raw.get("text_after_cursor") or "")
        if inserted_text and (not before and not after):
            split = (
                split_terminal_inserted_text(full_text, inserted_text)
                if is_terminal_app(app)
                else split_inserted_text(full_text, inserted_text)
            )
            if split:
                before, after = split

        input_area_type = str(input_raw.get("input_area_type") or "text_field")
        terminal_mode = is_terminal_app(app) and bool(full_text)
        if terminal_mode:
            input_area_type = "terminal_text_buffer"
        if app.app_type == "web_browser" and input_area_type == "text_field":
            input_area_type = "web_text_field"

        input_info = InputInfo(
            input_area_type=input_area_type,
            accessibility_role=str(input_raw.get("accessibility_role") or ""),
            position_on_screen=input_raw.get("position_on_screen") or {
                "x": 0, "y": 0, "width": 0, "height": 0,
            },
            input_capabilities=InputCapabilities(
                is_editable=bool(caps_raw.get("is_editable")) or terminal_mode,
                supports_markdown=bool(caps_raw.get("supports_markdown")),
                dom_id=str(caps_raw.get("dom_id") or ""),
                dom_classes=str(caps_raw.get("dom_classes") or ""),
            ),
            cursor_state=CursorState(
                cursor_position=_as_int(cursor_raw.get("cursor_position"), -1),
                has_text_selected=bool(cursor_raw.get("has_text_selected")),
                selected_text=str(cursor_raw.get("selected_text") or ""),
                text_before_cursor=before,
                text_after_cursor=after,
                full_field_content=full_text,
            ),
            surrounding_context=input_raw.get("surrounding_context") or {
                "text_before_input_area": "",
                "text_after_input_area": "",
            },
        )
        logger.debug("ContextHelper using native helper for hwnd=%s proc=%s", app.hwnd, app.app_name)
        return FocusContext(
            active_application=app,
            text_insertion_point=input_info,
            input_box_identifier=build_input_box_identifier(app, input_info),
        )
    except Exception as e:
        logger.debug("ContextHelper native response mapping failed: %s", e)
        return None


def _get_focus_context_python(inserted_text: str = "") -> Optional[FocusContext]:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = ctypes.wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    title_buf = ctypes.create_unicode_buffer(512)
    class_buf = ctypes.create_unicode_buffer(256)
    rect = ctypes.wintypes.RECT()
    try:
        ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 512)
        ctypes.windll.user32.GetClassNameW(hwnd, class_buf, 256)
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    except Exception:
        pass

    proc, proc_path = _process_info(pid.value)
    window_title = title_buf.value or ""
    browser_context = _browser_context(proc, window_title)
    app_type = "web_browser" if browser_context else "native_app"
    app = AppInfo(
        app_name=proc,
        app_identifier=proc,
        window_title=window_title,
        window_position={
            "x": int(rect.left),
            "y": int(rect.top),
            "width": int(max(0, rect.right - rect.left)),
            "height": int(max(0, rect.bottom - rect.top)),
        },
        app_type=app_type,
        app_metadata={
            "process_id": int(pid.value or 0),
            "app_path": proc_path,
            "window_id": int(hwnd),
        },
        browser_context=browser_context,
        hwnd=int(hwnd),
        process_id=int(pid.value or 0),
        window_class=class_buf.value or "",
    )

    full_text = read_focus_text()
    focused_element = get_focused_element_snapshot()
    is_editable = bool(focused_element.get("editable")) or full_text is not None
    full_text = full_text or ""
    before = ""
    after = ""
    if inserted_text:
        split = (
            split_terminal_inserted_text(full_text, inserted_text)
            if is_terminal_app(app)
            else split_inserted_text(full_text, inserted_text)
        )
        if split:
            before, after = split
    terminal_mode = is_terminal_app(app) and bool(full_text)

    input_info = InputInfo(
        input_area_type="terminal_text_buffer" if terminal_mode else _input_area_type(app, focused_element),
        accessibility_role=str(focused_element.get("role") or ""),
        position_on_screen=focused_element.get("bounds") or {
            "x": 0, "y": 0, "width": 0, "height": 0,
        },
        input_capabilities=InputCapabilities(
            is_editable=is_editable or terminal_mode,
            supports_markdown=_supports_markdown(proc, focused_element),
            dom_id=str(focused_element.get("automation_id") or ""),
            dom_classes=str(focused_element.get("class_name") or ""),
        ),
        cursor_state=CursorState(
            cursor_position=-1,
            text_before_cursor=before,
            text_after_cursor=after,
            full_field_content=full_text,
        ),
    )
    return FocusContext(
        active_application=app,
        text_insertion_point=input_info,
        input_box_identifier=build_input_box_identifier(app, input_info),
    )


def build_input_box_identifier(app: AppInfo, input_info: InputInfo) -> str:
    caps = input_info.input_capabilities
    cursor = input_info.cursor_state
    stable_input = caps.dom_id or caps.dom_classes or input_info.accessibility_role
    if not stable_input:
        stable_input = f"{app.hwnd}:{app.window_class}"
    return "|".join([
        app.app_identifier or app.app_name,
        str(app.hwnd),
        app.window_class or "",
        stable_input,
        str(bool(cursor.full_field_content is not None)),
    ])


def _process_name(pid: int) -> str:
    return _process_info(pid)[0]


def _process_info(pid: int) -> tuple[str, str]:
    if not pid:
        return "", ""
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return "", ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.wintypes.DWORD(len(buf))
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(size))
            if not ok:
                return "", ""
            path = buf.value or ""
            return (os.path.basename(path) or "").lower(), path
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return "", ""


def _browser_context(proc: str, title: str) -> Optional[dict]:
    if proc not in {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe"}:
        return None
    page_title = re.sub(
        r"\s+-\s+(Google Chrome|Microsoft Edge|Mozilla Firefox|Opera|Brave)\s*$",
        "",
        title or "",
    )
    return {
        "page_title": page_title,
        "page_url": "",
        "domain": "",
    }


def _supports_markdown(proc: str, element: dict) -> bool:
    role = (element.get("role") or "").lower()
    cls = (element.get("class_name") or "").lower()
    if proc in {"obsidian.exe", "notion.exe", "code.exe", "cursor.exe", "discord.exe", "slack.exe"}:
        return True
    return "document" in role or "richedit" in cls


def _input_area_type(app: AppInfo, element: dict) -> str:
    role = (element.get("role") or "").lower()
    if "document" in role or "web" in role:
        return "document"
    if app.app_type == "web_browser":
        return "web_text_field"
    return "text_field"


def _find_child_edit(hwnd: int) -> int:
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_proc(child, _lparam):
        cls = _class_name(int(child)).lower()
        if "edit" in cls or "richedit" in cls:
            matches.append(int(child))
            return False
        return True

    try:
        ctypes.windll.user32.EnumChildWindows(hwnd, enum_proc, 0)
    except Exception:
        return 0
    return matches[0] if matches else 0


def _class_name(hwnd: int) -> str:
    if not hwnd:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
        return buf.value or ""
    except Exception:
        return ""


def _window_rect(hwnd: int) -> dict:
    rect = ctypes.wintypes.RECT()
    try:
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    except Exception:
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    return {
        "x": int(rect.left),
        "y": int(rect.top),
        "width": int(max(0, rect.right - rect.left)),
        "height": int(max(0, rect.bottom - rect.top)),
    }


def _read_window_text(hwnd: int) -> str:
    if not hwnd:
        return ""
    try:
        WM_GETTEXT = 0x000D
        WM_GETTEXTLENGTH = 0x000E
        length = int(ctypes.windll.user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.SendMessageW(hwnd, WM_GETTEXT, length + 1, buf)
        return buf.value or ""
    except Exception:
        return ""


def _as_int(value, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default

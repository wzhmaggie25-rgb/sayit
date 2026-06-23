from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    temp_appdata = tempfile.mkdtemp(prefix="sayit-smoke-appdata-")
    os.environ["APPDATA"] = temp_appdata

    from infrastructure.database import Database
    from infrastructure.injector import InjectionTarget, Injector
    from infrastructure.silent_monitor import SilentMonitor

    existing_notepad_hwnds = {row[0] for row in enum_notepad_windows()}
    temp_doc = tempfile.NamedTemporaryFile(prefix="sayit-smoke-", suffix=".txt", delete=False)
    temp_doc.close()
    proc = subprocess.Popen(["notepad.exe", temp_doc.name])
    hwnd = 0
    try:
        hwnd, pid, title, cls = wait_for_notepad_window(existing_notepad_hwnds)
        if not hwnd:
            print(json.dumps({"ok": False, "reason": "notepad window not found"}, ensure_ascii=False))
            return 1

        focus_window(hwnd)
        injector = Injector()
        target = InjectionTarget(hwnd=hwnd, pid=pid, proc="notepad.exe", cls=cls, title=title)
        injected = injector.inject("hello wrld", target=target)
        if not injected:
            print(json.dumps({"ok": False, "reason": "inject failed"}, ensure_ascii=False))
            return 1

        db = Database()
        history_id = db.add_history(raw_text="hello wrld", refined_text="hello wrld", final_text="hello wrld")
        monitor = SilentMonitor()
        monitor.start(str(history_id), "hello wrld", hwnd=hwnd, pid=pid)
        time.sleep(1.0)

        focus_window(hwnd)
        if not set_focused_value("hello world", hwnd=hwnd):
            print(json.dumps({"ok": False, "reason": "set edited value failed"}, ensure_ascii=False))
            return 1

        deadline = time.monotonic() + 8.0
        rules = []
        history = []
        while time.monotonic() < deadline:
            time.sleep(0.5)
            rules = db.get_rules(active_only=False)
            history = db.get_history(limit=1)
            if rules and history and history[0].get("edited_text_status") == "EXTRACTED":
                break

        print(json.dumps({
            "ok": bool(rules),
            "history": history[0] if history else None,
            "rules": [
                {
                    "pattern": rule.get("pattern"),
                    "replacement": rule.get("replacement"),
                    "source_history_id": rule.get("source_history_id"),
                }
                for rule in rules
            ],
            "target_text_preview": read_target_text_preview(hwnd),
            "appdata": temp_appdata,
        }, ensure_ascii=False, default=str))
        return 0 if rules else 1
    finally:
        if hwnd:
            try:
                ctypes.windll.user32.PostMessageW(wintypes.HWND(hwnd), 0x0010, 0, 0)
                time.sleep(0.5)
            except Exception:
                pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(temp_appdata, ignore_errors=True)
        try:
            os.unlink(temp_doc.name)
        except Exception:
            pass


def wait_for_notepad_window(existing_hwnds: set[int] | None = None) -> tuple[int, int, str, str]:
    existing_hwnds = existing_hwnds or set()
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        rows = [row for row in enum_notepad_windows() if row[0] not in existing_hwnds]
        if rows:
            return rows[0]
        time.sleep(0.3)
    return 0, 0, "", ""


def enum_notepad_windows() -> list[tuple[int, int, str, str]]:
    user32 = ctypes.windll.user32
    rows: list[tuple[int, int, str, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title = ctypes.create_unicode_buffer(512)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 512)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "Notepad":
            rows.append((int(hwnd), int(pid.value), title.value, cls.value))
        return True

    user32.EnumWindows(enum_proc, 0)
    return rows


def focus_window(hwnd: int):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd_value = wintypes.HWND(hwnd)
    user32.ShowWindow(hwnd_value, 9)
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd_value, None)
    user32.AttachThreadInput(current_thread, foreground_thread, True)
    user32.AttachThreadInput(current_thread, target_thread, True)
    user32.BringWindowToTop(hwnd_value)
    user32.SetForegroundWindow(hwnd_value)
    user32.SetFocus(hwnd_value)
    user32.AttachThreadInput(current_thread, target_thread, False)
    user32.AttachThreadInput(current_thread, foreground_thread, False)
    time.sleep(0.5)


def set_focused_value(value: str, hwnd: int = 0) -> bool:
    if hwnd and set_child_edit_text(hwnd, value):
        return True
    try:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        uia = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}")
        element = uia.GetFocusedElement()
        pattern = element.GetCurrentPattern(10002)
        pattern.SetValue(value)
        return True
    except Exception:
        return paste_value(value, hwnd=hwnd)


def set_child_edit_text(hwnd: int, value: str) -> bool:
    child = find_edit_child(hwnd)
    if not child:
        return False
    WM_SETTEXT = 0x000C
    WM_GETTEXT = 0x000D
    WM_GETTEXTLENGTH = 0x000E
    user32 = ctypes.windll.user32
    if not user32.SendMessageW(wintypes.HWND(child), WM_SETTEXT, 0, value):
        return False
    time.sleep(0.2)
    length = int(user32.SendMessageW(wintypes.HWND(child), WM_GETTEXTLENGTH, 0, 0))
    if length <= 0:
        return False
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(wintypes.HWND(child), WM_GETTEXT, length + 1, buf)
    return buf.value == value


def find_edit_child(hwnd: int) -> int:
    user32 = ctypes.windll.user32
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(child, _lparam):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(child, cls, 256)
        name = cls.value.lower()
        if "edit" in name or "richedit" in name:
            matches.append(int(child))
            return False
        return True

    user32.EnumChildWindows(wintypes.HWND(hwnd), enum_proc, 0)
    return matches[0] if matches else 0


def read_target_text_preview(hwnd: int) -> str:
    try:
        child = find_edit_child(hwnd)
        if not child:
            return ""
        WM_GETTEXT = 0x000D
        WM_GETTEXTLENGTH = 0x000E
        user32 = ctypes.windll.user32
        length = int(user32.SendMessageW(wintypes.HWND(child), WM_GETTEXTLENGTH, 0, 0))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(min(length, 200) + 1)
        user32.SendMessageW(wintypes.HWND(child), WM_GETTEXT, len(buf), buf)
        return buf.value
    except Exception:
        return ""


def paste_value(value: str, hwnd: int = 0) -> bool:
    try:
        import pyperclip

        if hwnd:
            focus_window(hwnd)
        pyperclip.copy(value)
        send_key_combo([0x11, 0x41])
        time.sleep(0.1)
        send_key_combo([0x11, 0x56])
        time.sleep(0.5)
        return True
    except Exception:
        return False


def send_key_combo(keys: list[int]):
    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


if __name__ == "__main__":
    raise SystemExit(main())

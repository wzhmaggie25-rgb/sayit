"""Text injection — 4-level waterfall: UIA → Clipboard → SendInput → fallback.

Handles ~30 apps with per-app strategy tables, UIPI detection, and terminal routing.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import logging
import os
import threading
import time
import traceback
from dataclasses import dataclass

try:
    import pyperclip
except Exception:
    pyperclip = None

from infrastructure.context_helper_client import ContextHelperClient
from infrastructure.config_store import ConfigStore

logger = logging.getLogger(__name__)


@dataclass
class InjectionTarget:
    hwnd: int = 0
    pid: int = 0
    proc: str = ""
    cls: str = ""
    title: str = ""


@dataclass
class InjectionResult:
    """Structured result of an injection attempt.

    Fields:
        ok: Whether the injection was reported successful.
        state: One of "verified_success", "attempted_unverified",
               "no_editable_target", "injection_failed",
               "recognition_failed".
        verified: Whether we confirmed the text actually appeared in the
                  target via readback (WM_GETTEXT or UIA ValuePattern).
        method: Which injection layer succeeded ("uia", "clipboard",
                "sendinput", "win32_child", or "" on total failure).
        reason: Human-readable explanation string.
        clipboard_preserved: Whether the original clipboard was preserved
                             (i.e. final_text NOT left on clipboard).
        clipboard_restored: Whether we explicitly restored original clipboard
                            after a paste operation.
        target_verified: Whether readback confirmed text in target.
        target_restored: Whether the original target window was restored
                         to foreground (may be False for child-edit injection).
    """
    ok: bool = False
    state: str = "recognition_failed"
    verified: bool = False
    method: str = ""
    reason: str = ""
    clipboard_preserved: bool = False
    clipboard_restored: bool = False
    target_verified: bool = False
    target_restored: bool = False

    def __bool__(self) -> bool:
        """Backward compat: InjectionResult can be used as bool."""
        return self.ok

# ── Win32 constants ───────────────────────────────────────────

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
PUL = ctypes.POINTER(ctypes.c_ulong)

GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13


class _KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", PUL)]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", PUL)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyBdInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


def _clipboard_get_text() -> str | None:
    if pyperclip is not None:
        try:
            return pyperclip.paste()
        except Exception:
            pass
    try:
        if not ctypes.windll.user32.OpenClipboard(None):
            return None
        try:
            handle = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            locked = ctypes.windll.kernel32.GlobalLock(handle)
            if not locked:
                return ""
            try:
                return ctypes.wstring_at(locked)
            finally:
                ctypes.windll.kernel32.GlobalUnlock(handle)
        finally:
            ctypes.windll.user32.CloseClipboard()
    except Exception:
        return None


def _clipboard_set_text(text: str) -> bool:
    if pyperclip is not None:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            pass
    try:
        if not ctypes.windll.user32.OpenClipboard(None):
            return False
        try:
            ctypes.windll.user32.EmptyClipboard()
            data = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(data)
            handle = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not handle:
                return False
            locked = ctypes.windll.kernel32.GlobalLock(handle)
            if not locked:
                ctypes.windll.kernel32.GlobalFree(handle)
                return False
            try:
                ctypes.memmove(locked, ctypes.addressof(data), size)
            finally:
                ctypes.windll.kernel32.GlobalUnlock(handle)
            ctypes.windll.user32.SetClipboardData(CF_UNICODETEXT, handle)
            return True
        finally:
            ctypes.windll.user32.CloseClipboard()
    except Exception:
        return False


# ── Strategy tables ───────────────────────────────────────────

TERMINAL_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty"}
TERMINAL_PROCS = frozenset({
    "windowsterminal.exe", "wt.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "conhost.exe", "mintty.exe", "xshell.exe", "xshellcore.exe", "warp.exe"})
UIA_UNRELIABLE_CLASSES = frozenset(
    {"WeChatMainWndForPC", "StandardFrame_DingTalk", "TscShellContainerClass"})

APP_STRATEGIES = {
    # Terminal -> temporary clipboard + Ctrl+Shift+V
    "windowsterminal.exe": "clipboard_terminal", "wt.exe": "clipboard_terminal",
    "cmd.exe": "clipboard_terminal", "powershell.exe": "clipboard_terminal",
    "pwsh.exe": "clipboard_terminal", "conhost.exe": "clipboard_terminal",
    "mintty.exe": "clipboard_terminal", "xshell.exe": "clipboard_terminal",
    "warp.exe": "clipboard_terminal",          # Typeless: terminal blacklist
    # Office → UIA
    "excel.exe": "uia", "powerpnt.exe": "uia", "winword.exe": "uia",
    "onenote.exe": "clipboard",         # Typeless: Office family, UIA unreliable
    # WPS → UIA
    "et.exe": "uia", "wpp.exe": "uia", "wps.exe": "uia",
    "soffice.bin": "uia",              # LibreOffice
    # IDE / Editors → UIA
    "cursor.exe": "uia", "sublime_text.exe": "uia", "zed.exe": "uia",
    "code.exe": "uia", "devenv.exe": "uia",
    "notepad++.exe": "uia",            # Scintilla-based, UIA accessible
    "obsidian.exe": "uia",             # Electron + CodeMirror
    # Browsers → UIA
    "chrome.exe": "uia", "firefox.exe": "uia", "opera.exe": "uia", "msedge.exe": "uia",
    # IM (self-drawn controls) → Clipboard
    "whatsapp.exe": "clipboard", "dingtalk.exe": "clipboard",
    "wxwork.exe": "clipboard", "weixin.exe": "clipboard", "wechat.exe": "clipboard",
    "aliim.exe": "clipboard", "tencentdocs.exe": "clipboard",
    "feishu.exe": "clipboard",         # 飞书 — self-drawn UI
    "lark.exe": "clipboard",           # Lark — 飞书国际版
    "teams.exe": "clipboard",          # Teams v2 (WebView2), UIA unreliable
    "discord.exe": "clipboard",        # Electron + rich text input
    "slack.exe": "clipboard",          # Electron, same as Discord
    # Other → Clipboard
    "cloudmusic.exe": "clipboard", "zoom.exe": "clipboard",
    "wemail.exe": "clipboard", "wpspdf.exe": "clipboard",
    "notion.exe": "clipboard",         # Electron + custom editor
    "figma.exe": "clipboard",          # WebGL, no native controls
}

TYPELESS_ACCESSIBILITY_CONFIG = {
    # Reference: reference/injection_strategy.js lines 3626-3658.
    "app_blacklist": {
        "exact": {
            "weixin.exe", "dingtalk.exe", "warp.exe", "tencentdocs.exe",
            "cloudmusic.exe", "winword.exe", "powerpnt.exe", "excel.exe",
            "cmd.exe", "powershell.exe", "wt.exe", "windowsterminal.exe",
            "mintty.exe", "onenote.exe", "notepad++.exe", "sublime_text.exe",
            "zoom.exe", "wps.exe", "et.exe", "wpp.exe", "wpspdf.exe",
            "soffice.bin", "whatsapp.root.exe", "whatsapp.exe",
            "xshellcore.exe", "xshell.exe",
        },
        "regex": [],
    },
    "app_whitelist": {
        "exact": {"cursor.exe", "wxwork.exe", "wemail.exe", "aliim.exe", "zed.exe"},
        "regex": [r"web\.whatsapp\.com"],
    },
    "url_blacklist": {
        "exact": [],
        "prefix": [
            "https://docs.google.com/document/d",
            "https://docs.qq.com/doc/",
            "https://docs.qq.com/sheet/",
        ],
        "domain": [],
        "regex": [],
    },
    "url_whitelist": {
        "exact": [],
        "prefix": ["https://www.figma.com/design/"],
        "domain": [],
        "regex": [],
    },
}


class Injector:
    """4-level waterfall text injection."""

    # Modifiers to release before injection (L/R + generic VK for each)
    _MODIFIER_RELEASE_ORDER = [
        0xA4, 0xA5, 0x12,   # Alt L/R/VK — first, cancel menu activation
        0x5B, 0x5C,          # Win L/R
        0xA2, 0xA3, 0x11,    # Ctrl L/R/VK
        0xA0, 0xA1, 0x10,    # Shift L/R/VK — last, avoid capitalisation
    ]

    def __init__(self, injection_mode: str = "auto"):
        self._lock = threading.RLock()
        self.injection_mode = injection_mode
        self.last_target_hwnd = 0
        self.last_target_pid = 0
        self.last_target_proc = ""
        self.last_target_title = ""
        self.last_target_class = ""

    def capture_target(self) -> InjectionTarget:
        """Snapshot the current cursor/input window at recording start."""
        hwnd, cls, pid, proc = self._foreground_info()
        title = ""
        if hwnd:
            try:
                title_buf = ctypes.create_unicode_buffer(512)
                ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 512)
                title = title_buf.value or ""
            except Exception:
                title = ""
        target = InjectionTarget(hwnd=hwnd or 0, pid=pid, proc=proc, cls=cls, title=title)
        logger.info(
            "[INJECT-TARGET] captured hwnd=%s pid=%s proc=%s class=%s title=%r",
            target.hwnd, target.pid, target.proc, target.cls, target.title[:80])
        return target

    def _foreground_info(self) -> tuple[int, str, int, str]:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return 0, "", 0, ""
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
        cls = buf.value or ""
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = self._proc_name(pid.value)
        return hwnd, cls, pid.value, proc

    def _assess_target_editability(self, target: InjectionTarget | None) -> str:
        """Assess whether the foreground/focused element is an editable text target.

        Returns one of:
          "editable" — focused UIA element with ValuePattern/TextPattern,
                       or foreground hwnd has Win32 Edit/RichEdit child, or
                       known app strategy exists.
          "no_editable" — no focused element, foreground hwnd missing,
                          or UIA reports no editable capabilities.
          "unknown" — cannot determine (should fall through to injection attempt).
        """
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                logger.info("[INJECT-EDITABILITY] no foreground window → no_editable")
                return "no_editable"

            # Quick Win32 check: does foreground hwnd or its focused child have Edit class?
            focus_hwnd = ctypes.windll.user32.GetFocus()
            if focus_hwnd:
                class_buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetClassNameW(focus_hwnd, class_buf, 256)
                cls = (class_buf.value or "").lower()
                if "edit" in cls or "richedit" in cls:
                    logger.info("[INJECT-EDITABILITY] focused Win32 edit control → editable")
                    return "editable"

            # Try UIA focused element
            try:
                import comtypes
                comtypes.CoInitialize()
                try:
                    from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
                    uia = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
                    elem = uia.GetFocusedElement()
                    if elem is None:
                        logger.info("[INJECT-EDITABILITY] no UIA focused element → no_editable")
                        return "no_editable"
                    # Check for ValuePattern or TextPattern
                    try:
                        vp = elem.GetCurrentPattern(10002)
                        if vp is not None:
                            logger.info("[INJECT-EDITABILITY] UIA ValuePattern available → editable")
                            return "editable"
                    except Exception:
                        pass
                    try:
                        tp = elem.GetCurrentPattern(10014)
                        if tp is not None:
                            logger.info("[INJECT-EDITABILITY] UIA TextPattern available → editable")
                            return "editable"
                    except Exception:
                        pass
                    # No editable pattern found
                    logger.info("[INJECT-EDITABILITY] UIA element has no editable pattern → no_editable")
                    return "no_editable"
                finally:
                    comtypes.CoUninitialize()
            except Exception as e:
                logger.debug("[INJECT-EDITABILITY] UIA check failed: %s", e)

            # Fallback: check for child edit under foreground
            if hwnd and self._find_child_edit(hwnd):
                logger.info("[INJECT-EDITABILITY] child edit found → editable")
                return "editable"

            logger.info("[INJECT-EDITABILITY] cannot determine editability → unknown")
            return "unknown"
        except Exception as e:
            logger.debug("[INJECT-EDITABILITY] assessment error: %s", e)
            return "unknown"

    def _proc_name(self, pid: int) -> str:
        try:
            h = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
            if not h:
                return ""
            buf = ctypes.create_unicode_buffer(260)
            sz = wintypes.DWORD(260)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz))
            ctypes.windll.kernel32.CloseHandle(h)
            return os.path.basename(buf.value).lower() if ok else ""
        except Exception:
            return ""

    def paste(self, text: str, terminal: bool = False) -> tuple[bool, str, bool]:
        """Clipboard paste via ctypes keybd_event (bypasses UIPI for admin windows).

        Returns ``(shortcut_sent, snapshot_kind, restore_ok)``:

        - ``shortcut_sent``: True when the Ctrl+V (or Ctrl+Shift+V) shortcut was
          dispatched. Does NOT mean the text reached the target — the caller
          must readback the target before declaring ``verified_success``.
        - ``snapshot_kind``: one of "EMPTY" / "TEXT" / "UNSUPPORTED_OR_MULTIFORMAT"
          / "READ_FAILED" / "set_failed". When non-text clipboard content was
          detected (image / file list / HTML / RTF / multiple formats) the
          paste is REFUSED and snapshot_kind reflects that — the caller must
          pick a different injection path so we never destroy user content.
        - ``restore_ok``: True when the original clipboard snapshot was
          successfully restored after the paste. False means the final text
          may still be on the clipboard.

        Restores the original clipboard after the paste based on the snapshot:
        EMPTY → EmptyClipboard, TEXT → write back the original string. The old
        "did clipboard still hold our text after Ctrl+V" heuristic is gone —
        it produced false negatives on every normal paste consumer.

        Restore retries up to 3 times with 0.1s back-off. On final failure the
        caller marks clipboard_preserved/restored as False.
        """
        from infrastructure.clipboard_snapshot import (
            ClipboardSnapshot, read_snapshot, restore_snapshot,
        )

        with self._lock:
            snap = read_snapshot()
            logger.info(
                "[INJECT-CLIPBOARD] snapshot kind=%s formats=%s detail=%r",
                snap.kind, snap.formats[:6], snap.detail[:80])

            # Refuse to use the clipboard path when we cannot safely restore.
            # The caller will fall through to another layer (UIA / SendInput).
            if not snap.safe_for_clipboard_paste:
                logger.warning(
                    "[INJECT-CLIPBOARD] refusing clipboard paste — snapshot=%s "
                    "(would destroy user content)", snap.kind)
                return False, snap.kind, True  # untouched, so restore is trivially ok

            if not _clipboard_set_text(text):
                return False, "set_failed", True

            text_len = len(text)
            pre = 0.05 if text_len < 100 else (0.10 if text_len < 1000 else 0.20)
            post = 0.25 if text_len < 100 else (0.50 if text_len < 1000 else 0.80)
            if terminal:
                post = max(post, 0.60)
            logger.info(
                "[INJECT-CLIPBOARD] backup_kind=%s terminal=%s text_len=%d",
                snap.kind, terminal, text_len)
            time.sleep(pre)
            try:
                logger.info(
                    "[INJECT-CLIPBOARD] paste shortcut=%s text_len=%d post_delay=%.2f",
                    "Ctrl+Shift+V" if terminal else "Ctrl+V", text_len, post)
                VK_CONTROL = 0x11
                VK_RSHIFT = 0xA1
                VK_V = 0x56
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
                if terminal:
                    ctypes.windll.user32.keybd_event(VK_RSHIFT, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_V, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
                if terminal:
                    ctypes.windll.user32.keybd_event(VK_RSHIFT, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            except Exception:
                logger.warning("[injector] keybd_event paste failed: %s", traceback.format_exc())
                # Always try to restore — paste shortcut never dispatched.
                restore_ok = self._restore_with_retry(snap)
                return False, snap.kind, restore_ok
            time.sleep(post)

            # ALWAYS restore based on snapshot — EMPTY → EmptyClipboard,
            # TEXT → write back original string. Never leave the final text
            # sitting on the clipboard for the user to discover later.
            restore_ok = self._restore_with_retry(snap)
            logger.info(
                "[INJECT-CLIPBOARD] restore result=%s kind=%s terminal=%s",
                restore_ok, snap.kind, terminal)
            return True, snap.kind, restore_ok

    def _restore_with_retry(self, snap) -> bool:
        """Restore clipboard snapshot with up to 3 retries and 0.1s back-off."""
        from infrastructure.clipboard_snapshot import restore_snapshot
        for attempt in range(3):
            if restore_snapshot(snap):
                return True
            if attempt < 2:
                time.sleep(0.1)
        logger.warning(
            "[INJECT-CLIPBOARD] restore failed after 3 attempts kind=%s",
            snap.kind)
        return False

    def _direct_input(self, text: str) -> bool:
        try:
            code_units = text.encode("utf-16-le")
            inputs = []
            for i in range(0, len(code_units), 2):
                cu = code_units[i] | (code_units[i + 1] << 8)
                dn = INPUT(); dn.type = INPUT_KEYBOARD; dn.ki.wVk = 0
                dn.ki.wScan = cu; dn.ki.dwFlags = KEYEVENTF_UNICODE
                up = INPUT(); up.type = INPUT_KEYBOARD; up.ki.wVk = 0
                up.ki.wScan = cu; up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                inputs.extend([dn, up])
            if not inputs:
                return True
            chunk_size = 200
            offset = 0
            total = len(inputs)
            while offset < total:
                chunk = inputs[offset:offset + chunk_size]
                offset += len(chunk)
                arr = (INPUT * len(chunk))(*chunk)
                # ── [INJECT-PATH] key synthesis — log per-chunk vk/scan/char ──
                glyphs_in_chunk = []
                ascii_hits = []
                for inp in chunk:
                    if inp.ki.dwFlags & KEYEVENTF_KEYUP:
                        continue  # only log key-down events
                    cu = inp.ki.wScan
                    try:
                        glyph = chr(cu) if 0 < cu < 0x110000 else "?"
                    except Exception:
                        glyph = "?"
                    glyphs_in_chunk.append(glyph)
                    if glyph.isascii() and glyph.isprintable():
                        ascii_hits.append((hex(cu), glyph))
                logger.info(
                    "[INJECT-PATH] route=sendinput chunk_offset=%d chunk_size=%d "
                    "first_glyphs=%r ascii_hits=%s",
                    offset - len(chunk), len(chunk) // 2,
                    "".join(glyphs_in_chunk[:8]),
                    ascii_hits if ascii_hits else "none")
                ctypes.windll.user32.SendInput(len(arr), ctypes.byref(arr), ctypes.sizeof(INPUT))
                if offset < total:
                    time.sleep(0.005)
            return True
        except Exception:
            logger.warning("[injector] _direct_input error: %s", traceback.format_exc())
            return False

    def _focus_window(self, hwnd: int) -> bool:
        try:
            cur = ctypes.windll.user32.GetForegroundWindow()
            if cur == hwnd:
                return True
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            foreground_thread = ctypes.windll.user32.GetWindowThreadProcessId(cur, None) if cur else 0
            target_thread = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
            if foreground_thread:
                ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, True)
            if target_thread:
                ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, True)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.SetFocus(hwnd)
            try:
                ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass
            try:
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                ctypes.windll.user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                ctypes.windll.user32.SetWindowPos(
                    hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            if target_thread:
                ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, False)
            if foreground_thread:
                ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, False)
            time.sleep(0.08)
            return ctypes.windll.user32.GetForegroundWindow() == hwnd
        except Exception:
            return False

    def _release_modifiers(self, *, force: bool = False, reason: str = ""):
        """Send synthetic keyup for modifiers to clear stuck hotkey/paste state."""
        before = self._get_modifier_states()
        for vk in self._MODIFIER_RELEASE_ORDER:
            # ── Guard: only release if the key is physically pressed ──
            # Sending keyup for an already-up modifier can produce stray
            # characters on some Windows editions/IME configurations.
            if not force and not (ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000):
                continue
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.ki.wVk = vk
            inp.ki.wScan = 0
            inp.ki.dwFlags = KEYEVENTF_KEYUP
            ctypes.windll.user32.SendInput(
                1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.001)  # tiny gap between events
        time.sleep(0.03)  # let OS digest all keyup events
        logger.info(
            "[INJECT-MODIFIERS] release force=%s reason=%s before=%s after=%s",
            force, reason, before, self._get_modifier_states())

    def _get_modifier_states(self):
        """Read current modifier key states via GetAsyncKeyState."""
        vks = {"Ctrl": 0x11, "Alt": 0x12, "Shift": 0x10, "LWin": 0x5B, "RWin": 0x5C}
        return {
            name: bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
            for name, vk in vks.items()
        }

    def _snapshot_target_text(self, hwnd: int) -> tuple[bool, str]:
        """Capture the current text from a Win32 child Edit control.

        Returns ``(ok, text)``. ``ok=False`` means readback is not possible
        for this target — caller should treat the injection as
        ``attempted_unverified`` rather than ``injection_failed``.
        """
        if not hwnd:
            return False, ""
        try:
            child = self._find_child_edit(hwnd) or hwnd
        except Exception:
            child = hwnd
        try:
            WM_GETTEXTLENGTH = 0x000E
            WM_GETTEXT = 0x000D
            user32 = ctypes.windll.user32
            send_proto = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t,
                wintypes.HWND, wintypes.UINT,
                wintypes.WPARAM, wintypes.LPARAM,
            )
            send = send_proto(("SendMessageW", user32))
            length = int(send(child, WM_GETTEXTLENGTH, 0, 0))
            if length < 0:
                return False, ""
            if length == 0:
                return True, ""  # zero-length readback is still valid
            buf = ctypes.create_unicode_buffer(length + 1)
            send(child, WM_GETTEXT, length + 1,
                 ctypes.cast(buf, ctypes.c_void_p).value or 0)
            return True, buf.value or ""
        except Exception:
            return False, ""

    def _verify_target_text(self, hwnd: int, expected: str,
                             pre_text: str | None) -> str:
        """Decide post-paste readback outcome via pre/post diff.

        Phase 3 fix: reject substring false positives by requiring a
        provable pre→post insertion.

        Returns one of:
          "verified"     — post content PROVES expected was inserted.
          "unchanged"    — target text did not change at all (paste was
                           confirmed-rejected). Caller should map to
                           ``injection_failed``.
          "no_readback"  — readback failed or returned ambiguous data.
                           Caller maps to ``attempted_unverified``.
        """
        ok, post = self._snapshot_target_text(hwnd)
        if not ok:
            return "no_readback"

        # Without a pre snapshot, fall back to weak substring check.
        if pre_text is None:
            return "verified" if expected and expected in post else "no_readback"

        if post == pre_text:
            return "unchanged"

        # Strong diff check: post must be pre with expected cleanly inserted.
        if expected:
            # Count increase rules out the case where expected was already
            # present and only a different edit occurred.
            if post.count(expected) > pre_text.count(expected):
                idx = post.find(expected)
                if idx >= 0:
                    # Removing the first occurrence of expected from post
                    # should recover pre exactly.
                    if post[:idx] + post[idx + len(expected):] == pre_text:
                        return "verified"
        return "no_readback"

    def inject(self, text: str, target: InjectionTarget | None = None) -> InjectionResult:
        """4-level waterfall injection.

        Returns InjectionResult with structured outcome info. The result
        is truthy (via __bool__) if injection succeeded, falsy if not.
        On failure, clipboard_preserved is always True — the final text
        is left on the clipboard for manual paste.
        """
        with self._lock:
            return self._inject_locked(text, target)

    def _inject_locked(self, text: str, target: InjectionTarget | None) -> InjectionResult:
        def _fail(reason: str = "") -> InjectionResult:
            # On failure: do NOT auto-copy text to clipboard unless
            # copy_result_to_clipboard is explicitly enabled.
            # Per spec: verified_success/no_editable_target must preserve clipboard;
            # injection_failed also preserves clipboard by default.
            try:
                cfg_copy = ConfigStore().get("copy_result_to_clipboard", False)
            except Exception:
                cfg_copy = False
            if cfg_copy:
                try:
                    _clipboard_set_text(text)
                    logger.warning(
                        "[INJECT-FALLBACK] copy_result_to_clipboard=True — "
                        "final text written to clipboard (len=%d) reason=%s",
                        len(text), reason)
                except Exception:
                    pass
            else:
                logger.warning(
                    "[INJECT-FALLBACK] all injection paths failed — "
                    "clipboard preserved (untouched) reason=%s", reason)
            return InjectionResult(ok=False, state="injection_failed",
                                    clipboard_preserved=(not cfg_copy),
                                    reason=reason or "all_injection_paths_failed")

        def _ok(method: str, verified: bool = False, target_restored: bool = False,
                restore_ok: bool = True) -> InjectionResult:
            return InjectionResult(ok=True, state="verified_success",
                                    verified=verified, method=method,
                                    clipboard_preserved=restore_ok,
                                    clipboard_restored=restore_ok,
                                    target_verified=verified,
                                    target_restored=target_restored)

        def _attempted_unverified(method: str, reason: str = "", restore_ok: bool = True) -> InjectionResult:
            """Action dispatched but target readback was not possible.

            Per ROUND5_CODE_REVIEW.md P0-3: the Ctrl+V/SendInput shortcut
            was sent but we cannot prove the text reached the target. We
            MUST NOT then try a second injection path — that risks
            duplicating the text in a target that did accept the first
            attempt. Clipboard is preserved; SilentMonitor must skip this
            history.
            """
            return InjectionResult(
                ok=True,  # treated as "no error" for pipeline flow purposes;
                          # callers check `state` to gate SilentMonitor.
                state="attempted_unverified",
                verified=False,
                method=method,
                clipboard_preserved=restore_ok,
                clipboard_restored=restore_ok,
                target_verified=False,
                reason=reason or "shortcut_sent_no_readback",
            )

        self._release_modifiers(reason="inject_start")
        logger.info(
            "[INJECT-PRE] text=%r len=%d vk_list=%s modifiers=%s",
            text[:20], len(text), self._MODIFIER_RELEASE_ORDER,
            self._get_modifier_states())

        # ── Stage 0: Assess current foreground editability ──
        # Do NOT restore captured target — inject into current foreground.
        # If no editable element is focused, return no_editable_target
        # immediately (never touches clipboard).
        editability = self._assess_target_editability(target)
        if editability == "no_editable":
            logger.info(
                "[INJECT-POST] no editable target — "
                "returning no_editable_target state")
            return InjectionResult(ok=False, state="no_editable_target",
                                    clipboard_preserved=True,
                                    reason="no_editable_target")

        # ── Stage A: use current foreground (never restore captured target) ──
        hwnd, cls, pid, proc = self._foreground_info()
        self.last_target_hwnd = hwnd or 0
        self.last_target_pid = pid
        self.last_target_proc = proc
        self.last_target_class = cls
        logger.info(
            "[INJECT-PATH] entry text_preview=%r len=%d target_hwnd=%s target_class=%s "
            "target_process=%s injection_mode=%s",
            text[:8] if len(text) > 8 else text, len(text),
            hwnd or 0, cls, proc,
            self.injection_mode)

        try:
            title_buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 512)
            self.last_target_title = title_buf.value or ""
        except Exception:
            self.last_target_title = ""

        context = self._get_context_for_strategy()
        strategy = self._strategy_for_context(proc, cls, context)
        is_terminal = self._is_terminal_target(proc, cls)
        if is_terminal:
            self._release_modifiers(force=True, reason="terminal_before_paste")

        logger.info(
            "[INJECT-PATH] route strategy=%s terminal=%s text_len=%d "
            "target_process=%s target_class=%s target_title=%r "
            "will_try_uia=%s will_try_clipboard=%s will_try_sendinput=%s "
            "cls_in_unreliable=%s context_app_type=%s",
            strategy, is_terminal, len(text), proc, cls, self.last_target_title[:80],
            bool(strategy == "uia" and cls not in UIA_UNRELIABLE_CLASSES),
            bool(strategy != "send_input"),
            bool(not is_terminal),
            cls in UIA_UNRELIABLE_CLASSES,
            (context.get("active_application") or {}).get("app_type") if context else "")

        # Layer 1: UIA
        # _inject_uia returns tri-state:
        #   True  → verified, return _ok
        #   False → SetValue attempted but unverified → return attempted_unverified
        #   None  → no action taken → fall through to clipboard paste
        if strategy == "uia" and cls not in UIA_UNRELIABLE_CLASSES:
            uia_result = self._inject_uia(text)
            if uia_result is True:
                logger.info("[INJECT-POST] ok via=UIA")
                return _ok("uia", verified=True)
            elif uia_result is False:
                logger.info(
                    "[INJECT-POST] UIA SetValue attempted but unverified — "
                    "returning attempted_unverified (no clipboard fallthrough)")
                return _attempted_unverified("uia", reason="uia_setvalue_unverified")
            # uia_result is None → no action, fall through

        # Pre-paste target snapshot — used to differentiate
        # verified / unchanged / no_readback after a paste shortcut.
        readback_hwnd = hwnd or 0
        pre_ok, pre_text = self._snapshot_target_text(readback_hwnd)
        logger.info(
            "[INJECT-READBACK] pre-snapshot hwnd=%s ok=%s len=%d",
            readback_hwnd, pre_ok, len(pre_text) if pre_ok else -1)

        # Layer 2: Clipboard paste
        # New contract: paste() returns (shortcut_sent, snapshot_kind, restore_ok).
        # It refuses to run when the snapshot is non-text/multi-format/read-failed
        # so we never destroy user clipboard content. In that case fall
        # through to SendInput (which does not touch the clipboard).
        if strategy != "send_input":
            paste_sent, snap_kind, restore_ok = self.paste(text, terminal=is_terminal)
            if paste_sent:
                if is_terminal:
                    self._release_modifiers(force=True, reason="terminal_after_paste_ok")
                # Readback to decide verified / unchanged / no_readback.
                verdict = self._verify_target_text(
                    readback_hwnd, text, pre_text if pre_ok else None)
                logger.info(
                    "[INJECT-POST] clipboard paste sent verdict=%s snapshot=%s "
                    "restore_ok=%s",
                    verdict, snap_kind, restore_ok)
                if verdict == "verified":
                    return _ok("clipboard", verified=True, restore_ok=restore_ok)
                if verdict == "unchanged":
                    # Paste shortcut sent but target text did not change —
                    # the consumer refused our paste (admin window / IME /
                    # UIPI / disabled control). Per Round 7 spec:
                    # reliable unchanged → injection_failed.
                    # DO NOT try SendInput on top: we have no proof the paste
                    # was truly rejected vs rendered elsewhere; chase will
                    # risk duplicate text.
                    return _fail("paste_target_unchanged")
                # no_readback — cannot prove anything either way.
                return _attempted_unverified(
                    "clipboard", reason="paste_no_readback", restore_ok=restore_ok)
            logger.info(
                "[INJECT-PATH] clipboard skipped/failed snapshot=%s — "
                "falling through", snap_kind)

        # Layer 3: SendInput
        if is_terminal:
            logger.warning(
                "[INJECT-PATH] terminal clipboard failed; no SendInput fallback "
                "target_process=%s target_class=%s text_len=%d",
                proc, cls, len(text))
            self._release_modifiers(force=True, reason="terminal_after_paste_failed")
            return _fail("terminal_clipboard_failed")
        if self._direct_input(text):
            verdict = self._verify_target_text(
                readback_hwnd, text, pre_text if pre_ok else None)
            logger.info("[INJECT-POST] sendinput verdict=%s", verdict)
            if verdict == "verified":
                return _ok("sendinput", verified=True)
            if verdict == "unchanged":
                # SendInput dispatched but target didn't budge — clear
                # failure (control disabled, window inactive, etc.).
                return _fail("sendinput_target_unchanged")
            # no_readback after SendInput: text may be in the target but we
            # cannot prove it. Don't fail (that would imply auto-copy under
            # legacy behavior); don't retry either.
            return _attempted_unverified("sendinput", reason="sendinput_no_readback")

        logger.info("[INJECT-POST] FAILED all=3")
        return _fail("all_three_layers_failed")

    def _get_context_for_strategy(self) -> dict:
        try:
            context = ContextHelperClient().get_full_context(timeout=0.3)
            return context if isinstance(context, dict) else {}
        except Exception:
            return {}

    def _inject_win32_child_edit(self, text: str, hwnd: int) -> bool:
        """Inject text into a Win32 Edit/RichEdit child of `hwnd`.

        Uses SendMessage(WM_SETTEXT) + WM_GETTEXT readback so the path is
        deterministic and does not depend on the target being foreground.
        Returns True only if the readback matches `text` exactly.

        **Guard:** refuses WM_SETTEXT when the control already has content,
        because WM_SETTEXT replaces the entire field (non-destructive). For
        non-empty controls, use the clipboard or SendInput path instead.
        """
        child = self._find_child_edit(hwnd)
        if not child:
            return False
        try:
            WM_SETTEXT = 0x000C
            WM_GETTEXT = 0x000D
            WM_GETTEXTLENGTH = 0x000E
            user32 = ctypes.windll.user32
            # SendMessageW returns LRESULT (pointer-sized). Without restype
            # ctypes truncates to 32 bits — break out a private prototype so
            # we don't mutate global SendMessageW state.
            send_proto = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t,
                wintypes.HWND, wintypes.UINT,
                wintypes.WPARAM, wintypes.LPARAM,
            )
            send = send_proto(("SendMessageW", user32))

            # ── Guard: refuse if control already has content ──
            length = int(send(child, WM_GETTEXTLENGTH, 0, 0))
            if length > 0:
                logger.info(
                    "[INJECT-WIN32] refusing WM_SETTEXT — control has %d chars "
                    "(non-destructive guard)", length)
                return False

            # Pass `text` as a buffer pointer cast to LPARAM — equivalent
            # to MSDN's "(LPARAM)lpString" convention.
            text_buf = ctypes.create_unicode_buffer(text)
            r = send(child, WM_SETTEXT, 0,
                     ctypes.cast(text_buf, ctypes.c_void_p).value or 0)
            if not r:
                return False
            time.sleep(0.05)
            length = int(send(child, WM_GETTEXTLENGTH, 0, 0))
            if length < 0:
                return False
            buf = ctypes.create_unicode_buffer(length + 1)
            send(child, WM_GETTEXT, length + 1,
                 ctypes.cast(buf, ctypes.c_void_p).value or 0)
            return buf.value == text
        except Exception:
            logger.info("[INJECT-WIN32] child edit injection failed: %s", traceback.format_exc())
            return False

    def _find_child_edit(self, hwnd: int) -> int:
        matches: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_proc(child, _lparam):
            class_buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(child, class_buf, 256)
            cls = (class_buf.value or "").lower()
            if "edit" in cls or "richedit" in cls:
                matches.append(int(child))
                return False
            return True

        try:
            ctypes.windll.user32.EnumChildWindows(hwnd, enum_proc, 0)
        except Exception:
            return 0
        return matches[0] if matches else 0

    def _strategy_for_context(self, proc: str, cls: str, context: dict) -> str:
        strategy = APP_STRATEGIES.get(proc, "uia")
        if self._is_terminal_target(proc, cls):
            return "clipboard_terminal"
        if not context:
            return strategy
        app = context.get("active_application") or {}
        input_info = context.get("text_insertion_point") or {}
        caps = input_info.get("input_capabilities") or {}
        context_proc = (app.get("app_name") or "").lower()
        if context_proc and context_proc != proc:
            return strategy
        policy = self._typeless_accessibility_policy(context, proc)
        if policy == "blacklist" and strategy == "uia":
            return "clipboard"
        if app.get("app_type") == "web_browser":
            return APP_STRATEGIES.get(proc, "uia")
        if cls in UIA_UNRELIABLE_CLASSES:
            return "clipboard"
        if caps.get("is_editable") is False and strategy == "uia":
            return "clipboard"
        return strategy

    @staticmethod
    def _is_terminal_target(proc: str, cls: str) -> bool:
        return (proc or "").lower() in TERMINAL_PROCS or cls in TERMINAL_CLASSES

    def _typeless_accessibility_policy(self, context: dict, proc: str) -> str:
        app = context.get("active_application") or {}
        browser = app.get("browser_context") or {}
        app_id = (app.get("app_identifier") or app.get("app_name") or proc or "").lower()
        page_url = str(browser.get("page_url") or "")
        domain = str(browser.get("domain") or "")
        cfg = TYPELESS_ACCESSIBILITY_CONFIG

        app_whitelist = self._matches_app_rule(cfg["app_whitelist"], app_id)
        app_blacklist = self._matches_app_rule(cfg["app_blacklist"], app_id)
        url_whitelist = self._matches_url_rule(cfg["url_whitelist"], page_url, domain)
        url_blacklist = self._matches_url_rule(cfg["url_blacklist"], page_url, domain)

        if app_whitelist or url_whitelist:
            return "whitelist"
        if app_blacklist or url_blacklist:
            return "blacklist"
        return "neutral"

    @staticmethod
    def _matches_app_rule(rule: dict, app_id: str) -> bool:
        if not app_id:
            return False
        lowered = app_id.lower()
        exact = {str(item).lower() for item in rule.get("exact", [])}
        if lowered in exact:
            return True
        import re
        return any(re.search(pattern, app_id) for pattern in rule.get("regex", []))

    @staticmethod
    def _matches_url_rule(rule: dict, page_url: str, domain: str = "") -> bool:
        if not page_url and not domain:
            return False
        lowered_url = page_url.lower()
        lowered_domain = domain.lower()
        if lowered_url in {str(item).lower() for item in rule.get("exact", [])}:
            return True
        if lowered_domain and lowered_domain in {str(item).lower() for item in rule.get("domain", [])}:
            return True
        if any(lowered_url.startswith(str(prefix).lower()) for prefix in rule.get("prefix", [])):
            return True
        import re
        return any(re.search(pattern, page_url) for pattern in rule.get("regex", []))

    def _inject_uia(self, text: str) -> bool | None:
        """Try UIA ValuePattern injection with read-back verification.

        Returns tri-state:
          True   — SetValue succeeded AND read-back confirmed.
          False  — SetValue was attempted but read-back failed — the
                   element may have been modified. **Must NOT** fall
                   through to clipboard paste (would duplicate text).
          None   — No action taken (no focused element, no ValuePattern).
                   Caller may proceed to clipboard paste.

        Does NOT call TextPattern.Select() — that would select all content
        and destroy the user's cursor position. Does NOT interact with the
        clipboard. Does NOT fall through to additional injection after the
        element may have been modified.
        """
        try:
            import comtypes
            import comtypes.client
        except Exception as e:
            logger.info("[INJECT-UIA] comtypes unavailable → fallback: %s", e)
            return None

        com_initialized = False

        try:
            comtypes.CoInitialize()
            com_initialized = True

            # ── Properly create IUIAutomation COM object ──
            # On Windows 10/11 the UIAutomation typelib (UIAutomationClient.tlb)
            # is always available. Try loading it first for proper vtable binding.
            # Fallback: use raw IUnknown (won't have GetFocusedElement but will
            # be caught by outer except and fall through to clipboard).
            try:
                from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
                uia = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
            except Exception:
                # Typelib not generated yet — CreateObject returns IUnknown,
                # which will raise AttributeError on GetFocusedElement.
                # That's caught by outer except and falls through.
                uia = comtypes.client.CreateObject(
                    "{ff48dba4-60ef-4201-aa87-54103eef594e}")

            elem = uia.GetFocusedElement()
            if elem is None:
                logger.info("[INJECT-UIA] no focused element → fallback")
                return None

            # ── Try ValuePattern SetValue ──
            try:
                vp = elem.GetCurrentPattern(10002).QueryInterface(
                    "{EA3A3B8A-4B6E-4B9E-9F6A-6F6B5B2F9B8B}")
                vp.SetValue(text)
                logger.info("[INJECT-UIA] SetValue called — verifying read-back")
            except Exception:
                logger.info("[INJECT-UIA] ValuePattern not available → no action")
                return None

            # ── Read-back verification (with timeout) ──
            readback_ok = self._verify_uia_readback(text, elem)
            if readback_ok:
                logger.info("[INJECT-UIA] read-back verified → OK")
                return True
            else:
                logger.info(
                    "[INJECT-UIA] read-back failed/mismatch → "
                    "SetValue may have modified target, returning False "
                    "(no clipboard fallthrough)")
                return False

        except Exception:
            logger.info("[INJECT-UIA] exception: %s", traceback.format_exc())
            return None
        finally:
            if com_initialized:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

    def _verify_uia_readback(self, expected: str, elem) -> bool:
        """Read back focused element value with 0.1s timeout. Returns True if match."""
        result = [None]
        error = [None]

        def _read():
            try:
                import comtypes
                comtypes.CoInitialize()
                try:
                    vp = elem.GetCurrentPattern(10002).QueryInterface(
                        "{EA3A3B8A-4B6E-4B9E-9F6A-6F6B5B2F9B8B}")
                    result[0] = (vp.CurrentValue or "")
                except Exception as e:
                    error[0] = str(e)[:80]
                finally:
                    comtypes.CoUninitialize()
            except Exception:
                pass

        t = threading.Thread(target=_read, daemon=True, name="uia-readback")
        t.start()
        t.join(0.1)  # 0.1s timeout per spec

        if t.is_alive():
            logger.warning("[INJECT-UIA] read-back timeout (0.1s) — UIA may be deadlocked")
            return False

        if error[0]:
            logger.info("[INJECT-UIA] read-back error: %s", error[0])
            return False

        read_text = result[0]
        if read_text is None:
            logger.info("[INJECT-UIA] read-back returned None")
            return False

        # Containment check — expected should appear in the element value.
        # Phase 3 fix: drop the reverse check (read_text in expected) which
        # produces false positives when readback is empty or short.
        if expected and expected in read_text:
            return True

        logger.info("[INJECT-UIA] read-back mismatch: expected=%r got=%r",
                    expected[:40], read_text[:40])
        return False

    def get_foreground_window_info(self) -> tuple[str, str, str, str]:
        """Get (proc, class, title, class) for the foreground window."""
        hwnd, cls, pid, proc = self._foreground_info()
        if not hwnd:
            return "", "", "", ""
        title_buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 512)
        return proc, cls, title_buf.value or "", cls


# ── UIPI check ───────────────────────────────────────────────
# Windows User Interface Privilege Isolation: a low-integrity process
# cannot send input (keybd_event / SendInput) to a high-integrity window.
# This affects WH_KEYBOARD_LL hooks when an admin window is in the foreground.

def is_uipi_blocked() -> bool:
    """Return True if the foreground window is elevated and we are not."""
    try:
        import ctypes
        from ctypes import wintypes
        # Get foreground window PID
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return False
        fg_pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(fg_pid))
        if not fg_pid:
            return False
        # Check if we are elevated
        our_elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
        if our_elevated:
            return False  # we are admin too, UIPI doesn't block
        # Check if foreground process is elevated
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        TOKEN_QUERY = 0x0008
        h_proc = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, fg_pid)
        if not h_proc:
            return False
        try:
            h_token = wintypes.HANDLE()
            if not ctypes.windll.advapi32.OpenProcessToken(
                    h_proc, TOKEN_QUERY, ctypes.byref(h_token)):
                return False
            try:
                elevation = wintypes.DWORD()
                size = wintypes.DWORD(ctypes.sizeof(elevation))
                ok = ctypes.windll.advapi32.GetTokenInformation(
                    h_token, 20,  # TokenElevation = 20
                    ctypes.byref(elevation), ctypes.sizeof(elevation),
                    ctypes.byref(size))
                if not ok:
                    return False
                return bool(elevation.value)
            finally:
                ctypes.windll.kernel32.CloseHandle(h_token)
        finally:
            ctypes.windll.kernel32.CloseHandle(h_proc)
    except Exception:
        return False

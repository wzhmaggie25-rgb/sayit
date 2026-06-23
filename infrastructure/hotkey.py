"""Global hotkey manager — single key or combo hotkey (modifiers + main key).

Toggle mode: press once to start recording, again to stop.
Default: RAlt (Right Alt, VK_RMENU=0xA5). User can customize any single key or combo.

Three trigger modes, auto-detected from parse_combo():
  (A) Single non-modifier  (e.g. F9)     → suppress key down+up
  (B) Single modifier      (e.g. RAlt)   → suppress own down+up (SYS messages)
  (C) Combo                (e.g. Ctrl+A) → modifiers pass through, only main key suppressed

Architecture: raw ctypes WH_KEYBOARD_LL hook. When the hook proc returns 1 (non-zero),
the event is blocked from reaching the OS. No pynput — pynput's win32_event_filter only
skips on_press/on_release callbacks; it does NOT suppress at the OS level.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ── VK tables ─────────────────────────────────────────────────

KEY_NAME_TO_VK = {
    # letters
    "A":0x41,"B":0x42,"C":0x43,"D":0x44,"E":0x45,"F":0x46,
    "G":0x47,"H":0x48,"I":0x49,"J":0x4A,"K":0x4B,"L":0x4C,
    "M":0x4D,"N":0x4E,"O":0x4F,"P":0x50,"Q":0x51,"R":0x52,
    "S":0x53,"T":0x54,"U":0x55,"V":0x56,"W":0x57,"X":0x58,
    "Y":0x59,"Z":0x5A,
    # digits
    "0":0x30,"1":0x31,"2":0x32,"3":0x33,"4":0x34,
    "5":0x35,"6":0x36,"7":0x37,"8":0x38,"9":0x39,
    # function keys
    "F1":0x70,"F2":0x71,"F3":0x72,"F4":0x73,"F5":0x74,
    "F6":0x75,"F7":0x76,"F8":0x77,"F9":0x78,"F10":0x79,
    "F11":0x7A,"F12":0x7B,
    # special keys
    "Space":0x20,"Tab":0x09,"Enter":0x0D,"Backspace":0x08,
    "Escape":0x1B,"Delete":0x2E,"Insert":0x2D,
    "Home":0x24,"End":0x23,"PageUp":0x21,"PageDown":0x22,
    "Up":0x26,"Down":0x28,"Left":0x25,"Right":0x27,
    "CapsLock":0x14,"NumLock":0x90,"ScrollLock":0x91,
    "PrintScreen":0x2C,"Pause":0x13,
    # symbols
    "`":0xC0,"-":0xBD,"=":0xBB,"[":0xDB,"]":0xDD,"\\":0xDC,
    ";":0xBA,"'":0xDE,",":0xBC,".":0xBE,"/":0xBF,
    # numpad
    "Numpad0":0x60,"Numpad1":0x61,"Numpad2":0x62,
    "Numpad3":0x63,"Numpad4":0x64,"Numpad5":0x65,
    "Numpad6":0x66,"Numpad7":0x67,"Numpad8":0x68,
    "Numpad9":0x69,
    "NumpadMultiply":0x6A,"NumpadAdd":0x6B,
    "NumpadSubtract":0x6D,"NumpadDecimal":0x6E,"NumpadDivide":0x6F,
    # L/R modifier keys (for single-key triggers)
    "RAlt":0xA5,"LAlt":0xA4,"RCtrl":0xA3,"LCtrl":0xA2,
    "RShift":0xA1,"LShift":0xA0,
}

VK_TO_KEY_NAME = {v:k for k,v in KEY_NAME_TO_VK.items()}
for vk, name in {0xA2:"LCtrl",0xA3:"RCtrl",0x11:"Ctrl",
                 0xA0:"LShift",0xA1:"RShift",0x10:"Shift",
                 0xA4:"LAlt",0xA5:"RAlt",0x12:"Alt",
                 0x5B:"LWin",0x5C:"RWin"}.items():
    if vk not in VK_TO_KEY_NAME:
        VK_TO_KEY_NAME[vk] = name

ALL_MODIFIER_NAMES = {"Ctrl","Shift","Alt","Win",
                      "LCtrl","RCtrl","LShift","RShift","LAlt","RAlt"}

GENERIC_MODIFIER_NAMES = {"Ctrl","Shift","Alt","Win"}

MODIFIER_VK_SET = {0x11,0x10,0x12,0x5B,0x5C,0xA0,0xA1,0xA2,0xA3,0xA4,0xA5}

KEY_DOWN  = {0x0100, 0x0104}   # WM_KEYDOWN, WM_SYSKEYDOWN
KEY_UP    = {0x0101, 0x0105}   # WM_KEYUP,   WM_SYSKEYUP

DEFAULT_HOTKEY = "RAlt"
DEBOUNCE_MS = 0.200


# ── Helpers ────────────────────────────────────────────────────

def _to_generic(name: str) -> str:
    return {"LCtrl":"Ctrl","RCtrl":"Ctrl",
            "LShift":"Shift","RShift":"Shift",
            "LAlt":"Alt","RAlt":"Alt"}.get(name, name)

def _is_modifier(vk: int) -> bool:
    return vk in MODIFIER_VK_SET

def _is_down(msg: int) -> bool:
    return msg in KEY_DOWN

def _is_up(msg: int) -> bool:
    return msg in KEY_UP

def _resolve_vk(vk: int, flags: int) -> int:
    if vk == 0x12:  # VK_MENU
        return 0xA5 if (flags & 0x01) else 0xA4
    if vk == 0x11:  # VK_CONTROL
        return 0xA3 if (flags & 0x01) else 0xA2
    return vk

def _is_altgr_fake_ctrl(vk: int, scanCode: int) -> bool:
    return vk == 0xA2 and (scanCode & 0x200)

def parse_combo(s: str) -> tuple[set, str]:
    """Parse hotkey string. Returns (generic_modifiers_set, raw_main_key)."""
    parts = [p.strip() for p in s.split("+")]
    if not parts:
        return set(), ""
    modifiers = set()
    for p in parts[:-1]:
        if p in ALL_MODIFIER_NAMES:
            modifiers.add(_to_generic(p))
    main = parts[-1]
    return modifiers, main


# ── Mask key (vkE8) for preempting SC_KEYMENU ─────────────────

_VK_MASK = 0xE8  # Microsoft-designated "unassigned" VK
_KEYEVENTF_KEYUP = 0x0002

def _send_mask_key():
    """Inject vkE8 down+up to preempt Windows menu activation.

    Even if the WH_KEYBOARD_LL suppress leaks, the OS sees an intervening key
    between Alt-down and Alt-up, so SC_KEYMENU is not triggered.
    Battle-tested in Typeless / Lightning Talk.
    """
    ctypes.windll.user32.keybd_event(_VK_MASK, 0, 0, 0)
    ctypes.windll.user32.keybd_event(_VK_MASK, 0, _KEYEVENTF_KEYUP, 0)


def _force_release_hotkey_modifiers(reason: str = ""):
    """Clear logical Alt state after a suppressed single-modifier hotkey."""
    for vk in (0xA5, 0xA4, 0x12):
        ctypes.windll.user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)
    _send_mask_key()
    logger.info("[hotkey] forced Alt release reason=%s", reason)


# ── Raw WH_KEYBOARD_LL hook (ctypes) ──────────────────────────

class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

# HOOKPROC signature: LRESULT CALLBACK(int nCode, WPARAM wParam, LPARAM lParam)
_HOOKPROC = ctypes.WINFUNCTYPE(
    wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_SetWindowsHookEx = _user32.SetWindowsHookExW
_SetWindowsHookEx.argtypes = (ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
_SetWindowsHookEx.restype = wintypes.HHOOK

_UnhookWindowsHookEx = _user32.UnhookWindowsHookEx
_UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
_UnhookWindowsHookEx.restype = wintypes.BOOL

_CallNextHookEx = _user32.CallNextHookEx
_CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_CallNextHookEx.restype = wintypes.LPARAM

_GetMessage = _user32.GetMessageW
_GetMessage.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
_GetMessage.restype = wintypes.BOOL

_PostThreadMessage = _user32.PostThreadMessageW
_PostThreadMessage.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_PostThreadMessage.restype = wintypes.BOOL

WH_KEYBOARD_LL = 13
WM_QUIT = 0x0012


class HotkeyManager:
    """Hotkey manager — raw WH_KEYBOARD_LL hook + poll heartbeat.

    Toggle mode: one press starts recording, next press stops.
    Uses raw ctypes hook because pynput's win32_event_filter doesn't actually
    suppress events at the OS level (it only skips on_press/on_release callbacks).
    """

    # Module-level hook state (only one HotkeyManager per process)
    _hook_installed = False
    _hook_handle: Optional[wintypes.HHOOK] = None
    _pump_thread: Optional[threading.Thread] = None
    _pump_thread_id: int = 0
    _pump_running = False

    def __init__(self, on_start: Callable, on_stop: Callable,
                 hotkey_name: str = DEFAULT_HOTKEY):
        self.on_start = on_start
        self.on_stop = on_stop
        self._recording = False

        # ── Parse combo ──
        self._required_mods, self._main_key = parse_combo(hotkey_name)
        self._main_vk = KEY_NAME_TO_VK.get(self._main_key)
        if self._main_vk is None:
            logger.error("[hotkey] Unknown main key '%s', falling back to RAlt",
                         self._main_key)
            self._main_key = "RAlt"
            self._main_vk = KEY_NAME_TO_VK["RAlt"]
            self._required_mods = set()

        self._recorded_mods = set()
        self._state = 'IDLE'
        self._last_toggle_ts = 0.0
        self._lock = threading.Lock()
        self._toggling = False
        self._processing = False
        self._single_key_mode = (len(self._required_mods) == 0)

        # Lifecycle
        self._active = False

        logger.info("[hotkey] combo=%s mods=%s main='%s'(VK=0x%02X) single_key=%s",
                    hotkey_name, self._required_mods, self._main_key, self._main_vk,
                    self._single_key_mode)

    # ── Win32 hook filter (called from LowLevelKeyboardProc) ─

    def _win32_filter(self, msg, data):
        """Called from the Windows hook proc. Return False to suppress event."""
        vk = data.vkCode
        _flags = data.flags
        _scan = data.scanCode

        # 1. Always pass through injected events (from our own SendInput)
        if _flags & 0x10:   # LLKHF_INJECTED
            return True

        # 2. Suppress AltGr fake Ctrl (scanCode bit 9 set)
        if _is_altgr_fake_ctrl(vk, _scan):
            return False

        # Resolve L/R for modifier keys
        is_mod = _is_modifier(vk)
        resolved_vk = _resolve_vk(vk, _flags) if is_mod else vk
        is_main = (resolved_vk == self._main_vk)

        with self._lock:
            s = self._state
            ltt = self._last_toggle_ts

        now = time.monotonic()

        with self._lock:
            processing = self._processing
        if processing and is_main and (_is_down(msg) or _is_up(msg)):
            _force_release_hotkey_modifiers("pipeline_busy")
            self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'BUSY(suppress)', False)
            return False

        # ── IDLE ──
        if s == 'IDLE':
            # ── Mode B: Single modifier key trigger (default: RAlt) ──
            if self._single_key_mode and is_mod:
                if is_main and _is_down(msg):
                    with self._lock:
                        self._state = 'MATCHED'
                    _send_mask_key()  # vkE8: preempt SC_KEYMENU (belt-and-suspenders)
                    self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE→MATCHED', False)
                    return False
                if is_main and _is_up(msg):
                    self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE(stray-up)', False)
                    return False
                self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE(pass)', True)
                return True

            # ── Mode A: Single non-modifier (e.g. F9) ──
            if self._single_key_mode and not is_mod:
                if is_main and _is_down(msg):
                    with self._lock:
                        self._state = 'MATCHED'
                    self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE→MATCHED', False)
                    return False
                self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE(pass)', True)
                return True

            # ── Mode C: Combo (modifiers + main key) ──
            if not self._single_key_mode:
                if is_mod:
                    name = VK_TO_KEY_NAME.get(vk, "")
                    generic = _to_generic(name)
                    if generic in self._required_mods:
                        with self._lock:
                            self._recorded_mods.add(generic)
                    self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE(mod-pass)', True)
                    return True

                with self._lock:
                    ready = self._recorded_mods >= self._required_mods

                if ready and is_main and _is_down(msg):
                    with self._lock:
                        self._state = 'MATCHED'
                        self._recorded_mods.clear()
                    self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE→MATCHED', False)
                    return False

                self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE(pass)', True)
                return True

            self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'IDLE(pass)', True)
            return True

        # ── MATCHED ──
        if s == 'MATCHED':
            if is_main:
                if _is_up(msg):
                    with self._lock:
                        self._state = 'IDLE'
                        self._last_toggle_ts = now
                    self._do_toggle()
                    if self._single_key_mode and _is_modifier(self._main_vk):
                        _force_release_hotkey_modifiers("matched_key_up")
                    self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'MATCHED→IDLE(toggle)', False)
                    return False
                else:
                    self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'MATCHED(repeat)', False)
                    return False

            # Mode B: other key down while main modifier held → cancel match
            if self._single_key_mode and _is_modifier(self._main_vk) and _is_down(msg):
                with self._lock:
                    self._state = 'IDLE'
                self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'MATCHED→IDLE(cancel)', True)
                return True

            self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, 'MATCHED(pass)', True)
            return True

        self._log_filter(msg, vk, _flags, _scan, resolved_vk, is_main, '?(pass)', True)
        return True

    def _log_filter(self, msg, vk, flags, scan, resolved_vk, is_main, action, result):
        """Per-event log for verifying hook behavior (set to DEBUG in prod)."""
        logger.info(
            "[hotkey] msg=%-4d vk=0x%02X→0x%02X flags=0x%04X scan=0x%03X "
            "main=%s state=%-6s action=%-22s → %s",
            msg, vk, resolved_vk, flags, scan,
            "Y" if is_main else "n", self._state,
            action, "PASS" if result else "SUPPRESS"
        )

    # ── Toggle logic ───────────────────────────────────────

    def _do_toggle(self):
        """Dispatch toggle action to a background thread so the hook callback
        returns immediately and the message pump is never blocked.

        Rapid double-presses are guarded by _toggling flag — a second press
        while the first toggle is still running is silently dropped.
        """
        with self._lock:
            if self._toggling:
                logger.info("[hotkey] toggle skipped — previous toggle still in flight")
                return
            if self._processing:
                logger.info("[hotkey] toggle skipped - pipeline processing")
                _force_release_hotkey_modifiers("toggle_processing")
                return
            self._toggling = True

        threading.Thread(target=self._do_toggle_sync, daemon=True, name="hotkey-toggle").start()

    def _do_toggle_sync(self):
        """Actual toggle logic, runs on a background thread."""
        try:
            if not self._recording:
                logger.info("[hotkey] toggle → start recording")
                try:
                    accepted = self.on_start()
                    self._recording = accepted is not False
                    if not self._recording:
                        logger.info("[hotkey] start rejected by backend")
                except Exception as e:
                    self._recording = False
                    logger.error("[hotkey] on_start error: %s", e)
            else:
                logger.info("[hotkey] toggle → stop recording")
                try:
                    accepted = self.on_stop()
                    if accepted is not False:
                        # Keep the hotkey in busy state until the backend
                        # releases the full ASR/AI/injection pipeline.
                        with self._lock:
                            self._processing = True
                        logger.info("[hotkey] stop accepted; entering processing guard")
                    else:
                        self._recording = False
                        logger.info("[hotkey] stop ignored by backend")
                except Exception as e:
                    logger.error("[hotkey] on_stop error: %s", e)
        finally:
            if self._single_key_mode and _is_modifier(self._main_vk):
                _force_release_hotkey_modifiers("toggle_finally")
            with self._lock:
                self._toggling = False

    # ── Lifecycle ──────────────────────────────────────────

    def start(self):
        """Install WH_KEYBOARD_LL hook and start message pump on a dedicated thread.

        CRITICAL: SetWindowsHookEx AND GetMessage MUST run on the same thread,
        otherwise WH_KEYBOARD_LL callbacks are never dispatched.
        """
        if HotkeyManager._hook_installed:
            logger.warning("[hotkey] Hook already installed")
            return

        self._active = True
        self._state = 'IDLE'
        self._last_toggle_ts = 0.0
        self._recorded_mods.clear()

        HotkeyManager._pump_running = True
        HotkeyManager._pump_thread = threading.Thread(
            target=self._hook_thread, daemon=True, name="hotkey-hook")
        HotkeyManager._pump_thread.start()

        # Wait briefly for the hook to be installed
        for _ in range(50):  # 500ms max
            if HotkeyManager._hook_installed or HotkeyManager._hook_handle:
                break
            time.sleep(0.01)

        if not HotkeyManager._hook_handle:
            logger.error("[hotkey] Hook install timed out or failed")
            self._active = False
            HotkeyManager._pump_running = False

    def _hook_thread(self):
        """Single thread: define hook proc, install hook, run message pump."""
        _self = self  # capture for closure

        _first_call = [True]  # mutable to avoid nonlocal

        @_HOOKPROC
        def _hook_proc(nCode, wParam, lParam):
            if _first_call[0]:
                _first_call[0] = False
                logger.info("[hotkey] HOOK_ALIVE! First callback: nCode=%d wParam=0x%X",
                           nCode, wParam)
            if nCode >= 0:  # HC_ACTION
                data = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                try:
                    result = _self._win32_filter(wParam, data)
                except Exception as e:
                    logger.warning("[hotkey] filter exception: %s", e)
                    result = True
                if result is False:
                    return 1  # Non-zero = suppress event at OS level
                elif result is True:
                    pass  # fall through to CallNextHookEx
                else:
                    logger.warning("[hotkey] filter returned non-bool: %r (type=%s)",
                                   result, type(result).__name__)
            return _CallNextHookEx(hHook, nCode, wParam, lParam)

        # Prevent GC — keep a strong reference on this HotkeyManager instance
        self._hook_proc_ref = _hook_proc

        # Install hook ON THIS THREAD (critical — same thread as GetMessage below)
        hHook = _SetWindowsHookEx(WH_KEYBOARD_LL, _hook_proc, None, 0)
        err = ctypes.get_last_error()
        logger.info("[hotkey] SetWindowsHookEx returned hHook=0x%X GetLastError=%d",
                   hHook or 0, err)
        if not hHook:
            logger.error("[hotkey] SetWindowsHookEx FAILED — hook not installed!")
            HotkeyManager._hook_handle = None
            return

        HotkeyManager._hook_handle = hHook
        HotkeyManager._hook_installed = True
        HotkeyManager._pump_thread_id = _kernel32.GetCurrentThreadId()
        logger.info("[hotkey] hook installed (hHook=0x%X thread=%d main_vk=0x%02X)",
                   hHook, HotkeyManager._pump_thread_id, self._main_vk)

        # ── Message pump (MUST run on same thread as SetWindowsHookEx) ──
        msg = wintypes.MSG()
        while HotkeyManager._pump_running:
            ret = _GetMessage(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:  # WM_QUIT (0) or error (-1)
                break
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup
        HotkeyManager._hook_installed = False
        if hHook:
            _UnhookWindowsHookEx(hHook)
            HotkeyManager._hook_handle = None
        self._hook_proc_ref = None
        logger.info("[hotkey] hook thread exited (pump stopped)")

    def stop(self):
        """Uninstall hook and stop message pump."""
        self._active = False
        HotkeyManager._pump_running = False

        # Wake up the message pump to exit
        if HotkeyManager._pump_thread_id:
            _PostThreadMessage(HotkeyManager._pump_thread_id, WM_QUIT, 0, 0)

        if HotkeyManager._pump_thread and HotkeyManager._pump_thread.is_alive():
            HotkeyManager._pump_thread.join(timeout=1.0)

        with self._lock:
            self._state = 'IDLE'
            self._recorded_mods.clear()

        logger.info("[hotkey] stopped")

    def pause(self):
        """Pause hook without changing _active intent."""
        self.stop()
        self._active = True  # restore intent
        logger.info("[hotkey] paused (_active=%s)", self._active)

    def resume(self):
        """Resume hook if _active is True."""
        if self._active:
            self.start()
            logger.info("[hotkey] resumed")

    def is_recording(self) -> bool:
        return self._recording

    def set_recording(self, recording: bool):
        """Synchronize hotkey-local toggle state with backend pipeline truth."""
        with self._lock:
            self._recording = bool(recording)
            if not recording:
                self._processing = False
                _force_release_hotkey_modifiers("set_recording_false")

    def update_hotkey(self, name: str) -> bool:
        """Update hotkey combo dynamically. Restarts hook if _active."""
        mods, main = parse_combo(name)
        main_vk = KEY_NAME_TO_VK.get(main)
        if main_vk is None:
            logger.warning("[hotkey] Unknown key '%s', ignoring update", main)
            return False

        was_active = self._active
        if was_active:
            self.pause()

        self._required_mods = mods
        self._main_key = main
        self._main_vk = main_vk
        self._single_key_mode = (len(mods) == 0)
        self._recorded_mods.clear()
        self._last_toggle_ts = 0.0
        with self._lock:
            self._state = 'IDLE'

        if was_active:
            self.start()

        logger.info("[hotkey] updated to %s single_key=%s", name, self._single_key_mode)
        return True

    # Legacy _message_pump replaced by _hook_thread (merged hook + pump)

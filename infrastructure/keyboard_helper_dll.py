"""Keyboard helper DLL — WH_KEYBOARD_LL hook via ctypes (Typeless architecture v2).

v2 (2026-06-26)
---------------
The C++ HookProc no longer calls Python directly. Instead, the hook thread
signals a native auto-reset event and a *native worker thread* (inside the
DLL) consumes the signal and invokes the Python callback. The Python side
keeps the original guarantee of running each toggle on its own daemon
thread so the worker thread is never stuck inside long-running Python work.

ABI exported by sayit_keyboard_helper.dll:

    int install_hook(void* callback)              -> 1 on success
    int uninstall_hook()                          -> 1
    int is_hook_installed()                       -> 1 / 0
    unsigned long get_pending_count()             -> not-yet-consumed toggles
    unsigned long get_total_emitted()             -> lifetime emitted (install scope)
    unsigned long get_total_consumed()            -> lifetime consumed (install scope)
    int __test_trigger_toggle()                   -> test-only; emits one toggle
                                                     identical to an RAlt up event,
                                                     bypassing physical keys.
"""
from __future__ import annotations
import ctypes
import logging
import os
import threading
import time

from infrastructure.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

_CALLBACK_TYPE = ctypes.CFUNCTYPE(None)  # void(*)()
_HOOK_INSTALL_LOCK = threading.Lock()
_CALLBACK_HANDLE = None  # keep ctypes thunk alive while installed


class _LibLoader:
    """Thread-safe lazy loader for sayit_keyboard_helper.dll."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._lib = None
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._lib = None

    def load(self):
        if self._lib is not None:
            return self._lib

        dll_path = self._find_dll()
        if not dll_path:
            logger.warning("[keyboard-helper] DLL not found")
            return None

        try:
            self._lib = ctypes.CDLL(dll_path)
        except OSError as e:
            logger.warning("[keyboard-helper] load failed: %s", e)
            return None

        self._lib.install_hook.argtypes = [ctypes.c_void_p]
        self._lib.install_hook.restype = ctypes.c_int

        self._lib.uninstall_hook.argtypes = []
        self._lib.uninstall_hook.restype = ctypes.c_int

        self._lib.is_hook_installed.argtypes = []
        self._lib.is_hook_installed.restype = ctypes.c_int

        # Optional symbols (older builds of the DLL may not export these).
        for name, restype in (
            ("get_pending_count", ctypes.c_ulong),
            ("get_total_emitted", ctypes.c_ulong),
            ("get_total_consumed", ctypes.c_ulong),
            ("__test_trigger_toggle", ctypes.c_int),
        ):
            try:
                fn = getattr(self._lib, name)
                fn.argtypes = []
                fn.restype = restype
            except AttributeError:
                logger.info(
                    "[keyboard-helper] optional export %s not present (older DLL)",
                    name)

        logger.info("[keyboard-helper] loaded from %s", dll_path)
        return self._lib

    @staticmethod
    def _find_dll() -> str | None:
        # The DLL lives under <repo>/native/context_helper/build/...
        # Resolve relative to this source file too — PROJECT_ROOT is derived
        # from __main__.__file__ and is incorrect under pytest / other hosts.
        here_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        roots = [PROJECT_ROOT, here_root]
        candidates: list[str] = []
        for root in roots:
            candidates.extend([
                os.path.join(root, "native", "context_helper", "build", "Release",
                             "sayit_keyboard_helper.dll"),
                os.path.join(root, "native", "context_helper", "build", "Debug",
                             "sayit_keyboard_helper.dll"),
                os.path.join(root, "native", "context_helper", "build",
                             "sayit_keyboard_helper.dll"),
                os.path.join(root, "bin", "sayit_keyboard_helper.dll"),
            ])
        for path in candidates:
            if os.path.exists(path):
                return os.path.realpath(path)
        return None

    @property
    def is_loaded(self) -> bool:
        return self._lib is not None


class KeyboardHelperDll:
    """Keyboard hook via ctypes. Singleton — one WH_KEYBOARD_LL per process."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._loader = _LibLoader()
        self._lib = self._loader.load()
        self._installed = False

    @property
    def is_available(self) -> bool:
        return self._lib is not None

    @property
    def lib(self):
        """Test-only accessor for raw ctypes lib handle."""
        return self._lib

    def install(self, callback) -> bool:
        """Install the WH_KEYBOARD_LL hook with a zero-arg Python callback.

        v2 layering:
          - HookProc (C++)                — never touches Python
          - Worker thread (C++)            — receives SetEvent, calls _dispatch
          - _dispatch (this module)        — spawns a daemon thread per toggle
                                             so worker is never blocked
          - business callback (orchestrator.toggle_recording)

        Returns True on success.
        """
        global _CALLBACK_HANDLE

        if not self.is_available:
            logger.warning("[keyboard-helper] cannot install — DLL not loaded")
            return False

        if not callable(callback):
            logger.warning("[keyboard-helper] install: callback is not callable")
            return False

        with _HOOK_INSTALL_LOCK:
            if self._lib.is_hook_installed():
                logger.warning("[keyboard-helper] already installed")
                return False

            # ── Worker-thread → Python dispatch ─────────────────
            # The worker thread invokes _dispatch. We still spawn a daemon
            # thread per toggle so any business work that blocks (audio
            # device, ASR, injection) does not starve the worker queue.
            def _dispatch():
                try:
                    threading.Thread(
                        target=callback, daemon=True, name="hotkey-dispatch"
                    ).start()
                except Exception as e:
                    logger.warning("[keyboard-helper] dispatch failed: %s", e)

            _CALLBACK_HANDLE = _CALLBACK_TYPE(_dispatch)

            result = self._lib.install_hook(_CALLBACK_HANDLE)
            self._installed = (result == 1)

        logger.info("[keyboard-helper] install: %s",
                    "OK" if self._installed else "FAILED")
        return self._installed

    def uninstall(self):
        """Uninstall the WH_KEYBOARD_LL hook.

        The DLL now joins both the hook thread and the worker thread before
        uninstall_hook returns, so by the time we drop _CALLBACK_HANDLE no
        native thread can still reference it.
        """
        global _CALLBACK_HANDLE

        with _HOOK_INSTALL_LOCK:
            if self._lib and self._lib.is_hook_installed():
                self._lib.uninstall_hook()
                self._installed = False
                _CALLBACK_HANDLE = None
                logger.info("[keyboard-helper] uninstalled")

    @property
    def is_installed(self) -> bool:
        if not self._lib:
            return False
        return self._lib.is_hook_installed() == 1

    # ── Test-only introspection ─────────────────────────────

    def get_pending_count(self) -> int:
        if not self._lib or not hasattr(self._lib, "get_pending_count"):
            return -1
        return int(self._lib.get_pending_count())

    def get_total_emitted(self) -> int:
        if not self._lib or not hasattr(self._lib, "get_total_emitted"):
            return -1
        return int(self._lib.get_total_emitted())

    def get_total_consumed(self) -> int:
        if not self._lib or not hasattr(self._lib, "get_total_consumed"):
            return -1
        return int(self._lib.get_total_consumed())

    def test_trigger_toggle(self) -> bool:
        """Test-only: synthesize an RAlt-up emit from C++ side.

        Behavior is identical to what HookProc does on the RAlt rising edge
        EXCEPT no physical key is involved and the entry point cannot be
        reached from the LowLevelHooks pipeline. Used by the stress test to
        validate the native producer → worker → Python transport.
        """
        if not self._lib:
            return False
        try:
            fn = getattr(self._lib, "__test_trigger_toggle")
        except AttributeError:
            return False
        return fn() == 1

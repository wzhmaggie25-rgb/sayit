"""Keyboard helper DLL — WH_KEYBOARD_LL hook via ctypes (Typeless architecture).

Loads sayit_keyboard_helper.dll and provides a Pythonic interface to
the RAlt toggle hook.

Typeless pattern: in-process DLL call — identical to Typeless' koffi approach
but using Python's built-in ctypes to avoid external dependencies.
"""
from __future__ import annotations
import ctypes
import logging
import os
import threading
import time
from ctypes import wintypes

from infrastructure.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

_CALLBACK_TYPE = ctypes.CFUNCTYPE(None)  # void(*)()
_HOOK_LIBRARY = None
_HOOK_INSTALL_LOCK = threading.Lock()
_CALLBACK_HANDLE = None  # keep reference to prevent gc


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

        # Bind exported functions
        self._lib.install_hook.argtypes = [ctypes.c_void_p]
        self._lib.install_hook.restype = ctypes.c_int

        self._lib.uninstall_hook.argtypes = []
        self._lib.uninstall_hook.restype = ctypes.c_int

        self._lib.is_hook_installed.argtypes = []
        self._lib.is_hook_installed.restype = ctypes.c_int

        logger.info("[keyboard-helper] loaded from %s", dll_path)
        return self._lib

    @staticmethod
    def _find_dll() -> str | None:
        """Search for sayit_keyboard_helper.dll in known build locations."""
        candidates = [
            os.path.join(PROJECT_ROOT, "native", "context_helper", "build", "Release",
                         "sayit_keyboard_helper.dll"),
            os.path.join(PROJECT_ROOT, "native", "context_helper", "build", "Debug",
                         "sayit_keyboard_helper.dll"),
            os.path.join(PROJECT_ROOT, "native", "context_helper", "build",
                         "sayit_keyboard_helper.dll"),
            os.path.join(PROJECT_ROOT, "bin", "sayit_keyboard_helper.dll"),
        ]
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

    def install(self, callback) -> bool:
        """Install the WH_KEYBOARD_LL hook with a zero-arg Python callback.

        The callback is called on a background daemon thread, NOT on the hook
        thread — preventing LowLevelHooksTimeout from silently unhooking the
        hook when the callback takes too long (GIL contention, Win32 calls).

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

            # ── Dispatch wrapper ──────────────────────────────────
            # The hook thread (WH_KEYBOARD_LL) must return within ~300ms
            # or Windows silently unhooks. We cannot do any Python work
            # synchronously on it — especially under GIL contention from
            # _process_chunk (pure-Python per-sample audio processing).
            #
            # Solution: the ctypes callback only spawns a daemon thread,
            # then returns immediately (~0.1ms on hook thread).
            def _dispatch():
                threading.Thread(
                    target=callback, daemon=True, name="hotkey-dispatch"
                ).start()

            # Create a ctypes callback pointing to _dispatch, NOT the
            # original user callback. Keep a reference to prevent GC.
            _CALLBACK_HANDLE = _CALLBACK_TYPE(_dispatch)

            result = self._lib.install_hook(_CALLBACK_HANDLE)
            self._installed = (result == 1)

        logger.info("[keyboard-helper] install: %s", "OK" if self._installed else "FAILED")
        return self._installed

    def uninstall(self):
        """Uninstall the WH_KEYBOARD_LL hook.

        Thread safety: the DLL sets g_callback = nullptr first (inside
        uninstall_hook), then posts WM_QUIT to the hook thread. We hold the
        ctypes callback handle (via _CALLBACK_HANDLE) until the hook thread
        has had time to exit, preventing a GC race where the ctypes thunk
        is destroyed while the hook thread still references it.
        """
        global _CALLBACK_HANDLE

        with _HOOK_INSTALL_LOCK:
            if self._lib and self._lib.is_hook_installed():
                self._lib.uninstall_hook()
                self._installed = False
                # Give the hook thread time to exit its GetMessage loop,
                # ensuring g_callback is no longer referenced before we
                # release the ctypes thunk.
                time.sleep(0.05)
                _CALLBACK_HANDLE = None
                logger.info("[keyboard-helper] uninstalled")

    @property
    def is_installed(self) -> bool:
        if not self._lib:
            return False
        return self._lib.is_hook_installed() == 1
"""In-process UIA access via sayit_context_helper_dll.dll (ctypes FFI).

Replaces the old exe+JSON-RPC subprocess architecture with a direct
in-process DLL call — identical to Typeless' koffi approach but using
Python's built-in ctypes to avoid external dependencies.

Usage:
    dll = ContextHelperDll()
    context = dll.get_full_context(hwnd=123456)
    if context:
        print(context["text_insertion_point"]["cursor_state"]["full_field_content"])
"""
from __future__ import annotations

import ctypes
import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

from infrastructure.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


class _LibLoader:
    """Lazy-load the DLL once and cache function bindings."""

    def __init__(self):
        self._lib: Optional[ctypes.CDLL] = None
        self._lock = threading.Lock()
        self._load_error = ""

    def load(self) -> bool:
        if self._lib is not None:
            return True
        with self._lock:
            if self._lib is not None:
                return True
            dll_path = self._find_dll()
            if not dll_path:
                self._load_error = "dll not found"
                return False
            try:
                lib = ctypes.CDLL(str(dll_path))
                # get_full_context_json(HWND hwnd) -> char*
                lib.get_full_context_json.argtypes = [ctypes.c_void_p]
                lib.get_full_context_json.restype = ctypes.c_char_p
                # get_focused_context_json(HWND hwnd) -> char*
                lib.get_focused_context_json.argtypes = [ctypes.c_void_p]
                lib.get_focused_context_json.restype = ctypes.c_char_p
                # poll_keyboard_events_json() -> char*
                lib.poll_keyboard_events_json.argtypes = []
                lib.poll_keyboard_events_json.restype = ctypes.c_char_p
                # free_string(char* ptr)
                lib.free_string.argtypes = [ctypes.c_char_p]
                lib.free_string.restype = None
                self._lib = lib
                logger.info("ContextHelper DLL loaded: %s", dll_path)
                return True
            except Exception as e:
                self._load_error = str(e)
                logger.warning("ContextHelper DLL load failed: %s", e)
                return False

    @property
    def load_error(self) -> str:
        return self._load_error

    def get_full_context(self, hwnd: int = 0) -> Optional[dict]:
        if not self.load():
            return None
        try:
            raw = self._lib.get_full_context_json(ctypes.c_void_p(hwnd))
            if not raw:
                return None
            result: dict = json.loads(raw.decode("utf-8"))
            return result
        except Exception as e:
            logger.debug("ContextHelper DLL get_full_context error: %s", e)
            return None
        finally:
            if raw:
                self._lib.free_string(raw)

    def get_focused_context(self, hwnd: int = 0) -> Optional[dict]:
        if not self.load():
            return None
        try:
            raw = self._lib.get_focused_context_json(ctypes.c_void_p(hwnd))
            if not raw:
                return None
            result: dict = json.loads(raw.decode("utf-8"))
            return result
        except Exception as e:
            logger.debug("ContextHelper DLL get_focused_context error: %s", e)
            return None
        finally:
            if raw:
                self._lib.free_string(raw)

    def poll_keyboard_events(self) -> list[dict]:
        if not self.load():
            return []
        try:
            raw = self._lib.poll_keyboard_events_json()
            if not raw:
                return []
            result: list = json.loads(raw.decode("utf-8"))
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.debug("ContextHelper DLL poll_keyboard_events error: %s", e)
            return []
        finally:
            if raw:
                self._lib.free_string(raw)

    @staticmethod
    def _find_dll() -> Optional[Path]:
        candidates = [
            Path(PROJECT_ROOT) / "native" / "context_helper" / "build" / "Release" / "sayit_context_helper_dll.dll",
            Path(PROJECT_ROOT) / "native" / "context_helper" / "build" / "Debug" / "sayit_context_helper_dll.dll",
            Path(PROJECT_ROOT) / "native" / "context_helper" / "build" / "sayit_context_helper_dll.dll",
            Path(PROJECT_ROOT) / "bin" / "sayit_context_helper_dll.dll",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None


class ContextHelperDll:
    """Singleton wrapper — mirrors ContextHelperClient interface for drop-in replacement."""

    _instance: Optional["ContextHelperDll"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "ContextHelperDll":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._loader = _LibLoader()

    @property
    def is_available(self) -> bool:
        return self._loader.load()

    def get_full_context(self, hwnd: int = 0, timeout: float = 0.5) -> Optional[dict]:
        return self._loader.get_full_context(hwnd)

    def get_full_context_for_window(self, hwnd: int, timeout: float = 0.5) -> Optional[dict]:
        return self._loader.get_full_context(hwnd)

    def get_focused_input_info(self, hwnd: int = 0, timeout: float = 0.5) -> Optional[dict]:
        return self._loader.get_focused_context(hwnd)

    def poll_keyboard_events(self, timeout: float = 0.2) -> list[dict]:
        return self._loader.poll_keyboard_events()
"""Client for the native Sayit ContextHelper JSON-RPC process."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from infrastructure.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


class ContextHelperClient:
    """Small stdin/stdout JSON-RPC client with conservative failure handling."""

    _instance: Optional["ContextHelperClient"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "ContextHelperClient":
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
        self._lock = threading.RLock()
        self._proc: Optional[subprocess.Popen] = None
        self._disabled_reason = ""

    def get_full_context(self, timeout: float = 0.8) -> Optional[dict]:
        result = self.call("get_full_context", timeout=timeout)
        return result if isinstance(result, dict) else None

    def get_full_context_for_window(self, hwnd: int, timeout: float = 0.8) -> Optional[dict]:
        result = self.call("get_full_context_for_window", {"hwnd": int(hwnd)}, timeout=timeout)
        return result if isinstance(result, dict) else None

    def get_focused_app_info(self, timeout: float = 0.5) -> Optional[dict]:
        result = self.call("get_focused_app_info", timeout=timeout)
        return result if isinstance(result, dict) else None

    def get_window_app_info(self, hwnd: int, timeout: float = 0.5) -> Optional[dict]:
        result = self.call("get_window_app_info", {"hwnd": int(hwnd)}, timeout=timeout)
        return result if isinstance(result, dict) else None

    def get_focused_input_info(self, timeout: float = 0.5) -> Optional[dict]:
        result = self.call("get_focused_input_info", timeout=timeout)
        return result if isinstance(result, dict) else None

    def get_window_input_info(self, hwnd: int, timeout: float = 0.5) -> Optional[dict]:
        result = self.call("get_window_input_info", {"hwnd": int(hwnd)}, timeout=timeout)
        return result if isinstance(result, dict) else None

    def poll_keyboard_events(self, timeout: float = 0.2) -> list[dict]:
        result = self.call("poll_keyboard_events", timeout=timeout)
        return result if isinstance(result, list) else []

    def call(self, method: str, params: Optional[dict] = None,
             timeout: float = 0.5) -> Any:
        with self._lock:
            proc = self._ensure_process()
            if proc is None or proc.stdin is None or proc.stdout is None:
                return None
            request_id = uuid.uuid4().hex
            payload = {
                "id": request_id,
                "method": method,
                "params": params or {},
            }
            try:
                proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                proc.stdin.flush()
                line = self._readline_with_timeout(proc, timeout)
                if not line:
                    self._restart("timeout")
                    return None
                response = json.loads(line)
                if response.get("id") != request_id or not response.get("ok"):
                    logger.debug(
                        "ContextHelper native call failed method=%s response=%s",
                        method, response)
                    return None
                return response.get("result")
            except Exception as e:
                self._restart(str(e)[:120])
                return None

    def _ensure_process(self) -> Optional[subprocess.Popen]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        exe = self._helper_path()
        if not exe:
            if self._disabled_reason != "missing":
                logger.info("ContextHelper native helper missing; using Python fallback")
            self._disabled_reason = "missing"
            return None
        try:
            self._proc = subprocess.Popen(
                [str(exe)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._disabled_reason = ""
            logger.info("ContextHelper native helper started: %s", exe)
            return self._proc
        except Exception as e:
            self._proc = None
            self._disabled_reason = str(e)[:120]
            logger.info("ContextHelper native helper start failed: %s", self._disabled_reason)
            return None

    def _restart(self, reason: str):
        logger.debug("ContextHelper native helper restarting: %s", reason)
        self.close()
        self._disabled_reason = reason

    def close(self):
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except Exception:
            pass
        try:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=1.0)
        except Exception:
            pass
        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass

    @staticmethod
    def _readline_with_timeout(proc: subprocess.Popen, timeout: float) -> str:
        result: list[str] = []

        def _read():
            try:
                if proc.stdout is not None:
                    result.append(proc.stdout.readline())
            except Exception:
                result.append("")

        thread = threading.Thread(target=_read, daemon=True, name="context-helper-read")
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            return ""
        return result[0].strip() if result else ""

    @staticmethod
    def _helper_path() -> Optional[Path]:
        module_root = Path(__file__).resolve().parents[1]
        candidates = [
            Path(PROJECT_ROOT) / "native" / "context_helper" / "build" / "Release" / "sayit_context_helper.exe",
            Path(PROJECT_ROOT) / "native" / "context_helper" / "build" / "Debug" / "sayit_context_helper.exe",
            Path(PROJECT_ROOT) / "native" / "context_helper" / "build" / "sayit_context_helper.exe",
            Path(PROJECT_ROOT) / "bin" / "sayit_context_helper.exe",
            module_root / "native" / "context_helper" / "build" / "Release" / "sayit_context_helper.exe",
            module_root / "native" / "context_helper" / "build" / "Debug" / "sayit_context_helper.exe",
            module_root / "native" / "context_helper" / "build" / "sayit_context_helper.exe",
        ]
        env_path = os.environ.get("SAYIT_CONTEXT_HELPER")
        if env_path:
            candidate = Path(env_path)
            return candidate if candidate.exists() else None
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

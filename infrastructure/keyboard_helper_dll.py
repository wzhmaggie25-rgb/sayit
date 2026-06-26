"""Keyboard helper DLL — WH_KEYBOARD_LL hook via ctypes (Typeless architecture v2).

v2 (2026-06-26)
---------------
The C++ HookProc no longer calls Python directly. Instead, the hook thread
signals a native auto-reset event and a *native worker thread* (inside the
DLL) consumes the signal and invokes the Python callback. The Python side
keeps the original guarantee of running each toggle on its own daemon
thread so the worker thread is never stuck inside long-running Python work.

v2.1 (2026-06-26 stabilization round)
-------------------------------------
- Replaces the "spawn a daemon thread per toggle" pattern with a single
  ordered consumer thread. The previous implementation could theoretically
  reorder back-to-back toggles (start/stop) because the OS may schedule
  the second `hotkey-dispatch` thread before the first reaches the
  business callback. The consumer thread is reused for the lifetime of
  the install and drains a thread-safe queue in arrival order.
- Adds a diagnostic ring buffer (`recent_events()`) that records, per
  toggle: native sequence number, Python receive timestamp, dispatch
  timestamp, and dispatch elapsed time. Records ONLY sequence numbers
  and monotonic timestamps — never user text. Bounded to the last 64
  events so it cannot grow without limit.
- Records and exposes the DLL build identity (`helper_version` /
  `helper_build_id`) so we can prove at runtime which artifact is loaded.

ABI exported by sayit_keyboard_helper.dll (v2):

    int install_hook(void* callback)              -> 1 on success
    int uninstall_hook()                          -> 1
    int is_hook_installed()                       -> 1 / 0
    unsigned long get_pending_count()             -> not-yet-consumed toggles
    unsigned long get_total_emitted()             -> lifetime emitted (install scope)
    unsigned long get_total_consumed()            -> lifetime consumed (install scope)
    int __test_trigger_toggle()                   -> test-only; emits one toggle
                                                     identical to an RAlt up event,
                                                     bypassing physical keys.
    int __test_handle_event(vk, wParam, flags)    -> test-only; drives HookProc
                                                     parser with synthetic event
                                                     fields (no SendInput side
                                                     effects).
    void __test_reset_state()                     -> test-only; clear g_matched
    unsigned int helper_version()                 -> ABI version int
    const char* helper_build_id()                 -> build identity string
"""
from __future__ import annotations
import collections
import ctypes
import logging
import os
import queue
import threading
import time

from infrastructure.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

_CALLBACK_TYPE = ctypes.CFUNCTYPE(None)  # void(*)()
_HOOK_INSTALL_LOCK = threading.Lock()
_CALLBACK_HANDLE = None  # keep ctypes thunk alive while installed

# Minimum ABI version this Python module is compatible with. The DLL must
# export `helper_version` and return >= MIN_HELPER_VERSION; otherwise the
# loader logs a clear error and disables the hook rather than silently
# binding to a stale build.
MIN_HELPER_VERSION = 3

# Diagnostic ring buffer size. Each toggle records ~80 bytes of metadata
# (sequence numbers + monotonic timestamps + thread ids) — bounded so the
# diagnostic surface cannot grow during long sessions.
DIAG_RING_SIZE = 64


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
        self._dll_path = None

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
        self._dll_path = dll_path

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
            ("__test_reset_state", None),
            ("helper_version", ctypes.c_uint),
            ("helper_build_id", ctypes.c_char_p),
        ):
            try:
                fn = getattr(self._lib, name)
                fn.argtypes = []
                fn.restype = restype
            except AttributeError:
                logger.info(
                    "[keyboard-helper] optional export %s not present (older DLL)",
                    name)

        # __test_handle_event takes (vkCode, wParam, flags) — different signature
        try:
            fn = getattr(self._lib, "__test_handle_event")
            fn.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
            fn.restype = ctypes.c_int
        except AttributeError:
            logger.info(
                "[keyboard-helper] optional export __test_handle_event not present")

        # Native diagnostics (v3+)
        try:
            fn = getattr(self._lib, "native_event_count")
            fn.argtypes = []
            fn.restype = ctypes.c_ulong
        except AttributeError:
            pass
        try:
            fn = getattr(self._lib, "native_events")
            # native_events(NativeEventRecord* out, unsigned long max)
            fn.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            fn.restype = ctypes.c_ulong
        except AttributeError:
            pass

        version_str = ""
        build_id = ""
        try:
            version_str = str(int(self._lib.helper_version()))
        except Exception:
            version_str = "unknown"
        try:
            raw = self._lib.helper_build_id()
            if raw:
                build_id = raw.decode("ascii", "replace")
        except Exception:
            build_id = ""
        logger.info(
            "[keyboard-helper] loaded path=%s version=%s build=%s pid=%d",
            dll_path, version_str, build_id, os.getpid())
        if version_str.isdigit() and int(version_str) < MIN_HELPER_VERSION:
            logger.error(
                "[keyboard-helper] ABI version %s is older than required %d — "
                "RAlt hotkey disabled; rebuild native/context_helper",
                version_str, MIN_HELPER_VERSION)
            self._lib = None
            return None
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
    def dll_path(self) -> str | None:
        return self._dll_path

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

        # Ordered single-consumer dispatch state.
        self._consumer_thread: threading.Thread | None = None
        self._consumer_stop = threading.Event()
        self._toggle_queue: queue.Queue = queue.Queue()
        self._dispatch_counter = 0

        # Diagnostic ring: a bounded deque of dicts. Each entry is
        # `{seq, native_seq, recv_t, dispatch_t, latency_ms, thread_id}`.
        # Never contains user text. Inspect via recent_events().
        self._diag_lock = threading.Lock()
        self._diag_ring: collections.deque = collections.deque(maxlen=DIAG_RING_SIZE)
        self._t_install_ref = 0.0

    @property
    def is_available(self) -> bool:
        return self._lib is not None

    @property
    def lib(self):
        """Test-only accessor for raw ctypes lib handle."""
        return self._lib

    @property
    def dll_path(self) -> str | None:
        """Absolute resolved path of the loaded DLL, or None."""
        return self._loader.dll_path

    def helper_version(self) -> int:
        if not self._lib or not hasattr(self._lib, "helper_version"):
            return -1
        try:
            return int(self._lib.helper_version())
        except Exception:
            return -1

    def helper_build_id(self) -> str:
        if not self._lib or not hasattr(self._lib, "helper_build_id"):
            return ""
        try:
            raw = self._lib.helper_build_id()
            return raw.decode("ascii", "replace") if raw else ""
        except Exception:
            return ""

    def install(self, callback) -> bool:
        """Install the WH_KEYBOARD_LL hook with a zero-arg Python callback.

        v2.1 layering:
          - HookProc (C++)                   — never touches Python
          - Worker thread (C++)              — receives SetEvent
          - _dispatch (this module)          — runs on worker thread; ONLY
                                               appends sequence metadata to the
                                               diagnostic ring and pushes the
                                               toggle onto an in-process queue,
                                               then returns. NEVER spawns a
                                               thread.
          - _consumer (this module)          — single Python thread that drains
                                               the queue strictly in order and
                                               calls the business callback.
          - business callback (orchestrator.toggle_recording) — itself
            short-running; it either signals stop (sets a flag and emits a
            UI event) or schedules a new pipeline thread.

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

            # Reset diagnostic + consumer state for the new install.
            with self._diag_lock:
                self._diag_ring.clear()
                self._dispatch_counter = 0
                self._t_install_ref = time.monotonic()
            # Drain stale queue items from any previous install.
            try:
                while True:
                    self._toggle_queue.get_nowait()
            except queue.Empty:
                pass
            self._consumer_stop.clear()
            self._consumer_thread = threading.Thread(
                target=self._consumer_loop, args=(callback,),
                daemon=True, name="hotkey-consumer")
            self._consumer_thread.start()

            # ── Worker-thread → Python dispatch ─────────────────
            # The DLL worker invokes _dispatch on every toggle. We must
            # return as fast as possible so the worker can drain any
            # backlog: just snapshot metadata and put a token on the
            # queue. The consumer thread picks it up in arrival order.
            def _dispatch():
                try:
                    recv_t = time.monotonic()
                    try:
                        native_seq = int(self._lib.get_total_emitted()) \
                            if hasattr(self._lib, "get_total_emitted") else -1
                    except Exception:
                        native_seq = -1
                    self._toggle_queue.put({
                        "recv_t": recv_t,
                        "native_seq": native_seq,
                    })
                except Exception as e:
                    logger.warning("[keyboard-helper] dispatch failed: %s", e)

            _CALLBACK_HANDLE = _CALLBACK_TYPE(_dispatch)

            result = self._lib.install_hook(_CALLBACK_HANDLE)
            self._installed = (result == 1)

        logger.info("[keyboard-helper] install: %s",
                    "OK" if self._installed else "FAILED")
        if not self._installed:
            # Stop the consumer if we never actually engaged the hook.
            self._consumer_stop.set()
            self._toggle_queue.put(None)
        return self._installed

    def _consumer_loop(self, callback):
        """Single ordered consumer of toggle events.

        Runs for the lifetime of one install/uninstall cycle. Drains
        `self._toggle_queue` in arrival order and invokes `callback`. We
        do not spawn an inner thread per toggle: in production the
        business callback (`toggle_recording`) only sets flags / spawns
        the pipeline thread itself, so it returns promptly.
        """
        while not self._consumer_stop.is_set():
            try:
                item = self._toggle_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                break
            seq = 0
            disp_t = 0.0
            latency_ms = 0.0
            tid = threading.get_ident()
            try:
                with self._diag_lock:
                    self._dispatch_counter += 1
                    seq = self._dispatch_counter
                disp_t = time.monotonic()
                latency_ms = (disp_t - item.get("recv_t", disp_t)) * 1000.0
                callback()
            except Exception as e:
                logger.warning(
                    "[keyboard-helper] consumer callback raised seq=%d err=%s",
                    seq, e)
            finally:
                with self._diag_lock:
                    self._diag_ring.append({
                        "seq": seq,
                        "native_seq": item.get("native_seq", -1) if item else -1,
                        "recv_t": (item or {}).get("recv_t", 0.0),
                        "dispatch_t": disp_t,
                        "latency_ms": latency_ms,
                        "thread_id": tid,
                    })

    def uninstall(self):
        """Uninstall the WH_KEYBOARD_LL hook.

        The DLL now joins both the hook thread and the worker thread before
        uninstall_hook returns, so by the time we drop _CALLBACK_HANDLE no
        native thread can still reference it. We also stop the Python
        ordered consumer so a new install can start fresh.
        """
        global _CALLBACK_HANDLE

        with _HOOK_INSTALL_LOCK:
            if self._lib and self._lib.is_hook_installed():
                self._lib.uninstall_hook()
                self._installed = False
                _CALLBACK_HANDLE = None
                logger.info("[keyboard-helper] uninstalled")
            # Stop consumer regardless of whether hook was installed.
            self._consumer_stop.set()
            self._toggle_queue.put(None)
            t = self._consumer_thread
            self._consumer_thread = None
        if t is not None:
            t.join(timeout=2.0)

    @property
    def is_installed(self) -> bool:
        if not self._lib:
            return False
        return self._lib.is_hook_installed() == 1

    # ── Diagnostics ──────────────────────────────────────────

    def recent_events(self, limit: int = 16) -> list[dict]:
        """Return up to `limit` most-recent toggle dispatch records.

        Records contain only sequence numbers and monotonic timestamps —
        never user text. Safe to print to logs or stream to a /diag
        endpoint. The earliest entry is first.
        """
        with self._diag_lock:
            items = list(self._diag_ring)
            ref = self._t_install_ref
        items = items[-max(1, limit):]
        out = []
        for ev in items:
            out.append({
                "seq": ev["seq"],
                "native_seq": ev["native_seq"],
                "recv_ms": round((ev["recv_t"] - ref) * 1000.0, 2)
                            if ev["recv_t"] else 0.0,
                "dispatch_ms": round((ev["dispatch_t"] - ref) * 1000.0, 2)
                                if ev["dispatch_t"] else 0.0,
                "latency_ms": round(ev["latency_ms"], 2),
                "thread_id": ev["thread_id"],
            })
        return out

    def diagnostics(self) -> dict:
        """Snapshot of native + Python counters and the DLL identity.

        Useful for verifying which DLL build is actually loaded at runtime
        and confirming the consumer is keeping up with the producer.
        """
        emitted = self.get_total_emitted()
        consumed = self.get_total_consumed()
        pending = self.get_pending_count()
        with self._diag_lock:
            dispatched = self._dispatch_counter
        return {
            "dll_path": self.dll_path or "",
            "helper_version": self.helper_version(),
            "helper_build_id": self.helper_build_id(),
            "pid": os.getpid(),
            "is_installed": self.is_installed,
            "total_emitted": emitted,
            "total_consumed": consumed,
            "pending": pending,
            "dispatched": dispatched,
            "queue_depth": self._toggle_queue.qsize(),
            "native_event_count": self.native_event_count(),
        }

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

    def test_handle_event(self, vk: int, wparam: int, flags: int) -> int:
        """Test-only: drive HookProc parser with synthetic event fields.

        Returns 1 if the parser would swallow the key, 0 to pass through,
        -1 if not installed. Side-effect free (no SendInput injection).
        """
        if not self._lib:
            return -1
        try:
            fn = getattr(self._lib, "__test_handle_event")
        except AttributeError:
            return -1
        return int(fn(ctypes.c_uint(vk), ctypes.c_uint(wparam), ctypes.c_uint(flags)))

    def test_reset_state(self):
        """Test-only: clear HookProc internal `g_matched` state."""
        if not self._lib:
            return
        try:
            fn = getattr(self._lib, "__test_reset_state")
        except AttributeError:
            return
        fn()

    # ── Native diagnostics (v3+) ──────────────────────────

    def native_event_count(self) -> int:
        """Number of keyboard events recorded by the native ring buffer since install."""
        if not self._lib or not hasattr(self._lib, "native_event_count"):
            return -1
        try:
            return int(self._lib.native_event_count())
        except Exception:
            return -1

    def native_events(self, limit: int = 128) -> list[dict]:
        """Read most-recent native keyboard event records from the DLL ring buffer.

        Returns a list of dicts with fields:
          seq, vkCode, wParam, flags, matched_before, matched_after,
          emitted, tick_ms

        Only integer/enum/timestamp metadata — no text or personal data.
        Returns up to `limit` entries, oldest first.
        """
        if not self._lib or not hasattr(self._lib, "native_events"):
            return []
        max_entries = min(limit, 128)
        # Each NativeEventRecord is 8 × uint32 = 32 bytes
        buf_size = max_entries * 32
        buf = ctypes.create_string_buffer(buf_size)
        try:
            count = int(self._lib.native_events(buf, ctypes.c_ulong(max_entries)))
        except Exception:
            return []
        entries = []
        for i in range(count):
            offset = i * 32
            fields = [
                int.from_bytes(buf[offset + j*4: offset + j*4 + 4], 'little')
                for j in range(8)
            ]
            entries.append({
                "seq": fields[0],
                "vkCode": fields[1],
                "wParam": fields[2],
                "flags": fields[3],
                "matched_before": fields[4],
                "matched_after": fields[5],
                "emitted": fields[6],
                "tick_ms": fields[7],
            })
        return entries

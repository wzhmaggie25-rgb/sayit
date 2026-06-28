"""RAlt Stop Watcher — fallback RAlt edge detector for long-dictation reliability.

Purpose
-------
The primary RAlt detection path goes through WH_KEYBOARD_LL (HookProc in
sayit_keyboard_helper.dll). Under sustained GIL contention or other conditions,
Windows may silently unload the hook (LowLevelHooksTimeout), causing the
*second* RAlt press to be lost entirely — no HookProc call, no EmitToggle, no
Python callback, no stop.

This module provides a polling-based fallback that detects an RAlt down-edge
using GetAsyncKeyState and requests a stop when the main hook did NOT process
the event. It is armed only during the CAPTURING phase of a pipeline and
de-arms immediately after a single detection.

Design
------
- arm() snapshots the current total_emitted count from the DLL.
- A daemon thread polls GetAsyncKeyState(VK_RMENU) every 10 ms.
- Phase 1: Wait for initial start-key RAlt to release (avoids false trigger).
- Phase 2: Detect the NEXT RAlt down-edge (transition from not-down to down).
  - On down-edge, IMMEDIATELY check if emitted count increased:
    - If count increased → hook processed it → nothing to do.
    - If count unchanged → hook miss → invoke fallback callback.
  - No need to wait for up-edge: the down-edge is the user's intent to stop.
- disarm() signals the thread to exit and joins it (1s timeout).
- At most ONE detection per arm cycle (prevents runaway starts).

Thread safety
-------------
arm/disarm are designed to be called from different threads (orchestrator
holds _pipeline_lock). The polling thread is daemon and self-contained; it
uses only atomic/event flags to communicate with the outside world.
"""

from __future__ import annotations
import ctypes
import logging
import threading
import time

VK_RMENU = 0xA5

logger = logging.getLogger(__name__)


class RAltStopWatcher:
    """Fallback RAlt edge detector using GetAsyncKeyState polling.

    Usage:
        watcher = RAltStopWatcher(fallback_callback, helper)
        watcher.arm()       # start monitoring (after pipeline CAPTURING)
        # ... later ...
        watcher.disarm()    # stop monitoring

    `fallback_callback` is a zero-arg callable invoked when a hook-miss
    stop is detected. It should be orchestrator._fallback_stop().
    """

    def __init__(self, fallback_callback, helper=None):
        self._fallback_callback = fallback_callback
        self._helper = helper  # KeyboardHelperDll (for get_total_emitted)

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._armed = False
        self._initial_emitted = -1
        self._hook_misses = 0
        self._fallback_stops = 0

        # Test injection flags — set by tests to simulate key state without
        # requiring physical keyboard interaction.
        self._test_ralt_pressed = False  # test inject: RAlt is physically down
        self._test_emitted_override = None  # test inject: override emitted count

    # ── Public API ──────────────────────────────────────────────

    def arm(self, total_emitted: int | None = None):
        """Start monitoring for the next RAlt down-edge.

        Call after the pipeline enters CAPTURING. Snapshots the current
        emitted count for later comparison.

        Args:
            total_emitted: Optional pre-snapshot of helper.get_total_emitted().
                           If omitted, read from helper at arm time.
        """
        if self._armed:
            return
        self._armed = True

        # Snapshot emitted count at arm time
        if total_emitted is not None:
            self._initial_emitted = total_emitted
        elif self._helper is not None:
            try:
                self._initial_emitted = self._helper.get_total_emitted()
            except Exception:
                self._initial_emitted = -1
        else:
            self._initial_emitted = -1

        logger.debug("[RAltStopWatcher] armed (initial_emitted=%s)", self._initial_emitted)

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True,
            name="ralt-stop-watcher")
        self._thread.start()

    def disarm(self):
        """Stop monitoring. Thread-safe; may be called multiple times."""
        if not self._armed and self._thread is None:
            return
        self._armed = False
        self._stop_event.set()
        # Skip join when called from the polling thread itself
        # (e.g. via down-edge detection → disarm after fire).
        # External callers (orchestrator) will join the thread normally.
        if (self._thread is not None and self._thread.is_alive()
                and self._thread is not threading.current_thread()):
            self._thread.join(timeout=1.0)
        self._thread = None
        self._test_ralt_pressed = False
        self._test_emitted_override = None
        logger.debug("[RAltStopWatcher] disarmed")

    @property
    def is_armed(self) -> bool:
        return self._armed

    @property
    def hook_misses(self) -> int:
        return self._hook_misses

    @property
    def fallback_stops(self) -> int:
        return self._fallback_stops

    def diagnostics(self) -> dict:
        """Snapshot of watcher counters (no personal data)."""
        return {
            "armed": self._armed,
            "hook_misses": self._hook_misses,
            "fallback_stops": self._fallback_stops,
            "initial_emitted": self._initial_emitted,
        }

    # ── Internal ────────────────────────────────────────────────

    def _is_ralt_down(self) -> bool:
        """Check if RAlt is currently pressed."""
        if self._test_ralt_pressed:
            return True
        try:
            return bool(
                ctypes.windll.user32.GetAsyncKeyState(VK_RMENU) & 0x8000)
        except Exception:
            return False

    def _get_current_emitted(self) -> int:
        """Read current total_emitted from the helper DLL."""
        if self._test_emitted_override is not None:
            return self._test_emitted_override
        if self._helper is not None:
            try:
                return self._helper.get_total_emitted()
            except Exception:
                pass
        return -1

    def _poll_loop(self):
        """Daemon thread: detect RAlt down-edge, check hook processing.

        Phase 1: Wait for the initial RAlt to be fully released (the same
        press that started the recording). Without this, the watcher would
        immediately see a "down" from the start key itself and fire a false
        stop.

        Phase 2: Detect the next RAlt down-edge (transition up→down).
          - On detection, IMMEDIATELY check emitted count:
            - If increased → hook handled it → nothing to do.
            - If unchanged → hook miss → invoke fallback callback.
          - Fires on the down-edge alone — no need to wait for up-edge.
        """
        # ── Phase 1: Wait for initial RAlt release ──────────
        # The user pressed RAlt to start; that key may still be down for a
        # short time. Wait up to 2s for it to release.
        for _ in range(200):
            if self._stop_event.is_set():
                return
            if not self._is_ralt_down():
                break
            time.sleep(0.010)
        else:
            # Timed out — RAlt never released? Disarm defensively.
            logger.warning("[RAltStopWatcher] initial RAlt never released — disarming")
            self._armed = False
            return

        # Short stabilization pause after release
        time.sleep(0.050)

        # ── Phase 2: Detect next RAlt down-edge ──────────────
        # On down-edge: check emitted. If hook missed it, fire fallback.
        was_down = False
        while not self._stop_event.is_set() and self._armed:
            down = self._is_ralt_down()
            if down and not was_down:
                # Detected down-edge (transition from not-down to down)
                self._on_down_edge()
                return
            was_down = down
            time.sleep(0.010)

    def _on_down_edge(self):
        """Called when an RAlt down-edge is detected.

        If the hook already processed this event (total_emitted increased
        since arm), we do nothing. Otherwise, it's a hook miss — fire
        fallback immediately, without waiting for the up-edge.

        Note: there is a narrow race where both the hook and watcher fire
        nearly simultaneously. The orchestrator's _stop_request_latched
        flag ensures only one stop request is actually honored.
        """
        post = self._get_current_emitted()
        if post > self._initial_emitted:
            # Hook already processed the toggle — nothing to do.
            logger.debug(
                "[RAltStopWatcher] hook handled it (emitted %s -> %s)",
                self._initial_emitted, post)
        else:
            # Hook missed the event! Fire fallback on down-edge.
            self._hook_misses += 1
            logger.info(
                "[RAltStopWatcher] HOOK MISS detected on down-edge! "
                "emitted=%s (unchanged from %s) — firing fallback stop",
                post, self._initial_emitted)
            # Fire fallback stop once
            self._fallback_stops += 1
            try:
                self._fallback_callback()
            except Exception as e:
                logger.warning("[RAltStopWatcher] fallback callback failed: %s", e)

        # Either way, disarm after one detection. We only guard against one
        # missed stop per arm cycle.
        self.disarm()
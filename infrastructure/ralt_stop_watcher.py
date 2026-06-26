"""RAlt Stop Watcher — fallback RAlt edge detector for long-dictation reliability.

Purpose
-------
The primary RAlt detection path goes through WH_KEYBOARD_LL (HookProc in
sayit_keyboard_helper.dll). Under sustained GIL contention or other conditions,
Windows may silently unload the hook (LowLevelHooksTimeout), causing the
*second* RAlt press to be lost entirely — no HookProc call, no EmitToggle, no
Python callback, no stop.

This module provides a polling-based fallback that detects a complete RAlt
down→up cycle using GetAsyncKeyState and requests a stop when the main hook
did NOT process the event. It is armed only during the CAPTURING phase of a
pipeline and de-arms immediately after a single detection.

Design
------
- arm() snapshots the current total_emitted count from the DLL.
- A daemon thread polls GetAsyncKeyState(VK_RMENU) every 10 ms.
- On detecting a complete down→up transition, it re-checks total_emitted:
  - If the count increased → the hook processed it normally → do nothing.
  - If the count stayed the same → hook miss → invoke fallback callback.
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
        """Start monitoring for the next RAlt down→up.

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
        # (e.g. via _on_complete_cycle → disarm after cycle detection).
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
        """Daemon thread: detect RAlt down→up, then check hook processing.

        Phase 1: Wait for the initial RAlt to be fully released (the same
        press that started the recording). Without this, the watcher would
        immediately see a "down" from the start key itself and fire a false
        stop.

        Phase 2: Detect the next complete down→up transition.
        Phase 3: Compare emitted count. If hook didn't process it → fallback.
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

        # ── Phase 2: Detect next RAlt down→up ──────────────
        in_down = False
        while not self._stop_event.is_set() and self._armed:
            down = self._is_ralt_down()
            if down and not in_down:
                in_down = True  # detected falling edge: RAlt went down
            elif not down and in_down:
                # Detected rising edge: RAlt went up → complete cycle
                self._on_complete_cycle()
                return
            time.sleep(0.010)

    def _on_complete_cycle(self):
        """Called when a complete RAlt down→up cycle was detected.

        If the hook already processed this event (total_emitted increased),
        we do nothing. Otherwise, it's a hook miss → fire fallback.
        """
        post = self._get_current_emitted()
        if post > self._initial_emitted:
            # Hook already processed the toggle — nothing to do.
            logger.debug(
                "[RAltStopWatcher] hook handled it (emitted %s -> %s)",
                self._initial_emitted, post)
        else:
            # Hook missed the event!
            self._hook_misses += 1
            logger.info(
                "[RAltStopWatcher] HOOK MISS detected! "
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
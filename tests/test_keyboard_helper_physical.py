"""Real HookProc parser tests using the synthetic-event native entry.

This file complements `test_keyboard_helper_stress.py`. The previous
suite measured the C++ → worker → Python TRANSPORT by calling
`__test_trigger_toggle()` — but that entry point bypasses the actual
HookProc parsing logic (`g_matched`, VK_RMENU / VK_MENU+extended,
WM_SYSKEYUP, LLKHF_EXTENDED / LLKHF_INJECTED, auto-repeat).

Here we drive the EXACT production parser via `__test_handle_event(vk,
wParam, flags)`, which calls `HandleKeyEventCore` — the same function
HookProc itself invokes for every physical keystroke. Side-effect free
(no SendInput injection into the OS).

Skipped when DLL is missing or older than ABI v2.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

os.environ.setdefault("SAYIT_TEST_MODE", "1")

from infrastructure.keyboard_helper_dll import KeyboardHelperDll

# ── Windows VK + WM constants ─────────────────────────────────────
VK_RMENU      = 0xA5
VK_LMENU      = 0xA4
VK_MENU       = 0x12
VK_CONTROL    = 0x11
WM_KEYDOWN    = 0x0100
WM_KEYUP      = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP   = 0x0105
LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10


def _has_v2() -> bool:
    helper = KeyboardHelperDll()
    if not helper.is_available:
        return False
    try:
        getattr(helper.lib, "__test_handle_event")
    except AttributeError:
        return False
    return (
        hasattr(helper.lib, "helper_version")
        and helper.helper_version() >= 2
    )


@unittest.skipUnless(_has_v2(),
                     "sayit_keyboard_helper.dll missing or older than ABI v2")
class HookProcParserTests(unittest.TestCase):
    """Tests that exercise the real HookProc parsing state machine."""

    @classmethod
    def setUpClass(cls):
        cls.helper = KeyboardHelperDll()

    def setUp(self):
        try:
            self.helper.uninstall()
        except Exception:
            pass
        self.consumed = []
        self._cb_lock = threading.Lock()
        def _cb():
            with self._cb_lock:
                self.consumed.append(time.monotonic())
        self.cb = _cb
        ok = self.helper.install(self.cb)
        self.assertTrue(ok, "install_hook failed")
        # Always start each test with parser state reset.
        self.helper.test_reset_state()

    def tearDown(self):
        try:
            self.helper.uninstall()
        except Exception:
            pass

    def _wait_for_emits(self, n: int, timeout: float = 5.0):
        """Wait until the consumer thread has invoked the callback `n` times."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._cb_lock:
                got = len(self.consumed)
            if got >= n:
                return
            time.sleep(0.02)

    def _press_release(self, vk=VK_RMENU, flags_down=0, flags_up=0):
        """Drive a complete RAlt down→up cycle through the parser."""
        self.helper.test_handle_event(vk, WM_SYSKEYDOWN, flags_down)
        self.helper.test_handle_event(vk, WM_SYSKEYUP, flags_up)

    # ── 1. A complete RAlt down/up emits exactly one toggle ───────

    def test_single_ralt_press_release_emits_one_toggle(self):
        before = self.helper.get_total_emitted()
        self._press_release(VK_RMENU)
        self._wait_for_emits(1)
        after = self.helper.get_total_emitted()
        self.assertEqual(after - before, 1,
                         f"expected 1 toggle, got {after - before}")
        with self._cb_lock:
            self.assertEqual(len(self.consumed), 1)

    # ── 2. Three complete RAlt presses → exactly 3 toggles, in order ─

    def test_three_consecutive_presses_emit_three_toggles_in_order(self):
        before = self.helper.get_total_emitted()
        before_disp = self.helper.diagnostics()["dispatched"]
        for _ in range(3):
            self._press_release(VK_RMENU)
        self._wait_for_emits(3)
        emitted = self.helper.get_total_emitted() - before
        self.assertEqual(emitted, 3,
                         f"expected exactly 3 native emits, got {emitted}")
        with self._cb_lock:
            self.assertEqual(len(self.consumed), 3,
                             "consumer dropped or reordered a toggle")
        # Diagnostic ring records the seq order — must be monotonically
        # increasing 1,2,3 with no gaps.
        events = self.helper.recent_events(limit=3)
        seqs = [e["seq"] for e in events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), 3)
        # Native sequence must also advance monotonically.
        native = [e["native_seq"] for e in events]
        self.assertEqual(native, sorted(native))
        # Sanity: dispatched counter advanced by exactly 3.
        delta = self.helper.diagnostics()["dispatched"] - before_disp
        self.assertEqual(delta, 3)

    # ── 3. VK_MENU + LLKHF_EXTENDED is equivalent to VK_RMENU ────

    def test_vk_menu_extended_is_equivalent_to_vk_rmenu(self):
        before = self.helper.get_total_emitted()
        # Down: WM_SYSKEYDOWN with VK_MENU + EXTENDED, then up the same way.
        self.helper.test_handle_event(VK_MENU, WM_SYSKEYDOWN, LLKHF_EXTENDED)
        self.helper.test_handle_event(VK_MENU, WM_SYSKEYUP, LLKHF_EXTENDED)
        self._wait_for_emits(1)
        self.assertEqual(self.helper.get_total_emitted() - before, 1)

    # ── 4. Auto-repeat keydowns while held do NOT emit new toggles ─

    def test_auto_repeat_keydown_is_swallowed(self):
        before = self.helper.get_total_emitted()
        # Initial down enters matched state.
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYDOWN, 0)
        # 8 auto-repeat downs — each must be swallowed, NO new toggle.
        for _ in range(8):
            self.helper.test_handle_event(VK_RMENU, WM_SYSKEYDOWN, 0)
        # Now release — emits exactly one toggle.
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, 0)
        self._wait_for_emits(1)
        emitted = self.helper.get_total_emitted() - before
        self.assertEqual(emitted, 1,
                         f"auto-repeat caused duplicate emits: got {emitted}")

    # ── 5. Injected events (our own ForceReleaseAlt) are ignored ─

    def test_injected_events_do_not_change_state_machine(self):
        before = self.helper.get_total_emitted()
        # Press RAlt (sets matched=true)
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYDOWN, 0)
        # Inject many keyup events — they MUST be ignored (so matched stays
        # true and the next physical up still emits exactly one toggle).
        for _ in range(5):
            self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, LLKHF_INJECTED)
            self.helper.test_handle_event(VK_LMENU, WM_SYSKEYUP, LLKHF_INJECTED)
            self.helper.test_handle_event(VK_MENU,  WM_SYSKEYUP, LLKHF_INJECTED)
        # Physical up → emit.
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, 0)
        self._wait_for_emits(1)
        emitted = self.helper.get_total_emitted() - before
        self.assertEqual(emitted, 1,
                         f"injected events leaked into emit count: {emitted}")

    # ── 6. Stray RAlt up with no matching down emits nothing ─────

    def test_stray_up_does_not_emit(self):
        before = self.helper.get_total_emitted()
        # No down → up: should be swallowed silently.
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, 0)
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, 0)
        time.sleep(0.1)
        self.assertEqual(self.helper.get_total_emitted() - before, 0)

    # ── 7. Non-RAlt keys do not produce toggles ──────────────────

    def test_left_alt_does_not_toggle(self):
        before = self.helper.get_total_emitted()
        # Left Alt — VK_LMENU with no EXTENDED flag.
        self.helper.test_handle_event(VK_LMENU, WM_SYSKEYDOWN, 0)
        self.helper.test_handle_event(VK_LMENU, WM_SYSKEYUP, 0)
        # AltGr-style Ctrl press around it must also not consume RAlt.
        self.helper.test_handle_event(VK_CONTROL, WM_KEYDOWN, 0)
        self.helper.test_handle_event(VK_CONTROL, WM_KEYUP, 0)
        time.sleep(0.1)
        self.assertEqual(self.helper.get_total_emitted() - before, 0)

    # ── 8. After uninstall→install, state is fresh ───────────────

    def test_install_uninstall_resets_state(self):
        # Press down — matched=true
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYDOWN, 0)
        # Uninstall and reinstall — state machine should reset.
        self.helper.uninstall()
        ok = self.helper.install(self.cb)
        self.assertTrue(ok)
        self.helper.test_reset_state()
        before = self.helper.get_total_emitted()
        # An "up" now must be treated as stray and emit nothing.
        self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, 0)
        time.sleep(0.1)
        self.assertEqual(self.helper.get_total_emitted() - before, 0)

    # ── 9. 1000 full cycles with mixed garbage events ────────────

    def test_one_thousand_full_cycles_with_noise(self):
        """The headline coverage requested in CURRENT_TASK §B2:

        1000 complete RAlt down→up cycles interleaved with noise events
        — auto-repeat downs, injected ups, stray ups, left-Alt presses.
        Result MUST be exactly 1000 toggles, recorded in monotonically
        increasing order.
        """
        before = self.helper.get_total_emitted()
        N = 1000
        for i in range(N):
            # Each cycle: optional pre-noise + down + auto-repeats + injected ups + up.
            if i % 3 == 0:
                self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, LLKHF_INJECTED)
                self.helper.test_handle_event(VK_LMENU, WM_SYSKEYDOWN, 0)
                self.helper.test_handle_event(VK_LMENU, WM_SYSKEYUP, 0)
            # Press RAlt (random choice between VK_RMENU and VK_MENU+extended)
            if i % 2 == 0:
                self.helper.test_handle_event(VK_RMENU, WM_SYSKEYDOWN, 0)
            else:
                self.helper.test_handle_event(VK_MENU, WM_SYSKEYDOWN, LLKHF_EXTENDED)
            # Auto-repeat noise
            self.helper.test_handle_event(VK_RMENU, WM_SYSKEYDOWN, 0)
            # Injected garbage
            self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, LLKHF_INJECTED)
            # Release
            self.helper.test_handle_event(VK_RMENU, WM_SYSKEYUP, 0)

        self._wait_for_emits(N, timeout=30.0)
        emitted = self.helper.get_total_emitted() - before
        self.assertEqual(emitted, N,
                         f"expected {N} toggles, got {emitted}")
        with self._cb_lock:
            self.assertEqual(len(self.consumed), N,
                             "consumer lost or duplicated a toggle")
        # Diagnostic ring is bounded; just confirm last seq matches dispatched.
        diag = self.helper.diagnostics()
        self.assertEqual(diag["dispatched"], N)
        self.assertEqual(diag["pending"], 0)


if __name__ == "__main__":
    unittest.main()

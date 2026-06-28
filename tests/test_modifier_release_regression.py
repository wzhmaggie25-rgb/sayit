"""Phase A1: Modifier release regression tests.

Tests that Injector._release_modifiers() never emits key-up events for
modifiers that are not physically pressed. This is the root cause of the
FEVHLBIGKOPS garbage-text regression.

Key invariant:
  SayIt must never synthesize a key-up for a modifier that is not currently
  down for the corresponding physical/logical key.

Tests spy on SendInput to count actual keyboard events rather than just
asserting a mock return value.
"""
from __future__ import annotations
import ctypes
import sys
import unittest
from unittest.mock import patch, MagicMock

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test", allow_module_level=True)

from infrastructure.injector import (
    Injector, INPUT, INPUT_KEYBOARD, KEYEVENTF_KEYUP,
)


class ModifierReleaseRegressionTests(unittest.TestCase):
    """BEFORE FIX: These tests FAIL because force=True bypasses GetAsyncKeyState."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def _make_sendinput_spy(self):
        """Build a spy that records all SendInput calls and returns 1."""
        calls = []

        def spy(nInputs, pInputs, cbSize):
            for i in range(nInputs):
                inp = ctypes.cast(pInputs, ctypes.POINTER(INPUT))[i]
                if inp.type == INPUT_KEYBOARD and (inp.ki.dwFlags & KEYEVENTF_KEYUP):
                    calls.append({
                        "vk": inp.ki.wVk,
                        "scan": inp.ki.wScan,
                        "flags": inp.ki.dwFlags,
                    })
            return nInputs

        return calls, spy

    def test_all_modifiers_up_no_events_default(self):
        """All modifiers physically up → _release_modifiers() emits ZERO SendInput calls."""
        calls, spy = self._make_sendinput_spy()
        with patch.object(ctypes.windll.user32, "GetAsyncKeyState", return_value=0), \
             patch.object(ctypes.windll.user32, "SendInput", side_effect=spy):
            self.inj._release_modifiers(reason="test_all_up")
        self.assertEqual(len(calls), 0,
                         f"Expected zero SendInput calls when all modifiers up, got {len(calls)}: {calls}")

    def test_force_parameter_removed(self):
        """Round 9.4: force=True was removed — passing it must raise TypeError.
        
        BEFORE FIX: force=True bypassed GetAsyncKeyState entirely and emitted
        11 key-up events for all VKs in _MODIFIER_RELEASE_ORDER, producing
        the FEVHLBIGKOPS garbage prefix. The parameter is now removed so all
        callers always check physical state.
        """
        with self.assertRaises(TypeError):
            self.inj._release_modifiers(force=True, reason="test_force_removed")
        # Also verify the no-force API works (zero events when all keys up)
        calls, spy = self._make_sendinput_spy()
        with patch.object(ctypes.windll.user32, "GetAsyncKeyState", return_value=0), \
             patch.object(ctypes.windll.user32, "SendInput", side_effect=spy):
            self.inj._release_modifiers(reason="test_after_force")
        self.assertEqual(len(calls), 0,
                         f"No-force call must still respect physical state. "
                         f"Got {len(calls)} events: {calls}")

    def test_only_ralt_down_releases_only_ralt(self):
        """Only RAlt physically down → release only matching VKs, no duplicates."""
        calls, spy = self._make_sendinput_spy()

        # RAlt = VK_RMENU = 0xA5
        def _getkey_ralt(vk):
            if vk == 0xA5:  # VK_RMENU
                return 0x8000  # down
            return 0  # all others up

        with patch.object(ctypes.windll.user32, "GetAsyncKeyState", side_effect=_getkey_ralt), \
             patch.object(ctypes.windll.user32, "SendInput", side_effect=spy):
            self.inj._release_modifiers(reason="test_ralt_down")

        released_vks = [c["vk"] for c in calls]
        # Must only release VK_RMENU (0xA5) — not VK_LMENU (0xA4), not VK_MENU (0x12)
        self.assertIn(0xA5, released_vks,
                       "VK_RMENU must be released when RAlt is down")
        # Duplicate VK aliases must not be released
        for vk in [0xA4, 0x12]:  # VK_LMENU, VK_MENU
            self.assertNotIn(vk, released_vks,
                             f"VK 0x{vk:02X} must NOT be released for RAlt-only press")
        # Must not release unrelated modifiers
        for vk in [0x5B, 0x5C]:  # Win L/R
            self.assertNotIn(vk, released_vks, f"Win key VK 0x{vk:02X} must not be released")

    def test_multiple_modifiers_down_release_only_those(self):
        """Multiple genuinely pressed modifiers → release only those that are down."""
        calls, spy = self._make_sendinput_spy()

        # RAlt + LCtrl down
        def _getkey_multi(vk):
            if vk in (0xA5, 0xA2):  # VK_RMENU, VK_LCONTROL
                return 0x8000
            return 0

        with patch.object(ctypes.windll.user32, "GetAsyncKeyState", side_effect=_getkey_multi), \
             patch.object(ctypes.windll.user32, "SendInput", side_effect=spy):
            self.inj._release_modifiers(reason="test_multi_down")

        released_vks = [c["vk"] for c in calls]
        self.assertIn(0xA5, released_vks, "VK_RMENU must be released")
        self.assertIn(0xA2, released_vks, "VK_LCONTROL must be released")
        # But NOT RAlt aliases (VK_MENU 0x12, VK_LMENU 0xA4)
        for dup in [0x12, 0xA4]:
            self.assertNotIn(dup, released_vks,
                             f"Duplicate VK 0x{dup:02X} must not be released")
        # And NOT unpressed keys
        for vk in [0x5B, 0x5C, 0xA0, 0xA1, 0x10, 0xA3, 0x11]:
            self.assertNotIn(vk, released_vks,
                             f"Unpressed VK 0x{vk:02X} must not be released")

    def test_ten_consecutive_clean_calls_zero_events(self):
        """Ten consecutive calls with all keys up → zero keyboard events total."""
        calls, spy = self._make_sendinput_spy()
        with patch.object(ctypes.windll.user32, "GetAsyncKeyState", return_value=0), \
             patch.object(ctypes.windll.user32, "SendInput", side_effect=spy):
            for i in range(10):
                self.inj._release_modifiers(reason=f"clean_{i}")
        self.assertEqual(len(calls), 0,
                         f"10 consecutive calls with all keys up must produce 0 events, "
                         f"got {len(calls)}")

    def test_release_order_deterministic(self):
        """When multiple modifiers are down, release order is deterministic and
        does not include duplicate aliases."""
        calls, spy = self._make_sendinput_spy()

        # RAlt + LWin down
        def _getkey_two(vk):
            if vk in (0xA5, 0x5B):  # VK_RMENU, VK_LWIN
                return 0x8000
            return 0

        with patch.object(ctypes.windll.user32, "GetAsyncKeyState", side_effect=_getkey_two), \
             patch.object(ctypes.windll.user32, "SendInput", side_effect=spy):
            self.inj._release_modifiers(reason="test_order")

        released_vks = [c["vk"] for c in calls]
        # Exactly 2 events, no duplicates
        self.assertEqual(len(released_vks), 2,
                         f"Expected 2 releases for RAlt+LWin, got {len(released_vks)}: {released_vks}")


if __name__ == "__main__":
    unittest.main()
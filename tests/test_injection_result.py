"""InjectionResult dataclass and inject() tests.

Verifies the InjectionResult contract:

  inject() returns an InjectionResult with structured outcome data including
  state, ok, verified, method, reason, clipboard_preserved, clipboard_restored,
  target_verified, and target_restored fields.

  paste() always returns True (once shortcut sent) and always restores backup.
  Verification is done by caller via target readback, not clipboard heuristic.
"""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

from infrastructure.injector import InjectionResult, Injector


class InjectionResultTests(unittest.TestCase):
    """Tests for InjectionResult dataclass."""

    def test_default_construction(self):
        """Default InjectionResult is falsy with empty fields."""
        r = InjectionResult()
        self.assertFalse(r, "__bool__ must be False by default")
        self.assertFalse(r.ok)
        self.assertEqual(r.state, "recognition_failed")
        self.assertFalse(r.verified)
        self.assertEqual(r.method, "")
        self.assertEqual(r.reason, "")
        self.assertFalse(r.clipboard_preserved)
        self.assertFalse(r.clipboard_restored)
        self.assertFalse(r.target_verified)
        self.assertFalse(r.target_restored)

    def test_ok_construction(self):
        """InjectionResult(ok=True, state='verified_success') is truthy."""
        r = InjectionResult(ok=True, state="verified_success", verified=True,
                            method="clipboard", clipboard_preserved=True)
        self.assertTrue(r, "__bool__ must be True when ok=True")
        self.assertTrue(r.ok)
        self.assertEqual(r.state, "verified_success")
        self.assertTrue(r.verified)
        self.assertEqual(r.method, "clipboard")

    def test_no_editable_target_truthy(self):
        """no_editable_target has ok=False but clipboard_preserved=True."""
        r = InjectionResult(ok=False, state="no_editable_target",
                            clipboard_preserved=True,
                            reason="no_editable_target")
        self.assertFalse(r)
        self.assertEqual(r.state, "no_editable_target")
        self.assertTrue(r.clipboard_preserved)

    def test_bool_backward_compat(self):
        """__bool__ works for backward compat: if r: treats as bool."""
        ok_r = InjectionResult(ok=True, state="verified_success", method="uia")
        fail_r = InjectionResult(ok=False, state="injection_failed",
                                  reason="fail")
        self.assertTrue(bool(ok_r))
        self.assertFalse(bool(fail_r))

    def test_all_fields_stored(self):
        """All fields are correctly stored and retrieved."""
        r = InjectionResult(
            ok=True, state="verified_success", verified=True,
            method="win32_child", reason="",
            clipboard_preserved=True, clipboard_restored=True,
            target_verified=True, target_restored=True)
        self.assertEqual(r.ok, True)
        self.assertEqual(r.state, "verified_success")
        self.assertEqual(r.verified, True)
        self.assertEqual(r.method, "win32_child")
        self.assertEqual(r.reason, "")
        self.assertTrue(r.clipboard_preserved)
        self.assertTrue(r.clipboard_restored)
        self.assertTrue(r.target_verified)
        self.assertTrue(r.target_restored)

    def test_failure_state(self):
        """Failure result has injection_failed state."""
        r = InjectionResult(ok=False, state="injection_failed",
                             reason="all_three_layers_failed",
                             clipboard_preserved=True)
        self.assertFalse(r)
        self.assertEqual(r.state, "injection_failed")
        self.assertTrue(r.clipboard_preserved)

    def test_state_values_exist(self):
        """Known state values are recognized."""
        valid_states = {"verified_success", "no_editable_target",
                        "injection_failed", "recognition_failed"}
        for s in valid_states:
            r = InjectionResult(ok=(s == "verified_success"), state=s)
            self.assertIn(r.state, valid_states)


class InjectorPasteTests(unittest.TestCase):
    """Tests for paste() — always restores backup, returns True once sent."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def _patch_clipboard(self, initial=None):
        """Patch clipboard read/write with a simple dict store."""
        store = {"text": initial}

        def fake_get():
            return store.get("text")

        def fake_set(text):
            store["text"] = text
            return True

        return (
            patch("infrastructure.injector._clipboard_get_text",
                  side_effect=fake_get),
            patch("infrastructure.injector._clipboard_set_text",
                  side_effect=fake_set),
            store,
        )

    def test_paste_always_restores_backup(self):
        """paste() always restores original clipboard after sending shortcut."""
        get_patch, set_patch, store = self._patch_clipboard("original-text")
        with get_patch, set_patch, \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("time.sleep"):
            ok = self.inj.paste("new text")
        self.assertTrue(ok, "paste() should return True once shortcut sent")
        # After paste, clipboard should be restored to original
        self.assertEqual(store["text"], "original-text",
                         "clipboard must be restored after paste")

    def test_paste_empty_backup(self):
        """paste() works when there's no clipboard backup (None)."""
        get_patch, set_patch, store = self._patch_clipboard(None)
        with get_patch, set_patch, \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("time.sleep"):
            ok = self.inj.paste("new text")
        self.assertTrue(ok)
        # When backup is None, there's nothing to restore — clipboard state
        # is whatever remains after paste. The caller is responsible for
        # clipboard management when target is verified via readback.

    def test_paste_set_text_failure_returns_false(self):
        """If _clipboard_set_text fails, paste returns False immediately."""
        get_patch, set_patch, store = self._patch_clipboard(None)
        with get_patch, \
             patch("infrastructure.injector._clipboard_set_text",
                   return_value=False), \
             patch.object(self.inj, "_lock", MagicMock()):
            ok = self.inj.paste("hello")
        self.assertFalse(ok)

    def test_paste_backup_restored_on_keybd_failure(self):
        """If keybd_event fails, backup is still restored."""
        get_patch, set_patch, store = self._patch_clipboard("backup")
        with get_patch, set_patch, \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("ctypes.windll.user32.keybd_event",
                   side_effect=Exception("keybd failed")), \
             patch("time.sleep"):
            ok = self.inj.paste("hello")
        self.assertFalse(ok)
        self.assertEqual(store["text"], "backup",
                         "backup must be restored on keybd failure")


class InjectorResultTests(unittest.TestCase):
    """Tests for inject() return values and state."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_inject_returns_injection_result(self):
        """inject() returns InjectionResult, not bool."""
        with patch.object(self.inj, "_lock", MagicMock()):
            result = self.inj.inject("test text")
        self.assertIsInstance(result, InjectionResult)
        self.assertIn(result.state,
                      {"verified_success", "no_editable_target",
                       "injection_failed", "recognition_failed"})

    def test_inject_ok_truthy_with_state(self):
        """When injection succeeds via clipboard, result has verified_success state."""
        with patch.object(self.inj, "_direct_input", return_value=True), \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("time.sleep"):
            result = self.inj.inject("hello")
        self.assertTrue(result)
        self.assertEqual(result.state, "verified_success")
        # Without foreground info, strategy defaults to uia → clipboard → sendinput.
        # paste() will succeed first since it's mocked.
        self.assertIn(result.method, {"clipboard", "sendinput", "uia"})

    def test_inject_fail_has_clipboard_preserved(self):
        """When injection fails, clipboard_preserved=True (no auto-copy)."""
        with patch.object(self.inj, "_lock", MagicMock()):
            with patch.object(self.inj, "_direct_input", return_value=False), \
                 patch.object(self.inj, "_foreground_info",
                              return_value=(0, "", 0, "")), \
                 patch.object(self.inj, "_get_context_for_strategy",
                              return_value={}), \
                 patch.object(self.inj, "_strategy_for_context",
                              return_value="send_input"), \
                 patch.object(self.inj, "_is_terminal_target",
                              return_value=False), \
                 patch.object(self.inj, "_assess_target_editability",
                              return_value="unknown"):
                result = self.inj.inject("fail text")
        self.assertFalse(result)
        self.assertEqual(result.state, "injection_failed")
        self.assertTrue(result.clipboard_preserved,
                        "clipboard must be preserved on failure")
        self.assertIn("failed", result.reason)

    def test_inject_no_editable_target(self):
        """When no editable target, state=no_editable_target, clipboard preserved."""
        with patch.object(self.inj, "_lock", MagicMock()):
            with patch.object(self.inj, "_foreground_info",
                              return_value=(0, "", 0, "")), \
                 patch.object(self.inj, "_assess_target_editability",
                              return_value="no_editable"):
                result = self.inj.inject("no target text")
        self.assertFalse(result)
        self.assertEqual(result.state, "no_editable_target")
        self.assertTrue(result.clipboard_preserved,
                        "clipboard must NOT be touched for no_editable_target")


if __name__ == "__main__":
    unittest.main()
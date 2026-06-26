"""InjectionResult dataclass and paste verification tests.

Verifies the contract in CURRENT_TASK.md §C:

  inject() returns an InjectionResult with structured outcome data, not
  just a bool. The dataclass includes ok, verified, method, reason,
  clipboard_preserved, and target_restored fields, and is truthy via
  __bool__ for backward compatibility.

  paste() verifies text was consumed by checking clipboard after the
  paste delay. If our text is still on the clipboard, the paste likely
  didn't reach its target and paste() returns False.
"""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch, MagicMock

from infrastructure.injector import InjectionResult, Injector


class InjectionResultTests(unittest.TestCase):
    """Tests for InjectionResult dataclass."""

    def test_default_construction(self):
        """Default InjectionResult is falsy with empty fields."""
        r = InjectionResult()
        self.assertFalse(r, "__bool__ must be False by default")
        self.assertFalse(r.ok)
        self.assertFalse(r.verified)
        self.assertEqual(r.method, "")
        self.assertEqual(r.reason, "")
        self.assertFalse(r.clipboard_preserved)
        self.assertFalse(r.target_restored)

    def test_ok_construction(self):
        """InjectionResult(ok=True, method='clipboard') is truthy."""
        r = InjectionResult(ok=True, verified=True, method="clipboard",
                             reason="", clipboard_preserved=False)
        self.assertTrue(r, "__bool__ must be True when ok=True")
        self.assertTrue(r.ok)
        self.assertTrue(r.verified)
        self.assertEqual(r.method, "clipboard")

    def test_bool_backward_compat(self):
        """__bool__ works for backward compat: if r: treats as bool."""
        ok_r = InjectionResult(ok=True, method="uia")
        fail_r = InjectionResult(ok=False, reason="fail")
        self.assertTrue(bool(ok_r))
        self.assertFalse(bool(fail_r))

    def test_all_fields_stored(self):
        """All six fields are correctly stored and retrieved."""
        r = InjectionResult(
            ok=True, verified=True, method="win32_child",
            reason="", clipboard_preserved=False, target_restored=True)
        self.assertEqual(r.ok, True)
        self.assertEqual(r.verified, True)
        self.assertEqual(r.method, "win32_child")
        self.assertEqual(r.reason, "")
        self.assertEqual(r.clipboard_preserved, False)
        self.assertEqual(r.target_restored, True)

    def test_failure_preserves_clipboard(self):
        """Failure result has clipboard_preserved=True."""
        r = InjectionResult(ok=False, reason="all_three_layers_failed",
                             clipboard_preserved=True)
        self.assertFalse(r)
        self.assertTrue(r.clipboard_preserved)

    def test_inject_method_field_enum(self):
        """method field should be one of the known values."""
        valid = {"uia", "clipboard", "sendinput", "win32_child", ""}
        for method in valid:
            r = InjectionResult(ok=bool(method), method=method)
            self.assertIn(r.method, valid)


class InjectorPasteVerificationTests(unittest.TestCase):
    """Tests for paste() clipboard verification logic."""

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

    def test_paste_verified_when_text_consumed(self):
        """If clipboard no longer holds our text after paste, verified=True."""
        get_patch, set_patch, store = self._patch_clipboard("old-content")
        with get_patch, set_patch, \
             patch.object(self.inj, "_lock", MagicMock()):
            # Simulate: between the set and the verification check,
            # something consumed the clipboard text. We patch time.sleep
            # to flip the clipboard to a different value during the post
            # delay, as a real paste target would do.
            orig_sleep = time.sleep

            def consuming_sleep(seconds):
                if seconds == 0.25:  # post delay
                    store["text"] = "consumed-by-target"
                orig_sleep(seconds)

            with patch("time.sleep", side_effect=consuming_sleep):
                ok = self.inj.paste("hello")
        self.assertTrue(ok, "paste should return True when text was consumed")

    def test_paste_fails_when_text_still_on_clipboard(self):
        """If our text is still on clipboard after paste delay, verified=False."""
        get_patch, set_patch, store = self._patch_clipboard(None)
        with get_patch, set_patch, \
             patch.object(self.inj, "_lock", MagicMock()):
            # Simulate: text wasn't consumed — clipboard still has our text
            # after backup restore attempt
            def fake_set_not_consumed(text):
                store["text"] = text
                return True
            # paste() sets clipboard to "hello", then after delay checks
            # clipboard. If it still says "hello", paste wasn't consumed.
            store["text"] = "hello"
            ok = self.inj.paste("hello")
        self.assertFalse(ok,
                         "paste should return False when our text still on clipboard")

    def test_paste_set_text_failure_returns_false(self):
        """If _clipboard_set_text fails, paste returns False immediately."""
        get_patch, set_patch, store = self._patch_clipboard(None)
        with get_patch, \
             patch("infrastructure.injector._clipboard_set_text",
                   return_value=False), \
             patch.object(self.inj, "_lock", MagicMock()):
            ok = self.inj.paste("hello")
        self.assertFalse(ok)

    def test_inject_failure_returns_injection_result(self):
        """inject() returns InjectionResult, not bool."""
        result = self.inj.inject("test text")
        self.assertIsInstance(result, InjectionResult)
        # Without a real target, injection will fail — check structure
        self.assertIsInstance(result.ok, bool)
        self.assertIsInstance(result.verified, bool)
        self.assertIsInstance(result.method, str)
        self.assertIsInstance(result.reason, str)

    def test_inject_ok_truthy(self):
        """When injection succeeds, result is truthy with method set."""
        # Mock _direct_input to succeed
        with patch.object(self.inj, "_direct_input", return_value=True), \
             patch.object(self.inj, "_lock", MagicMock()):
            result = self.inj.inject("hello")
        self.assertTrue(result)
        self.assertEqual(result.method, "sendinput")

    def test_inject_fail_has_clipboard_preserved(self):
        """When injection fails, clipboard_preserved is True."""
        with patch.object(self.inj, "_lock", MagicMock()):
            # Stub all layers to fail
            with patch.object(self.inj, "_direct_input", return_value=False), \
                 patch.object(self.inj, "_foreground_info",
                              return_value=(0, "", 0, "")), \
                 patch.object(self.inj, "_get_context_for_strategy",
                              return_value={}), \
                 patch.object(self.inj, "_strategy_for_context",
                              return_value="send_input"), \
                 patch.object(self.inj, "_is_terminal_target",
                              return_value=False), \
                 patch("infrastructure.injector._clipboard_set_text",
                       return_value=True):
                result = self.inj.inject("fail text")
        self.assertFalse(result)
        self.assertTrue(result.clipboard_preserved)
        self.assertIn("failed", result.reason)


if __name__ == "__main__":
    unittest.main()
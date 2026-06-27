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
        valid_states = {"verified_success", "attempted_unverified",
                        "no_editable_target",
                        "injection_failed", "recognition_failed"}
        for s in valid_states:
            r = InjectionResult(ok=(s == "verified_success"), state=s)
            self.assertIn(r.state, valid_states)


class InjectorPasteTests(unittest.TestCase):
    """Tests for paste() — always restores backup, returns True once sent."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def _patch_clipboard(self, initial=None):
        """Patch clipboard read/write with a simple dict store.

        Also patches the snapshot module so paste() sees a TEXT or EMPTY
        snapshot mirroring the dict store, and `restore_snapshot` updates
        the same store. This lets the test inspect "the clipboard" via
        store['text'] after the call.
        """
        from infrastructure import clipboard_snapshot as snapmod
        store = {"text": initial}

        def fake_get():
            return store.get("text")

        def fake_set(text):
            store["text"] = text
            return True

        def fake_read_snapshot():
            t = store.get("text")
            if t is None:
                return snapmod.ClipboardSnapshot(kind="EMPTY")
            return snapmod.ClipboardSnapshot(kind="TEXT", text=t)

        def fake_restore_snapshot(snap):
            if snap.kind == "EMPTY":
                store["text"] = None
                return True
            if snap.kind == "TEXT":
                store["text"] = snap.text
                return True
            return False

        return (
            patch("infrastructure.injector._clipboard_get_text",
                  side_effect=fake_get),
            patch("infrastructure.injector._clipboard_set_text",
                  side_effect=fake_set),
            patch("infrastructure.clipboard_snapshot.read_snapshot",
                  side_effect=fake_read_snapshot),
            patch("infrastructure.clipboard_snapshot.restore_snapshot",
                  side_effect=fake_restore_snapshot),
            store,
        )

    def test_paste_always_restores_backup(self):
        """paste() always restores original clipboard after sending shortcut."""
        gp, sp, rsp, rrp, store = self._patch_clipboard("original-text")
        with gp, sp, rsp, rrp, \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("time.sleep"):
            ok, kind, restored = self.inj.paste("new text")
        self.assertTrue(ok, "paste() should return True once shortcut sent")
        self.assertEqual(kind, "TEXT")
        self.assertTrue(restored, "paste() must report restore_ok=True on success")
        # After paste, clipboard should be restored to original
        self.assertEqual(store["text"], "original-text",
                         "clipboard must be restored after paste")

    def test_paste_empty_backup_restored_empty(self):
        """When the snapshot is EMPTY, paste must restore it to None (empty)."""
        gp, sp, rsp, rrp, store = self._patch_clipboard(None)
        with gp, sp, rsp, rrp, \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("time.sleep"):
            ok, kind, restored = self.inj.paste("new text")
        self.assertTrue(ok)
        self.assertEqual(kind, "EMPTY")
        self.assertTrue(restored, "paste() must report restore_ok=True on success")
        # The new contract: EMPTY snapshot must be restored to EMPTY — final
        # text must NOT linger on the clipboard.
        self.assertIsNone(store["text"],
                          "EMPTY snapshot must restore clipboard to empty, "
                          "not leave the final text behind")

    def test_paste_refuses_unsupported_format(self):
        """paste() refuses to run when clipboard holds non-text/multi-format."""
        from infrastructure import clipboard_snapshot as snapmod
        with patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=snapmod.ClipboardSnapshot(
                       kind="UNSUPPORTED_OR_MULTIFORMAT",
                       formats=[2, 8], detail="CF_BITMAP,CF_DIB")), \
             patch.object(self.inj, "_lock", MagicMock()):
            ok, kind, restored = self.inj.paste("would-clobber-image")
        self.assertFalse(ok,
                         "paste must refuse when image/file content present")
        self.assertEqual(kind, "UNSUPPORTED_OR_MULTIFORMAT")
        self.assertTrue(restored, "clipboard untouched, restore trivially ok")

    def test_paste_refuses_read_failed(self):
        """paste() refuses when clipboard read fails (would risk data loss)."""
        from infrastructure import clipboard_snapshot as snapmod
        with patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=snapmod.ClipboardSnapshot(kind="READ_FAILED")), \
             patch.object(self.inj, "_lock", MagicMock()):
            ok, kind, restored = self.inj.paste("text")
        self.assertFalse(ok)
        self.assertEqual(kind, "READ_FAILED")
        self.assertTrue(restored, "clipboard untouched, restore trivially ok")

    def test_paste_set_text_failure_returns_false(self):
        """If _clipboard_set_text fails, paste returns False immediately."""
        from infrastructure import clipboard_snapshot as snapmod
        with patch("infrastructure.injector._clipboard_set_text",
                   return_value=False), \
             patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=snapmod.ClipboardSnapshot(kind="EMPTY")), \
             patch.object(self.inj, "_lock", MagicMock()):
            ok, kind, restored = self.inj.paste("hello")
        self.assertFalse(ok)
        self.assertEqual(kind, "set_failed")
        self.assertTrue(restored, "clipboard untouched, restore trivially ok")

    def test_paste_backup_restored_on_keybd_failure(self):
        """If keybd_event fails, backup is still restored."""
        gp, sp, rsp, rrp, store = self._patch_clipboard("backup")
        with gp, sp, rsp, rrp, \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("ctypes.windll.user32.keybd_event",
                   side_effect=Exception("keybd failed")), \
             patch("time.sleep"):
            ok, kind, restored = self.inj.paste("hello")
        self.assertFalse(ok)
        self.assertTrue(restored, "backup must be restored on keybd failure")
        self.assertEqual(store["text"], "backup",
                         "backup must be restored on keybd failure")


class InjectorResultTests(unittest.TestCase):
    """Tests for inject() return values and state."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_inject_returns_injection_result(self):
        """inject() returns InjectionResult, not bool."""
        from infrastructure import clipboard_snapshot as snapmod
        with patch.object(self.inj, "_lock", MagicMock()), \
             patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=snapmod.ClipboardSnapshot(kind="EMPTY")), \
             patch("infrastructure.clipboard_snapshot.restore_snapshot",
                   return_value=True):
            result = self.inj.inject("test text")
        self.assertIsInstance(result, InjectionResult)
        self.assertIn(result.state,
                      {"verified_success", "attempted_unverified",
                       "no_editable_target", "injection_failed",
                       "recognition_failed"})

    def test_inject_ok_truthy_with_state(self):
        """When injection succeeds via clipboard with readback, result.state is verified_success."""
        from infrastructure import clipboard_snapshot as snapmod
        # Make readback report the expected text in the post-paste snapshot.
        with patch.object(self.inj, "_direct_input", return_value=True), \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch.object(self.inj, "_snapshot_target_text",
                          side_effect=[(True, ""), (True, "hello")]), \
             patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=snapmod.ClipboardSnapshot(kind="EMPTY")), \
             patch("infrastructure.clipboard_snapshot.restore_snapshot",
                   return_value=True), \
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
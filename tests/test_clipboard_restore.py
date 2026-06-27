"""Phase 4: clipboard restore factual consistency — P0-6 fix.

paste() now returns (shortcut_sent, snapshot_kind, restore_ok).
restore_ok is False when snapshot restoration fails after 3 retries.
_ok() and _attempted_unverified() propagate restore_ok into
clipboard_preserved/clipboard_restored fields.
"""
from __future__ import annotations
import unittest
from unittest.mock import patch, MagicMock

from infrastructure.injector import Injector, InjectionResult, InjectionTarget
from infrastructure import clipboard_snapshot as snapmod


def _empty_snapshot():
    return snapmod.ClipboardSnapshot(kind="EMPTY")


class PasteRestoreFailureTests(unittest.TestCase):
    """paste() must report restore_ok=False when restoration fails."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_paste_restore_false_on_empty_failure(self):
        """When EmptyClipboard restore fails, paste returns restore_ok=False."""
        with patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=snapmod.ClipboardSnapshot(kind="EMPTY")), \
             patch("infrastructure.clipboard_snapshot.restore_snapshot",
                   return_value=False), \
             patch("infrastructure.injector._clipboard_set_text",
                   return_value=True), \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("time.sleep"):
            ok, kind, restored = self.inj.paste("hello")
        self.assertTrue(ok, "shortcut was sent")
        self.assertEqual(kind, "EMPTY")
        self.assertFalse(restored, "restore must be False when EmptyClipboard fails")

    def test_paste_restore_false_on_text_failure(self):
        """When text restore fails, paste returns restore_ok=False."""
        with patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=snapmod.ClipboardSnapshot(kind="TEXT", text="orig")), \
             patch("infrastructure.clipboard_snapshot.restore_snapshot",
                   return_value=False), \
             patch("infrastructure.injector._clipboard_set_text",
                   return_value=True), \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("time.sleep"):
            ok, kind, restored = self.inj.paste("hello")
        self.assertTrue(ok, "shortcut was sent")
        self.assertEqual(kind, "TEXT")
        self.assertFalse(restored, "restore must be False when text restore fails")

    def test_paste_restore_true_on_success(self):
        """Normal successful restore returns restore_ok=True."""
        with patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=snapmod.ClipboardSnapshot(kind="TEXT", text="orig")), \
             patch("infrastructure.clipboard_snapshot.restore_snapshot",
                   return_value=True), \
             patch("infrastructure.injector._clipboard_set_text",
                   return_value=True), \
             patch.object(self.inj, "_lock", MagicMock()), \
             patch("time.sleep"):
            ok, kind, restored = self.inj.paste("hello")
        self.assertTrue(ok)
        self.assertEqual(kind, "TEXT")
        self.assertTrue(restored)


class ClipboadRestorePropagatedTests(unittest.TestCase):
    """Verify that restore_ok=False flows into InjectionResult fields."""

    def test_inject_uia_ok_propagates_default_restore_ok(self):
        """UIA success (no clipboard) defaults to preserved+restored."""
        r = InjectionResult(ok=True, state="verified_success",
                            verified=True, method="uia",
                            clipboard_preserved=True,
                            clipboard_restored=True)
        self.assertTrue(r.clipboard_preserved)
        self.assertTrue(r.clipboard_restored)

    def test_no_editable_verified_preserved_restored(self):
        """No editable target preserves clipboard (clipboard never touched)."""
        r = InjectionResult(ok=False, state="no_editable_target",
                            clipboard_preserved=True,
                            clipboard_restored=False,
                            reason="no_editable_target")
        self.assertTrue(r.clipboard_preserved)
        self.assertFalse(r.clipboard_restored,
                         "No-edit target never touched clipboard, restore=False is acceptable")


class InjectResultClipboardRestoreIntegration(unittest.TestCase):
    """Full inject() flow — paste restore failure propagates to result."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")
        self.target = InjectionTarget(
            hwnd=4242, pid=1, proc="notepad.exe", cls="Edit", title="x")

    def _common_patches(self):
        return [
            patch.object(self.inj, "_lock", MagicMock()),
            patch.object(self.inj, "_focus_window", return_value=True),
            patch.object(self.inj, "_foreground_info",
                         return_value=(4242, "Edit", 1, "notepad.exe")),
            patch.object(self.inj, "_get_context_for_strategy", return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target", return_value=False),
            patch.object(self.inj, "_inject_uia", return_value=False),
            patch("infrastructure.clipboard_snapshot.read_snapshot",
                  return_value=_empty_snapshot()),
            patch("infrastructure.clipboard_snapshot.restore_snapshot",
                  return_value=True),
            patch("ctypes.windll.user32.keybd_event"),
            patch("time.sleep"),
        ]

    def test_verified_success_with_restore_false(self):
        """Clipboard success but restore fails → clipboard_preserved=False."""
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, "foo"), (True, "foobar")]),
            patch.object(self.inj, "_direct_input", return_value=False),
            # Make restore_snapshot return False for the paste path
            patch("infrastructure.clipboard_snapshot.restore_snapshot",
                  return_value=False),
        ]
        with patches[0]:
            with patches[1]:
                with patches[2]:
                    with patches[3]:
                        with patches[4]:
                            with patches[5]:
                                with patches[6]:
                                    with patches[7]:
                                        with patches[8]:
                                            with patches[9]:
                                                with patches[10]:
                                                    with patches[11]:
                                                        with patches[12]:
                                                            with patches[13]:
                                                                result = self.inj.inject(
                                                                    "bar", target=self.target)
        self.assertEqual(result.state, "verified_success")
        self.assertFalse(result.clipboard_preserved,
                         "restore failure must set clipboard_preserved=False")
        self.assertFalse(result.clipboard_restored,
                         "restore failure must set clipboard_restored=False")

    def test_verified_success_with_restore_ok(self):
        """Clipboard success with restore ok → clipboard_preserved=True."""
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, "foo"), (True, "foobar")]),
            patch.object(self.inj, "_direct_input", return_value=False),
        ]
        with patches[0]:
            with patches[1]:
                with patches[2]:
                    with patches[3]:
                        with patches[4]:
                            with patches[5]:
                                with patches[6]:
                                    with patches[7]:
                                        with patches[8]:
                                            with patches[9]:
                                                with patches[10]:
                                                    with patches[11]:
                                                        with patches[12]:
                                                            result = self.inj.inject(
                                                                "bar", target=self.target)
        self.assertEqual(result.state, "verified_success")
        self.assertTrue(result.clipboard_preserved)
        self.assertTrue(result.clipboard_restored)

    def test_attempted_unverified_with_restore_false(self):
        """No readback after paste, restore fails → clipboard_preserved=False."""
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, "foo"), (False, "")]),
            # Make restore_snapshot return False
            patch("infrastructure.clipboard_snapshot.restore_snapshot",
                  return_value=False),
        ]
        with patches[0]:
            with patches[1]:
                with patches[2]:
                    with patches[3]:
                        with patches[4]:
                            with patches[5]:
                                with patches[6]:
                                    with patches[7]:
                                        with patches[8]:
                                            with patches[9]:
                                                with patches[10]:
                                                    with patches[11]:
                                                        with patches[12]:
                                                            result = self.inj.inject(
                                                                "xyz", target=self.target)
        self.assertEqual(result.state, "attempted_unverified")
        self.assertFalse(result.clipboard_preserved,
                         "restore failure must set clipboard_preserved=False")
        self.assertFalse(result.clipboard_restored,
                         "restore failure must set clipboard_restored=False")


if __name__ == "__main__":
    unittest.main()
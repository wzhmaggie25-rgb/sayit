"""Clipboard snapshot tests — verify non-text/multi-format protection.

The injector's clipboard path now reads a `ClipboardSnapshot` first and
REFUSES to run when the clipboard holds anything we cannot safely restore
(images, file lists, HTML, RTF, custom formats, multiple formats, or any
read failure). This prevents silent destruction of user data — the bug
flagged by ROUND5_CODE_REVIEW.md P0-5.
"""
from __future__ import annotations
import sys
import unittest
from unittest.mock import patch, MagicMock

from infrastructure import clipboard_snapshot as snapmod
from infrastructure.clipboard_snapshot import (
    ClipboardSnapshot, CF_UNICODETEXT, CF_TEXT, CF_OEMTEXT, CF_LOCALE,
    CF_BITMAP, CF_DIB, CF_HDROP,
)
from infrastructure.injector import Injector


class SnapshotClassificationTests(unittest.TestCase):
    """Classifying the clipboard into EMPTY / TEXT / UNSUPPORTED / READ_FAILED."""

    def _patch_low_level(self, formats, text=None, open_ok=True):
        """Patch the low-level clipboard primitives used by read_snapshot."""
        u32 = MagicMock()
        # OpenClipboard
        u32.OpenClipboard.return_value = 1 if open_ok else 0
        u32.CloseClipboard.return_value = 1

        # EnumClipboardFormats(prev) returns the format AFTER `prev`, or 0
        # when there is nothing left. prev=0 starts iteration.
        seq = list(formats)

        def fake_enum(prev):
            if prev == 0:
                return seq[0] if seq else 0
            try:
                idx = seq.index(prev)
            except ValueError:
                return 0
            return seq[idx + 1] if idx + 1 < len(seq) else 0

        u32.EnumClipboardFormats.side_effect = fake_enum
        u32.GetClipboardFormatNameW.return_value = 0
        u32.GetClipboardData.return_value = 1 if text is not None else 0

        k32 = MagicMock()
        k32.GlobalLock.return_value = 0xCAFE if text is not None else 0
        k32.GlobalUnlock.return_value = 1

        wstring_at = MagicMock(return_value=text or "")

        return patch.multiple(
            "ctypes.windll",
            user32=u32, kernel32=k32,
        ), patch("ctypes.wstring_at", wstring_at)

    def test_empty_clipboard_classified_as_empty(self):
        u, w = self._patch_low_level(formats=[])
        with u, w:
            snap = snapmod.read_snapshot()
        self.assertEqual(snap.kind, "EMPTY")
        self.assertTrue(snap.is_empty)
        self.assertTrue(snap.safe_for_clipboard_paste)

    def test_text_only_classified_as_text(self):
        u, w = self._patch_low_level(
            formats=[CF_UNICODETEXT, CF_TEXT, CF_LOCALE, CF_OEMTEXT],
            text="hello world")
        with u, w:
            snap = snapmod.read_snapshot()
        self.assertEqual(snap.kind, "TEXT")
        self.assertEqual(snap.text, "hello world")
        self.assertTrue(snap.is_text)
        self.assertTrue(snap.safe_for_clipboard_paste)

    def test_image_classified_as_unsupported(self):
        u, w = self._patch_low_level(formats=[CF_BITMAP, CF_DIB])
        with u, w:
            snap = snapmod.read_snapshot()
        self.assertEqual(snap.kind, "UNSUPPORTED_OR_MULTIFORMAT")
        self.assertFalse(snap.safe_for_clipboard_paste)

    def test_file_list_classified_as_unsupported(self):
        """CF_HDROP (Windows file drag-drop) must be protected."""
        u, w = self._patch_low_level(formats=[CF_HDROP])
        with u, w:
            snap = snapmod.read_snapshot()
        self.assertEqual(snap.kind, "UNSUPPORTED_OR_MULTIFORMAT")
        self.assertFalse(snap.safe_for_clipboard_paste)

    def test_html_with_text_classified_as_unsupported(self):
        """Custom HTML format alongside text — protect rather than clobber."""
        u, w = self._patch_low_level(
            formats=[CF_UNICODETEXT, CF_LOCALE, 0xC04F],  # 0xC04F: custom registered fmt
            text="html-rich content")
        with u, w:
            snap = snapmod.read_snapshot()
        # CF_UNICODETEXT alone would be TEXT, but the extra non-text custom
        # format must downgrade to UNSUPPORTED to avoid losing the HTML.
        self.assertEqual(snap.kind, "UNSUPPORTED_OR_MULTIFORMAT")
        self.assertFalse(snap.safe_for_clipboard_paste)

    def test_read_failed_when_open_fails(self):
        u, w = self._patch_low_level(formats=[], open_ok=False)
        with u, w:
            snap = snapmod.read_snapshot()
        self.assertEqual(snap.kind, "READ_FAILED")
        self.assertFalse(snap.safe_for_clipboard_paste)


class InjectorPasteRefusesNonText(unittest.TestCase):
    """paste() must refuse to touch the clipboard when it holds non-text data."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_paste_refuses_image(self):
        with patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=ClipboardSnapshot(kind="UNSUPPORTED_OR_MULTIFORMAT",
                                                  formats=[CF_BITMAP, CF_DIB],
                                                  detail="CF_BITMAP,CF_DIB")), \
             patch.object(self.inj, "_lock", MagicMock()):
            ok, kind, restored = self.inj.paste("hello")
        self.assertFalse(ok)
        self.assertEqual(kind, "UNSUPPORTED_OR_MULTIFORMAT")
        self.assertTrue(restored)

    def test_paste_refuses_file_list(self):
        with patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=ClipboardSnapshot(kind="UNSUPPORTED_OR_MULTIFORMAT",
                                                  formats=[CF_HDROP],
                                                  detail="CF_HDROP")), \
             patch.object(self.inj, "_lock", MagicMock()):
            ok, kind, restored = self.inj.paste("hello")
        self.assertFalse(ok)
        self.assertEqual(kind, "UNSUPPORTED_OR_MULTIFORMAT")
        self.assertTrue(restored)

    def test_paste_refuses_read_failed(self):
        with patch("infrastructure.clipboard_snapshot.read_snapshot",
                   return_value=ClipboardSnapshot(kind="READ_FAILED")), \
             patch.object(self.inj, "_lock", MagicMock()):
            ok, kind, restored = self.inj.paste("hello")
        self.assertFalse(ok)
        self.assertEqual(kind, "READ_FAILED")
        self.assertTrue(restored)


class InjectorFallsThroughOnUnsafeSnapshot(unittest.TestCase):
    """When the clipboard holds non-text, inject() must skip clipboard and try SendInput."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    def test_inject_skips_clipboard_when_snapshot_unsupported(self):
        """Real-world case: user has an image on clipboard. SendInput should run."""
        with patch.object(self.inj, "_lock", MagicMock()):
            with patch.object(self.inj, "_get_focused_edit_hwnd",
                              return_value=0), \
                 patch.object(self.inj, "_foreground_info",
                              return_value=(0xABC, "", 0, "")), \
                 patch.object(self.inj, "_assess_target_editability",
                              return_value="editable"), \
                 patch.object(self.inj, "_get_context_for_strategy",
                              return_value={}), \
                 patch.object(self.inj, "_strategy_for_context",
                              return_value="clipboard"), \
                 patch.object(self.inj, "_is_terminal_target",
                              return_value=False), \
                 patch.object(self.inj, "_snapshot_target_text",
                              return_value=(True, "")), \
                 patch.object(self.inj, "_verify_target_text",
                              return_value="verified"), \
                 patch("infrastructure.clipboard_snapshot.read_snapshot",
                       return_value=ClipboardSnapshot(
                           kind="UNSUPPORTED_OR_MULTIFORMAT",
                           formats=[CF_BITMAP], detail="CF_BITMAP")), \
                 patch.object(self.inj, "_direct_input",
                              return_value=True) as direct_mock:
                result = self.inj.inject("text to inject")
        # SendInput should have been called as the fallback.
        self.assertTrue(direct_mock.called,
                        "inject must fall through to SendInput when clipboard is non-text")
        self.assertTrue(result.ok)
        self.assertEqual(result.method, "sendinput")


if __name__ == "__main__":
    unittest.main()

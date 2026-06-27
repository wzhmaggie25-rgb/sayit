"""Clipboard snapshot abstraction — protects non-text and unknown formats.

The Windows clipboard can hold many formats simultaneously (CF_UNICODETEXT,
CF_DIB/CF_BITMAP for images, CF_HDROP for files, CF_HTML, CF_RTF, custom
application-specific formats, …). The injector temporarily uses the
clipboard as a transport channel for Ctrl+V paste, but it must NEVER
silently destroy the user's existing content — that is data loss.

This module gives the injector a structured snapshot:

  EMPTY                       — clipboard truly contains nothing; safe to
                                temporarily write and then EmptyClipboard
                                back to restore the "empty" state.
  TEXT(value)                 — clipboard holds ONLY CF_UNICODETEXT/CF_TEXT
                                with a known string; safe to restore by
                                writing the same string back.
  UNSUPPORTED_OR_MULTIFORMAT  — clipboard holds image/file/HTML/RTF/custom
                                or multiple non-text formats; the injector
                                MUST skip any clipboard-based path so we
                                do not clobber it.
  READ_FAILED                 — OpenClipboard() failed (another process is
                                holding it, etc.); be conservative and
                                skip clipboard injection.

The text-list of "safe" formats here is intentionally narrow. Anything
else — even CF_LOCALE or CF_OEMTEXT alongside CF_UNICODETEXT — is treated
as multi-format and protected.
"""
from __future__ import annotations
import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Windows clipboard format constants ────────────────────────────
CF_TEXT = 1
CF_BITMAP = 2
CF_METAFILEPICT = 3
CF_SYLK = 4
CF_DIF = 5
CF_TIFF = 6
CF_OEMTEXT = 7
CF_DIB = 8
CF_PALETTE = 9
CF_PENDATA = 10
CF_RIFF = 11
CF_WAVE = 12
CF_UNICODETEXT = 13
CF_ENHMETAFILE = 14
CF_HDROP = 15
CF_LOCALE = 16
CF_DIBV5 = 17

# Formats that are safe synonyms of CF_UNICODETEXT — Windows auto-converts
# between them, so their presence alongside CF_UNICODETEXT does not mean
# "multiple distinct formats". CF_LOCALE is set by USER32 whenever text is
# on the clipboard and is not user content.
_TEXT_SAFE_AUTOFORMATS = frozenset({CF_TEXT, CF_OEMTEXT, CF_UNICODETEXT, CF_LOCALE})

GMEM_MOVEABLE = 0x0002


@dataclass
class ClipboardSnapshot:
    """Structured snapshot of the Windows clipboard at a point in time."""
    kind: str = "READ_FAILED"  # one of EMPTY / TEXT / UNSUPPORTED_OR_MULTIFORMAT / READ_FAILED
    text: Optional[str] = None
    formats: List[int] = field(default_factory=list)
    # When kind == UNSUPPORTED_OR_MULTIFORMAT, this carries a list of format
    # ids/names — used for logging only, never for content reproduction.
    detail: str = ""

    @property
    def is_empty(self) -> bool:
        return self.kind == "EMPTY"

    @property
    def is_text(self) -> bool:
        return self.kind == "TEXT"

    @property
    def safe_for_clipboard_paste(self) -> bool:
        """True only when we can safely take the clipboard for a paste op
        and then restore it without data loss. EMPTY and TEXT qualify;
        anything else does not."""
        return self.kind in ("EMPTY", "TEXT")


def _open_clipboard(retries: int = 3, delay: float = 0.01) -> bool:
    import time
    for _ in range(retries):
        if ctypes.windll.user32.OpenClipboard(None):
            return True
        time.sleep(delay)
    return False


def _close_clipboard() -> None:
    try:
        ctypes.windll.user32.CloseClipboard()
    except Exception:
        pass


def _enumerate_formats() -> List[int]:
    """Return all currently-available clipboard formats in priority order."""
    formats: List[int] = []
    fmt = 0
    while True:
        fmt = ctypes.windll.user32.EnumClipboardFormats(fmt)
        if not fmt:
            break
        formats.append(fmt)
        if len(formats) > 64:  # guard against pathological cases
            break
    return formats


def _format_name(fmt: int) -> str:
    """Best-effort name for a clipboard format id (for logging only)."""
    standard = {
        CF_TEXT: "CF_TEXT", CF_BITMAP: "CF_BITMAP",
        CF_METAFILEPICT: "CF_METAFILEPICT",
        CF_OEMTEXT: "CF_OEMTEXT", CF_DIB: "CF_DIB",
        CF_PALETTE: "CF_PALETTE", CF_UNICODETEXT: "CF_UNICODETEXT",
        CF_ENHMETAFILE: "CF_ENHMETAFILE", CF_HDROP: "CF_HDROP",
        CF_LOCALE: "CF_LOCALE", CF_DIBV5: "CF_DIBV5",
        CF_TIFF: "CF_TIFF", CF_WAVE: "CF_WAVE", CF_RIFF: "CF_RIFF",
        CF_SYLK: "CF_SYLK", CF_DIF: "CF_DIF", CF_PENDATA: "CF_PENDATA",
    }
    if fmt in standard:
        return standard[fmt]
    # Registered custom format (HTML, RTF, Shell IDList Array, …)
    buf = ctypes.create_unicode_buffer(128)
    n = ctypes.windll.user32.GetClipboardFormatNameW(fmt, buf, 127)
    if n > 0:
        return buf.value
    return f"fmt#{fmt}"


def _read_text() -> Optional[str]:
    """Read CF_UNICODETEXT only (caller has already opened the clipboard)."""
    try:
        handle = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        locked = ctypes.windll.kernel32.GlobalLock(handle)
        if not locked:
            return None
        try:
            return ctypes.wstring_at(locked)
        finally:
            ctypes.windll.kernel32.GlobalUnlock(handle)
    except Exception:
        return None


def read_snapshot() -> ClipboardSnapshot:
    """Read the current clipboard into a ClipboardSnapshot.

    Never raises — failures return kind="READ_FAILED".
    """
    if not _open_clipboard():
        return ClipboardSnapshot(kind="READ_FAILED", detail="open_failed")
    try:
        formats = _enumerate_formats()
        if not formats:
            return ClipboardSnapshot(kind="EMPTY", formats=[])

        # Strip text-safe auto-conversions to decide whether non-text formats
        # are present. Windows fills CF_TEXT/CF_OEMTEXT/CF_LOCALE
        # automatically whenever an app writes CF_UNICODETEXT, so their
        # presence does not change the "text-only" classification.
        non_text_formats = [f for f in formats if f not in _TEXT_SAFE_AUTOFORMATS]

        if CF_UNICODETEXT in formats and not non_text_formats:
            text = _read_text()
            if text is None:
                # Format reported present but read failed — protect content.
                return ClipboardSnapshot(
                    kind="READ_FAILED", formats=formats,
                    detail="cf_unicodetext_read_failed")
            return ClipboardSnapshot(kind="TEXT", text=text, formats=formats)

        # Anything else: image, file list, HTML, RTF, custom, or multiple
        # distinct formats. Refuse to touch.
        names = [_format_name(f) for f in formats]
        logger.info(
            "[CLIPBOARD-SNAPSHOT] non-text formats present, protecting: %s",
            names[:8])
        return ClipboardSnapshot(
            kind="UNSUPPORTED_OR_MULTIFORMAT",
            formats=formats,
            detail=",".join(names[:8]),
        )
    finally:
        _close_clipboard()


def restore_snapshot(snap: ClipboardSnapshot) -> bool:
    """Restore a previously-captured snapshot to the clipboard.

    Only EMPTY and TEXT are restored. UNSUPPORTED_OR_MULTIFORMAT and
    READ_FAILED return False — callers must never have written over them
    in the first place. EMPTY restoration calls EmptyClipboard() so a
    paste consumer sees an empty clipboard, not the injector's text.

    Returns True on success.
    """
    if snap.kind == "EMPTY":
        if not _open_clipboard():
            return False
        try:
            ctypes.windll.user32.EmptyClipboard()
            return True
        finally:
            _close_clipboard()

    if snap.kind == "TEXT":
        # Use the existing path in injector — local helper avoids cycles.
        try:
            import pyperclip
        except Exception:
            pyperclip = None
        text = snap.text or ""
        if pyperclip is not None:
            try:
                pyperclip.copy(text)
                return True
            except Exception:
                pass
        # Win32 fallback
        if not _open_clipboard():
            return False
        try:
            ctypes.windll.user32.EmptyClipboard()
            data = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(data)
            handle = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not handle:
                return False
            locked = ctypes.windll.kernel32.GlobalLock(handle)
            if not locked:
                ctypes.windll.kernel32.GlobalFree(handle)
                return False
            try:
                ctypes.memmove(locked, ctypes.addressof(data), size)
            finally:
                ctypes.windll.kernel32.GlobalUnlock(handle)
            ctypes.windll.user32.SetClipboardData(CF_UNICODETEXT, handle)
            return True
        finally:
            _close_clipboard()

    # UNSUPPORTED_OR_MULTIFORMAT / READ_FAILED — refuse.
    return False

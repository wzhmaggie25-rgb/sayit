r"""Silent self-learning using a Typeless-style track edit session."""
from __future__ import annotations

import ctypes
import difflib
import logging
import threading
import time
from typing import Optional

from domain.correction import (
    learn_from_edit,
)
from infrastructure.context_helper_client import ContextHelperClient
from infrastructure.database import Database
from infrastructure.focus_context import (
    FocusContext,
    extract_inserted_region,
    get_focus_context,
    get_focus_context_for_window,
    includes_inserted_text,
    includes_terminal_inserted_text,
    is_terminal_app,
    normalize_track_text,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 0.3
TRACK_TIMEOUT_SECONDS = 15.0
DEBOUNCE_SECONDS = 0.8
MAX_DIFF_RATIO = 0.5
USER_EDIT_KEYS = frozenset({
    "A", "S", "D", "F", "H", "G", "Z", "X", "C", "V", "B", "Q", "W", "E",
    "R", "Y", "T", "O", "U", "I", "P", "L", "J", "K", "N", "M",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
    "=", "-", "]", "[", "'", ";", "\\", ",", "/", ".", "`",
    "Enter", "Tab", "Space", "Delete",
})


def _context_contains_inserted(context: FocusContext, text: str) -> bool:
    full_text = context.text_insertion_point.cursor_state.full_field_content
    if is_terminal_app(context.active_application):
        return includes_terminal_inserted_text(full_text, text)
    return includes_inserted_text(full_text, text)


class SilentMonitor:
    """Track user edits after injection and learn conservative corrections.

    Mirrors Typeless' track-edit shape:
    inject text -> confirm inserted text in focused input -> bind input identity
    -> watch small user edits -> learn rules and dictionary terms.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._history_id = ""
        self._refined_text = ""
        self._target_hwnd = 0
        self._running = False
        self._on_learned = None
        self._hotwords_mgr = None
        self._track_context: Optional[FocusContext] = None
        self._last_context: Optional[FocusContext] = None
        self._last_pressed_info: Optional[dict] = None
        self._last_enter_time = 0.0

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def set_on_learned(self, callback):
        self._on_learned = callback

    def start(self, history_id: str, original_text: str,
              hwnd: int, pid: int = 0, hotwords_mgr=None):
        if not original_text or not hwnd:
            return
        with self._lock:
            if self._running:
                logger.info("SilentMonitor: previous track still running; skip new track")
                return
            self._running = True
            self._history_id = str(history_id) if history_id else ""
            self._refined_text = original_text
            self._target_hwnd = int(hwnd)
            self._hotwords_mgr = hotwords_mgr
            self._track_context = None
            self._last_context = None
            self._last_pressed_info = None
            self._last_enter_time = 0.0

        thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name=f"silent-monitor-{str(history_id)[:8]}")
        thread.start()
        logger.info("SilentMonitor started: hid=%s hwnd=%#x len=%d",
                    str(history_id)[:8], hwnd, len(original_text))

    def stop(self):
        with self._lock:
            self._running = False

    def _monitor_loop(self):
        try:
            if not self._start_track():
                return

            start_time = time.monotonic()
            while time.monotonic() - start_time < TRACK_TIMEOUT_SECONDS:
                time.sleep(POLL_INTERVAL)
                if not self.is_running:
                    return
                self._poll_keyboard_events()

                context = self._get_current_context()
                if context is None:
                    continue

                track = self._track_context
                if track is None:
                    return
                if self._target_hwnd and context.active_application.hwnd != self._target_hwnd:
                    self._check_edited_text("switch_input_box")
                    return

                if context.input_box_identifier != track.input_box_identifier:
                    self._check_edited_text("switch_input_box")
                    return

                current_full = context.text_insertion_point.cursor_state.full_field_content

                if not current_full.strip():
                    self._mark_history("", "CLEAR_INPUT")
                    logger.info("SilentMonitor: input cleared; skip learning")
                    return

                self._last_context = context
                if _context_contains_inserted(context, self._refined_text):
                    continue

                time.sleep(DEBOUNCE_SECONDS)
                trigger = "press_enter" if self._recent_enter_pressed() else "track_timeout"
                self._check_edited_text(trigger)
                return

            self._check_edited_text("track_timeout")
        finally:
            self.stop()

    def _start_track(self) -> bool:
        context = None
        deadline = time.monotonic() + 1.2
        while time.monotonic() < deadline:
            context = self._get_current_context(self._refined_text)
            if context is None:
                time.sleep(0.1)
                continue
            full_text = context.text_insertion_point.cursor_state.full_field_content
            if _context_contains_inserted(context, self._refined_text):
                break
            time.sleep(0.1)
        if context is None:
            self._mark_history(None, "START_FAILED")
            logger.info("SilentMonitor: no focus context; start failed")
            return False
        if self._target_hwnd and context.active_application.hwnd != self._target_hwnd:
            self._mark_history(None, "START_FAILED")
            logger.info(
                "SilentMonitor: target hwnd changed before tracking expected=%#x actual=%#x",
                self._target_hwnd, context.active_application.hwnd)
            return False

        input_info = context.text_insertion_point
        full_text = input_info.cursor_state.full_field_content
        is_editable = input_info.input_capabilities.is_editable
        contains = _context_contains_inserted(context, self._refined_text)

        if (
            not context.active_application
            or (
                not is_editable
                and not is_terminal_app(context.active_application)
            )
            or not contains
        ):
            self._mark_history(full_text or None, "START_FAILED")
            logger.info(
                "SilentMonitor: start failed editable=%s contains=%s hwnd=%#x",
                is_editable, contains,
                context.active_application.hwnd)
            return False

        self._track_context = context
        self._last_context = context
        self._mark_history(None, "TRACKING", attempts_delta=0)
        logger.info(
            "SilentMonitor: track success hid=%s input=%s",
            self._history_id, context.input_box_identifier)
        return True

    def _check_edited_text(self, trigger_type: str):
        track = self._track_context
        current = self._last_context or self._get_current_context()
        if track is None or current is None:
            self._mark_history(None, "NO_FOCUS")
            return

        current_full = current.text_insertion_point.cursor_state.full_field_content
        if not current_full.strip():
            self._mark_history(current_full, "CLEAR_INPUT")
            return
        if _context_contains_inserted(current, self._refined_text):
            self._mark_history(None, "NOT_MODIFIED")
            return

        original_full = track.text_insertion_point.cursor_state.full_field_content
        full_stats = analyze_modification(original_full, current_full)
        if full_stats["is_large_modify"]:
            self._mark_history(None, "LARGE_MODIFY")
            logger.info("SilentMonitor: large full-field modify skip stats=%s", full_stats)
            return

        original_cursor = track.text_insertion_point.cursor_state
        edited_inserted = extract_inserted_region(
            current_full,
            original_cursor.text_before_cursor,
            original_cursor.text_after_cursor,
        )
        if edited_inserted is None:
            self._mark_history(current_full, "ANCHOR_LOST")
            logger.info("SilentMonitor: anchors lost; skip learning")
            return

        edited_inserted = normalize_track_text(edited_inserted).strip()
        original_inserted = normalize_track_text(self._refined_text).strip()
        if not edited_inserted or edited_inserted == original_inserted:
            self._mark_history(edited_inserted or None, "NOT_MODIFIED")
            return

        stats = analyze_modification(original_inserted, edited_inserted)
        if stats["is_large_modify"]:
            self._mark_history(None, "LARGE_MODIFY")
            logger.info("SilentMonitor: large modify skip stats=%s", stats)
            return

        self._learn(original_inserted, edited_inserted, trigger_type, stats)

    def _learn(self, original_text: str, edited_text: str,
               trigger_type: str, stats: dict):
        db = Database()
        try:
            existing_rules = db.get_rules(active_only=False)
            merged, count = learn_from_edit(
                original_text=original_text,
                edited_text=edited_text,
                existing_rules=existing_rules,
                history_id=self._history_id,
            )
            if count > 0:
                db.merge_rules(merged)

            # ── Phase 6: hotword promotion only (no auto-add bypass) ─
            # Dictionary entries must come ONLY from the promotion engine,
            # which requires ≥ 2 distinct history sessions. Single-edit
            # auto-add (removed _auto_add_dictionary_terms) would bypass
            # the two-history gate.
            promoted_word = self._maybe_promote_hotword(db)

            status = "EXTRACTED" if count or promoted_word else "NO_RULE"
            self._mark_history(edited_text, status)
            logger.info(
                "SilentMonitor: learned rules=%d promoted=%s trigger=%s stats=%s",
                count, promoted_word or "none", trigger_type, stats)

            if self._on_learned and (count or promoted_word):
                try:
                    self._on_learned(count + (1 if promoted_word else 0))
                except Exception as e:
                    logger.warning("SilentMonitor: callback error: %s", e)
        except Exception as e:
            self._mark_history(edited_text, "LEARN_FAILED")
            logger.warning("SilentMonitor: learn failed: %s", e)

    def _maybe_promote_hotword(self, db) -> Optional[str]:
        """Run the hotword promotion decision against current rules.

        Returns the promoted word (replacement string) if one was added
        to the dictionary, else None. At most one promotion per call.

        Only marks the rule as promoted AFTER the word has been
        successfully added to the dictionary (HotwordsManager + DB),
        so temporary failures keep the candidate eligible for retry.
        """
        try:
            from domain.hotword_promotion import decide_promotion
            rules = db.get_rules(active_only=False)
            decision = decide_promotion(rules)
            if not decision.promoted_word:
                return None
            word = decision.promoted_word
            pat, repl = decision.promoted_rule_keys
            # Phase 7: promotion requires HotwordsManager for ASR sync.
            # No DB-only fallback — without HotwordsManager, promotion
            # silently fails and the rule stays eligible for retry when
            # a HotwordsManager becomes available.
            added = False
            if self._hotwords_mgr is not None:
                try:
                    added = bool(self._hotwords_mgr.add_word(word))
                except Exception as e:
                    logger.warning(
                        "SilentMonitor: hotwords_mgr.add_word failed: %s", e)
            if added:
                # Only mark promoted after successful dictionary add.
                try:
                    db.mark_rule_promoted(pat, repl)
                except Exception as e:
                    logger.warning("SilentMonitor: mark_rule_promoted failed: %s", e)
                logger.info(
                    "[HOTWORD-PROMOTION] promoted replacement=%r (from pattern=%r) "
                    "to personal dictionary", word, pat)
                return word
            return None
        except Exception as e:
            logger.warning("SilentMonitor: hotword promotion error: %s", e)
            return None

    def _get_current_context(self, inserted_text: str = "") -> Optional[FocusContext]:
        if self._target_hwnd:
            anchor_text = inserted_text or self._refined_text
            context = get_focus_context_for_window(self._target_hwnd, anchor_text)
            if context is not None:
                return context
        return get_focus_context(inserted_text)

    def _mark_history(self, edited_text: Optional[str], status: str, attempts_delta: int = 1):
        if not self._history_id:
            return
        try:
            Database().update_history_edit(
                self._history_id,
                edited_text=edited_text,
                status=status,
                attempts_delta=attempts_delta,
            )
        except Exception as e:
            logger.debug("SilentMonitor: history edit update failed: %s", e)

    def _poll_enter_key(self):
        self._poll_keyboard_events()

    def _poll_keyboard_events(self):
        try:
            events = ContextHelperClient().poll_keyboard_events()
            self._record_keyboard_events(events)
            if events:
                return
        except Exception:
            pass
        try:
            if ctypes.windll.user32.GetAsyncKeyState(0x0D) & 0x8000:
                self._record_keyboard_events([{"keyName": "Enter"}])
        except Exception:
            pass

    def _record_keyboard_events(self, events: list[dict]):
        pressing_keys = [
            event for event in events
            if isinstance(event, dict) and event.get("keyName") in USER_EDIT_KEYS
        ]
        if not pressing_keys:
            return
        now = time.monotonic()
        self._last_pressed_info = {
            "timestamp": now,
            "pressingKeys": pressing_keys,
        }
        if any(event.get("keyName") == "Enter" for event in pressing_keys):
            self._last_enter_time = now

    def _recent_enter_pressed(self) -> bool:
        return bool(self._last_enter_time and time.monotonic() - self._last_enter_time < 1.0)


def analyze_modification(original_text: str, edited_text: str) -> dict:
    original = normalize_track_text(original_text)[:1000]
    edited = normalize_track_text(edited_text)[:1000]
    matcher = difflib.SequenceMatcher(None, original, edited, autojunk=False)
    added = removed = changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("insert", "replace"):
            added += max(0, j2 - j1)
        if tag in ("delete", "replace"):
            removed += max(0, i2 - i1)
        changed += max(i2 - i1, j2 - j1)
    base = max(len(original), 1)
    ratio = changed / base
    # Typeless reference/track_edit.js analysisModification compares the
    # first 1000 chars of the full field and treats >50% changed as large.
    return {
        "added_count": added,
        "removed_count": removed,
        "changed_count": changed,
        "change_ratio": ratio,
        "is_large_modify": changed > base * MAX_DIFF_RATIO,
    }

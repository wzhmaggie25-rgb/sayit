"""Silent-learning contract: user edit -> dictionary term -> ASR hotword."""
from __future__ import annotations

from dataclasses import dataclass
import difflib
import re


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_ASCII_TERM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*$")
_CJK_TERM_RE = re.compile(r"^[\u4e00-\u9fff]+$")
_MIXED_TERM_RE = re.compile(r"^[A-Za-z0-9_+\-\u4e00-\u9fff]+$")

MAX_ASCII_TERM_LEN = 32
MAX_CJK_TERM_LEN = 8
MAX_MIXED_TERM_LEN = 32


@dataclass(frozen=True)
class SilentLearningDecision:
    eligible: bool
    corrected_term: str = ""
    original_term: str = ""
    reason: str = ""


@dataclass(frozen=True)
class SilentLearningResult:
    learned: bool
    added: bool
    refreshed: bool
    reason: str = ""
    corrected_term_len: int = 0


def can_start_silent_learning(injection_state: str, target_verified: bool, target_hwnd: int) -> bool:
    """Return whether a pipeline result is eligible to start edit tracking."""
    return (
        injection_state == "verified_success"
        and bool(target_verified)
        and bool(target_hwnd)
    )


def classify_user_edit(original_inserted: str, edited_inserted: str) -> SilentLearningDecision:
    """Return the one corrected term from a clear single replacement.

    The policy is intentionally narrow. Insertions, deletions, sentence rewrites,
    multiple edits, punctuation-only changes, and phrase replacements are all
    rejected. Cross-script replacement is allowed because only the corrected term
    is stored as an ASR hotword; no global replacement rule is created.
    """
    original = (original_inserted or "").strip()
    edited = (edited_inserted or "").strip()
    if not original or not edited:
        return SilentLearningDecision(False, reason="empty_input")
    if original == edited:
        return SilentLearningDecision(False, reason="not_modified")
    if _CONTROL_RE.search(original) or _CONTROL_RE.search(edited):
        return SilentLearningDecision(False, reason="control_character")

    matcher = difflib.SequenceMatcher(None, original, edited, autojunk=False)
    opcodes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    if len(opcodes) != 1:
        return SilentLearningDecision(False, reason="multiple_or_ambiguous_edits")

    tag, i1, i2, j1, j2 = opcodes[0]
    if tag != "replace":
        return SilentLearningDecision(False, reason="insert_or_delete")

    original_term = original[i1:i2].strip()
    corrected_term = edited[j1:j2].strip()
    if not original_term or not corrected_term:
        return SilentLearningDecision(False, reason="empty_replacement")
    if original_term == corrected_term:
        return SilentLearningDecision(False, reason="same_term")

    corrected_term = _expand_corrected_term(edited, j1, j2, corrected_term)
    if not _is_safe_term(corrected_term):
        return SilentLearningDecision(False, reason="unsafe_term")

    return SilentLearningDecision(
        True,
        corrected_term=corrected_term,
        original_term=original_term,
        reason="eligible",
    )


def apply_silent_learning(decision: SilentLearningDecision, hotword_manager) -> SilentLearningResult:
    """Apply a learning decision through the production hotword manager.

    ``HotwordsManager.add_word`` is the production boundary that writes the
    personal dictionary and refreshes ASR hotword context when a new word is
    inserted. A duplicate still counts as a stable learned decision, but not as a
    new dictionary row.
    """
    if not decision.eligible:
        return SilentLearningResult(False, False, False, decision.reason)
    if hotword_manager is None or not hasattr(hotword_manager, "add_word"):
        return SilentLearningResult(False, False, False, "missing_hotword_manager")
    added = bool(hotword_manager.add_word(decision.corrected_term))
    return SilentLearningResult(
        learned=True,
        added=added,
        refreshed=added,
        reason="learned" if added else "already_present",
        corrected_term_len=len(decision.corrected_term),
    )


def _expand_corrected_term(edited: str, j1: int, j2: int, replacement: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_+\-]+", replacement):
        left = j1
        right = j2
        while left > 0 and re.fullmatch(r"[A-Za-z0-9_+\-]", edited[left - 1]):
            left -= 1
        while right < len(edited) and re.fullmatch(r"[A-Za-z0-9_+\-]", edited[right]):
            right += 1
        return edited[left:right]
    if not _CJK_TERM_RE.fullmatch(replacement):
        return replacement
    if len(replacement) != 1:
        return replacement
    if j2 < len(edited) and _is_cjk(edited[j2]):
        return replacement + edited[j2]
    if j1 > 0 and _is_cjk(edited[j1 - 1]):
        return edited[j1 - 1] + replacement
    return replacement


def _is_safe_term(term: str) -> bool:
    if not term or term.strip() != term:
        return False
    if _CONTROL_RE.search(term) or re.search(r"\s", term):
        return False
    if term.isdigit():
        return False
    if _ASCII_TERM_RE.fullmatch(term):
        return 2 <= len(term) <= MAX_ASCII_TERM_LEN
    if _CJK_TERM_RE.fullmatch(term):
        return 2 <= len(term) <= MAX_CJK_TERM_LEN
    if _MIXED_TERM_RE.fullmatch(term):
        return 2 <= len(term) <= MAX_MIXED_TERM_LEN
    return False


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"

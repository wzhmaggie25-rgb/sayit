"""Hotword promotion — promote learned replacements to personal dictionary.

When the silent-learning loop has confidently observed the same
``(pattern, replacement)`` correction in MULTIPLE distinct history
sessions, the replacement is a strong candidate for the user's personal
hotword dictionary. ASR can then bias toward it, eliminating the need
for the same correction next time.

The promotion algorithm is deliberately conservative — false promotions
silently change ASR behavior and are very hard to undo. Rules from
ROUND5_CODE_REVIEW.md / CLAUDE_LONG_TASK.md Phase 5:

  1. Same ``(pattern, replacement)`` must appear in ≥ 2 DISTINCT
     ``history_id`` values. Re-scanning the same history does not
     add evidence.
  2. Only the **replacement** is promoted to the dictionary. The
     pattern is never added — it is the wrong (misrecognized) form.
  3. If the same pattern has multiple competing replacements, none
     gets promoted unless ONE is the unique winner with a clear
     margin over runners-up.
  4. Whole-sentence rewrites, additive edits, multi-edit diffs, and
     overly long candidates are excluded (we never promote phrases
     longer than HOTWORD_MAX_LEN characters).
  5. Promotion is idempotent: a rule marked promoted does not promote
     again. Re-scanning yields the same result.
  6. At most ONE word may be promoted per call — this caps blast
     radius and gives the user visible, traceable changes.

The caller (SilentMonitor) is responsible for syncing the
``HotwordsManager`` after a successful promotion so the ASR layer
picks it up immediately.
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Conservative thresholds — favor missed promotions over wrong ones.
MIN_DISTINCT_HISTORIES = 2          # at least N distinct history_ids
HOTWORD_MAX_LEN = 12                # CJK characters / token chars
HOTWORD_MIN_LEN = 2                 # at least 2 chars (no single-char promotions)
MIN_WINNER_MARGIN = 1               # winner must lead runners-up by ≥ N histories

# CJK or alnum-with-CJK only — pure ASCII numbers / punctuation are not
# personal hotwords.
_PERSONAL_TERM_RE = re.compile(r"^[A-Za-z0-9_+\-一-鿿]+$")


@dataclass
class PromotionCandidate:
    """One ``(pattern, replacement)`` rule with evidence."""
    pattern: str
    replacement: str
    history_ids: set[str]
    already_promoted: bool = False

    @property
    def evidence_count(self) -> int:
        return len(self.history_ids)


@dataclass
class PromotionDecision:
    """Outcome of a single ``decide()`` call."""
    promoted_word: Optional[str] = None
    promoted_rule_keys: tuple[str, str] | None = None  # (pattern, replacement)
    reason: str = ""


def _is_eligible_term(replacement: str, pattern: str) -> bool:
    """A replacement is eligible to enter the dictionary iff it is short,
    is CJK/alnum, and is not the same as the pattern."""
    if not replacement or replacement == pattern:
        return False
    if len(replacement) < HOTWORD_MIN_LEN or len(replacement) > HOTWORD_MAX_LEN:
        return False
    if not _PERSONAL_TERM_RE.match(replacement):
        return False
    # Reject pattern == replacement-with-only-whitespace differences.
    if replacement.strip() == pattern.strip():
        return False
    return True


def _normalize_candidate(rule: dict, history_ids_extra: Iterable[str] = ()) -> PromotionCandidate:
    """Build a PromotionCandidate from a rules-table row.

    ``rule['source_history_ids']`` is expected to be a JSON-decoded list of
    distinct history ids the rule has been observed in. If the row predates
    this schema column we fall back to ``rule['source_history_id']`` (single
    id) and merge in anything from ``history_ids_extra``.
    """
    seen: set[str] = set()
    ids = rule.get("source_history_ids")
    if isinstance(ids, list):
        for hid in ids:
            if hid:
                seen.add(str(hid))
    legacy = rule.get("source_history_id")
    if legacy:
        seen.add(str(legacy))
    for hid in history_ids_extra:
        if hid:
            seen.add(str(hid))
    return PromotionCandidate(
        pattern=rule["pattern"],
        replacement=rule["replacement"],
        history_ids=seen,
        already_promoted=bool(rule.get("promoted", False)),
    )


def decide_promotion(rules: list[dict]) -> PromotionDecision:
    """Pick at most one rule to promote. Pure function — no side effects.

    Args:
        rules: list of rule rows. Each must have ``pattern`` and
               ``replacement``; should have ``source_history_ids`` (list)
               and ``promoted`` (bool). Other fields are ignored.

    Returns a ``PromotionDecision``; ``promoted_word`` is the replacement
    to add to the dictionary, or ``None`` to skip.
    """
    # Build candidates filtered by eligibility and not-yet-promoted.
    candidates: list[PromotionCandidate] = []
    for r in rules:
        cand = _normalize_candidate(r)
        if cand.already_promoted:
            continue
        if not _is_eligible_term(cand.replacement, cand.pattern):
            continue
        if cand.evidence_count < MIN_DISTINCT_HISTORIES:
            continue
        candidates.append(cand)

    if not candidates:
        return PromotionDecision(reason="no_eligible_candidates")

    # Group by pattern to detect contested patterns. A pattern with multiple
    # surviving replacements is ambiguous — skip the whole pattern unless
    # there is a unique winner with a margin.
    by_pattern: dict[str, list[PromotionCandidate]] = {}
    for c in candidates:
        by_pattern.setdefault(c.pattern, []).append(c)

    best: PromotionCandidate | None = None
    best_score = -1
    for pat, group in by_pattern.items():
        group.sort(key=lambda c: c.evidence_count, reverse=True)
        winner = group[0]
        runner_up = group[1].evidence_count if len(group) > 1 else 0
        margin = winner.evidence_count - runner_up
        if margin < MIN_WINNER_MARGIN:
            logger.info(
                "[HOTWORD-PROMOTION] pattern=%r contested winner=%d runner=%d — skipping",
                pat, winner.evidence_count, runner_up)
            continue
        # Pick the global best across patterns by evidence count.
        if winner.evidence_count > best_score:
            best = winner
            best_score = winner.evidence_count

    if best is None:
        return PromotionDecision(reason="all_contested_or_below_threshold")

    logger.info(
        "[HOTWORD-PROMOTION] promoting replacement=%r (pattern=%r) "
        "evidence=%d distinct histories",
        best.replacement, best.pattern, best.evidence_count)
    return PromotionDecision(
        promoted_word=best.replacement,
        promoted_rule_keys=(best.pattern, best.replacement),
        reason="unique_winner_with_margin",
    )

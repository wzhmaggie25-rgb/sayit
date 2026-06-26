"""Correction rule engine: diff extraction, rule generation, text application."""
from __future__ import annotations

import difflib
import logging
import re
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

MIN_PATTERN_LEN = 2
MAX_PATTERN_LEN = 30
MAX_DIFF_RATIO = 0.5
INITIAL_CONFIDENCE = 0.4
CONFIDENCE_INCREMENT = 0.15
MAX_CONFIDENCE = 0.95
MIN_CONFIDENCE_FOR_APPLY = 0.3
MIN_MATCH_COUNT_FOR_APPLY = 3
PROTECTED_PATTERN = re.compile(
    r"([A-Za-z]:\\|/|\\|`|```|\b(git|npm|python|pip|curl|powershell|cmd)\b)",
    re.IGNORECASE,
)


def extract_diffs(original: str, edited: str) -> list[dict]:
    """Extract character-level diff segments between original and edited text."""
    if not original or not edited:
        return []
    if len(original) > 30:
        ratio = difflib.SequenceMatcher(None, original, edited).ratio()
        if ratio < (1.0 - MAX_DIFF_RATIO):
            return []
    matcher = difflib.SequenceMatcher(None, original, edited, autojunk=False)
    diffs = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        diffs.append({
            "op": tag,
            "original_segment": original[i1:i2],
            "edited_segment": edited[j1:j2],
        })
    return diffs


def generate_rules(diffs: list[dict], source_history_id: str = None) -> list[dict]:
    """Generate correction rules from character diff segments."""
    rules = []
    for diff in diffs:
        if diff["op"] not in ("replace", "insert"):
            continue
        pattern = diff["original_segment"].strip()
        replacement = diff["edited_segment"].strip()
        if not _is_learnable_pattern(pattern, replacement):
            continue
        sim = difflib.SequenceMatcher(None, pattern, replacement).ratio()
        rules.append(_new_rule(pattern, replacement, source_history_id, sim))
    return rules


def generate_token_rules(original: str, edited: str,
                         source_history_id: str = None) -> list[dict]:
    """Generate safer whole-token rules for mixed Chinese/English edits."""
    rules = []
    original_tokens = _tokenize_for_learning(original)
    edited_tokens = _tokenize_for_learning(edited)
    matcher = difflib.SequenceMatcher(None, original_tokens, edited_tokens, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace" or (i2 - i1) != 1 or (j2 - j1) != 1:
            continue
        pattern = original_tokens[i1].strip()
        replacement = edited_tokens[j1].strip()
        if not _is_learnable_token_pair(pattern, replacement):
            continue
        sim = difflib.SequenceMatcher(None, pattern, replacement).ratio()
        rules.append(_new_rule(pattern, replacement, source_history_id, sim))
    return rules


def _extract_chinese_local_replacement(original: str, edited: str,
                                        source_history_id: str = None) -> list[dict]:
    """Extract single-CJK-character correction rules from a Chinese edit.

    Unlike generate_token_rules (which operates on coarse whitespace-separated
    tokens), this function uses character-level diff on CJK substrings to
    detect when a SINGLE Chinese character was replaced by another single
    Chinese character in a local context.

    Examples:
        "今天天气很好" → "今天天气不错"
        Finds: "很好" → "不错"  (2-char→2-char replacement)

        "我想去北京" → "我想去上海"
        Finds: "北京" → "上海"  (2-char→2-char replacement)

    Returns an empty list when the edit is not a clean local CJK replacement
    (e.g. multi-token edit, cross-script change, insert/delete).
    """
    if not original or not edited or original == edited:
        return []

    # Must contain CJK on both sides
    has_cjk_orig = bool(re.search(r"[一-鿿]", original))
    has_cjk_edit = bool(re.search(r"[一-鿿]", edited))
    if not has_cjk_orig or not has_cjk_edit:
        return []

    matcher = difflib.SequenceMatcher(None, original, edited, autojunk=False)
    diffs = [op for op in matcher.get_opcodes() if op[0] != "equal"]

    # Must be exactly one replacement segment (no insert/delete mixed in)
    if len(diffs) != 1:
        return []
    tag, i1, i2, j1, j2 = diffs[0]
    if tag != "replace":
        return []

    pattern = original[i1:i2]
    replacement = edited[j1:j2]

    # Both sides must be short CJK strings (at least 1, at most 6 chars)
    if not pattern or not replacement:
        return []
    if not re.fullmatch(r"[一-鿿]+", pattern):
        return []
    if not re.fullmatch(r"[一-鿿]+", replacement):
        return []
    if len(pattern) > 6 or len(replacement) > 6:
        return []
    if pattern == replacement:
        return []

    sim = difflib.SequenceMatcher(None, pattern, replacement).ratio()
    rules = []
    rules.append(_new_rule(pattern, replacement, source_history_id, sim))
    return rules


def merge_rules(existing_rules: list[dict], new_rules: list[dict]) -> tuple[list[dict], int]:
    """Merge new rules into existing rule store. Returns (merged_list, added_count).

    Matching is done on (pattern, replacement) pair — NOT on pattern alone.
    This prevents a conflicting replacement (same pattern, different correction)
    from silently reinforcing the old rule instead of creating a new one.
    """
    count = 0
    for rule in new_rules:
        existing = None
        for existing_rule in existing_rules:
            if (existing_rule["pattern"] == rule["pattern"]
                    and existing_rule["replacement"] == rule["replacement"]):
                existing = existing_rule
                break
        if existing:
            existing["confidence"] = min(
                MAX_CONFIDENCE, existing["confidence"] + CONFIDENCE_INCREMENT)
            existing["match_count"] = existing.get("match_count", 1) + 1
            existing["updated_at"] = datetime.now().isoformat()
        else:
            existing_rules.append(rule)
        count += 1
    return existing_rules, count


def apply_rules(text: str, rules: list[dict]) -> str:
    """Apply active correction rules to text."""
    result, _ = apply_rules_with_stats(text, rules)
    return result


def apply_rules_with_stats(text: str, rules: list[dict]) -> tuple[str, list[str]]:
    """Apply active correction rules and return applied rule IDs."""
    if not text:
        return text, []
    result = text
    applied: list[str] = []
    for rule in rules:
        if not rule.get("is_active", True):
            continue
        if rule.get("confidence", 0) < MIN_CONFIDENCE_FOR_APPLY:
            continue
        if rule.get("match_count", 0) < MIN_MATCH_COUNT_FOR_APPLY:
            continue
        pattern = rule["pattern"]
        replacement = rule["replacement"]
        if pattern in result:
            result = result.replace(pattern, replacement)
            if rule.get("id"):
                applied.append(rule["id"])
    return result, applied


# ── Strict dictionary auto-learn gating ─────────────────────────────
#
# Policy (2026-06-26 hardening): the personal dictionary feeds ASR hotwords
# and AI bodyguard prompts. A polluted dictionary persistently degrades
# future recognition — false positives are HIGH risk, not low. This rewrites
# the previous "broad" extractor with hard rules:
#
#   1. At most ONE candidate per edit.
#   2. Replacement must come from a SINGLE 1↔1 token replacement segment.
#      Anything looser (multi-token, insert, char-level diff) is rejected.
#   3. The replacement, on its own, must look like a single proper-noun /
#      product / tech-term token: no whitespace, no sentence punctuation
#      (Chinese or English), no control characters, length-bounded by
#      script, and matching one of three shape regexes.
#   4. The pattern (the ASR error side) must itself be a single shaped
#      token. Empty / whitespace-only / punctuation patterns are rejected
#      so we cannot accidentally promote "" → "整句".
#   5. Pattern and replacement must be in the same script family (both
#      contain CJK, or neither does) — this prevents direction reversal
#      where e.g. the ASR-correct CJK word is "replaced" by an unrelated
#      English fragment.
#
# This is the only public surface SilentMonitor calls. Correction rule
# learning (learn_from_edit) is a separate, looser system.
_DICT_REJECT_CHARS_RE = re.compile(
    r"["
    r"\s　"                      # whitespace incl. ideographic space
    r"，。！？；：、…—–·"            # Chinese punctuation
    r",\.!?;:'\"`~@#\$%\^&\*"        # ASCII punctuation
    r"\(\)\{\}\[\]<>\|\\/"
    r"\n\r\t"
    r"]"
)
_DICT_ASCII_TERM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*$")
_DICT_CJK_TERM_RE   = re.compile(r"^[一-鿿]+$")
_DICT_MIXED_TERM_RE = re.compile(r"^[A-Za-z0-9_+\-一-鿿]+$")

DICT_MAX_ASCII_LEN = 24    # CamelCase product names, e.g. "DashScope"
DICT_MAX_CJK_LEN   = 8     # ~2–8 CJK chars; longer is almost certainly a phrase
DICT_MAX_MIXED_LEN = 24


def extract_dictionary_terms(original_text: str, edited_text: str) -> list[str]:
    """Conservative auto-dictionary extraction (replacement-side only).

    Returns at most one term that satisfies every rule in the policy above.
    If the edit is anything other than a SINGLE clean 1↔1 token replacement
    where the replacement looks like a proper-noun-class token, returns [].

    This is the canonical safety entry point used by SilentMonitor; the
    correction rule engine (learn_from_edit) is intentionally not touched
    so user-edit rules can still be learned by a different code path.
    """
    if not original_text or not edited_text or original_text == edited_text:
        return []

    original_tokens = _tokenize_for_learning(original_text)
    edited_tokens = _tokenize_for_learning(edited_text)
    if not original_tokens or not edited_tokens:
        return []

    matcher = difflib.SequenceMatcher(
        None, original_tokens, edited_tokens, autojunk=False)
    opcodes = [op for op in matcher.get_opcodes() if op[0] != "equal"]

    # Rule 1+2: exactly one diff segment, must be 1↔1 replace.
    if len(opcodes) != 1:
        return []
    tag, i1, i2, j1, j2 = opcodes[0]
    if tag != "replace":
        return []
    if (i2 - i1) != 1 or (j2 - j1) != 1:
        return []

    pattern = original_tokens[i1]
    replacement = edited_tokens[j1]
    if not _is_safe_dictionary_term(replacement, pattern):
        return []
    return [replacement]


def _is_safe_dictionary_term(replacement: str, pattern: str) -> bool:
    """Hard gate for an auto-learned personal-dictionary candidate.

    Both sides must be clean single-token strings; replacement must look
    like a proper-noun-class term; both must share the same script family.
    Any uncertainty returns False — the policy is "skip if unsure".
    """
    if not replacement or not pattern:
        return False
    # Pattern must be a real non-empty token, not whitespace/punctuation —
    # otherwise we could "learn" anything as a brand-new dictionary entry.
    if not pattern.strip() or _DICT_REJECT_CHARS_RE.search(pattern):
        return False
    if not replacement.strip():
        return False
    if replacement == pattern:
        return False
    # Hard reject: any disallowed character (whitespace, punctuation, ...)
    if _DICT_REJECT_CHARS_RE.search(replacement):
        return False
    if PROTECTED_PATTERN.search(replacement) or PROTECTED_PATTERN.search(pattern):
        return False
    if replacement.isdigit() or pattern.isdigit():
        return False

    # Shape check — must match ONE of the recognized term forms and obey
    # the script-specific length cap.
    if _DICT_ASCII_TERM_RE.fullmatch(replacement):
        if not (2 <= len(replacement) <= DICT_MAX_ASCII_LEN):
            return False
    elif _DICT_CJK_TERM_RE.fullmatch(replacement):
        if not (2 <= len(replacement) <= DICT_MAX_CJK_LEN):
            return False
    elif _DICT_MIXED_TERM_RE.fullmatch(replacement):
        if not (2 <= len(replacement) <= DICT_MAX_MIXED_LEN):
            return False
    else:
        return False

    # Direction sanity: same script family. Prevents "我们" → "WeChat" type
    # cross-script swaps which usually indicate an unrelated paste, not a
    # correction of the same mis-recognized word.
    pat_cjk = bool(re.search(r"[一-鿿]", pattern))
    rep_cjk = bool(re.search(r"[一-鿿]", replacement))
    if pat_cjk != rep_cjk:
        return False
    return True


def learn_from_edit(original_text: str, edited_text: str,
                    existing_rules: list[dict],
                    history_id: str = None) -> tuple[list[dict], int]:
    """Full learning pipeline: token diff + character diff -> new rule candidates."""
    token_rules = generate_token_rules(
        original_text, edited_text, source_history_id=history_id)
    # Also try Chinese local character-level replacement — this catches
    # single-CJK corrections that tokenize_for_learning would merge into
    # a whole-sentence token pair and reject.
    chinese_rules = _extract_chinese_local_replacement(
        original_text, edited_text, source_history_id=history_id)
    diffs = extract_diffs(original_text, edited_text)
    if not token_rules and not chinese_rules and not diffs:
        return existing_rules, 0
    char_rules = [] if (token_rules or chinese_rules) else generate_rules(
        diffs, source_history_id=history_id)
    new_rules = _merge_new_rule_candidates(token_rules + chinese_rules + char_rules)
    if not new_rules:
        return existing_rules, 0
    return new_rules, len(new_rules)


def _new_rule(pattern: str, replacement: str,
              source_history_id: str | None, sim: float) -> dict:
    now = datetime.now().isoformat()
    return {
        "id": str(uuid.uuid4()),
        "pattern": pattern,
        "replacement": replacement,
        "source_type": "user_edit",
        "source_history_id": source_history_id,
        "confidence": INITIAL_CONFIDENCE + sim * 0.2,
        "match_count": 1,
        "apply_count": 0,
        "is_active": True,
        "is_regex": False,
        "created_at": now,
        "updated_at": now,
    }


def _is_learnable_pattern(pattern: str, replacement: str) -> bool:
    if not pattern or not replacement or pattern == replacement:
        return False
    if len(pattern) < MIN_PATTERN_LEN or len(pattern) > MAX_PATTERN_LEN:
        return False
    if pattern.isdigit() or replacement.isdigit():
        return False
    if PROTECTED_PATTERN.search(pattern) or PROTECTED_PATTERN.search(replacement):
        return False
    return True


def _is_learnable_token_pair(pattern: str, replacement: str) -> bool:
    if not _is_learnable_pattern(pattern, replacement):
        return False
    return bool(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_+-]*", pattern)
        or re.fullmatch(r"[A-Za-z][A-Za-z0-9_+-]*", replacement)
        or (re.search(r"[\u4e00-\u9fff]", pattern) and re.search(r"[\u4e00-\u9fff]", replacement))
    )


def _looks_like_dictionary_term(replacement: str, original: str) -> bool:
    if not replacement or len(replacement) > 40:
        return False
    if PROTECTED_PATTERN.search(replacement):
        return False
    if re.fullmatch(r"[A-Z][A-Za-z0-9_+-]{2,}", replacement):
        return True
    if re.search(r"[A-Z]", replacement) and re.search(r"[a-z]", replacement):
        return True
    if re.search(r"[\u4e00-\u9fff]", replacement) and len(replacement) >= 2:
        return bool(original and replacement != original)
    return False


def _tokenize_for_learning(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_+-]*|[\u4e00-\u9fff]+|\d+|[^\s]", text or "")


def _merge_new_rule_candidates(rules: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for rule in rules:
        key = f"{rule['pattern']}\0{rule['replacement']}"
        if key in seen:
            continue
        seen.add(key)
        result.append(rule)
    return result


def _dedupe_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(term)
    return result

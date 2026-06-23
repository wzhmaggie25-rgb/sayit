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


def merge_rules(existing_rules: list[dict], new_rules: list[dict]) -> tuple[list[dict], int]:
    """Merge new rules into existing rule store. Returns (merged_list, added_count)."""
    count = 0
    for rule in new_rules:
        existing = None
        for existing_rule in existing_rules:
            if existing_rule["pattern"] == rule["pattern"]:
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


def extract_dictionary_terms(original_text: str, edited_text: str) -> list[str]:
    """Identify likely proper nouns from user edits for automatic dictionary sync."""
    terms: list[str] = []
    for rule in generate_token_rules(original_text, edited_text):
        if _looks_like_dictionary_term(rule["replacement"], rule["pattern"]):
            terms.append(rule["replacement"])
    for diff in extract_diffs(original_text, edited_text):
        if diff.get("op") not in ("replace", "insert"):
            continue
        replacement = (diff.get("edited_segment") or "").strip()
        original = (diff.get("original_segment") or "").strip()
        if _looks_like_dictionary_term(replacement, original):
            terms.append(replacement)
    return _dedupe_terms(terms)


def learn_from_edit(original_text: str, edited_text: str,
                    existing_rules: list[dict],
                    history_id: str = None) -> tuple[list[dict], int]:
    """Full learning pipeline: token diff + character diff -> new rule candidates."""
    token_rules = generate_token_rules(
        original_text, edited_text, source_history_id=history_id)
    diffs = extract_diffs(original_text, edited_text)
    if not token_rules and not diffs:
        return existing_rules, 0
    char_rules = [] if token_rules else generate_rules(diffs, source_history_id=history_id)
    new_rules = _merge_new_rule_candidates(token_rules + char_rules)
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

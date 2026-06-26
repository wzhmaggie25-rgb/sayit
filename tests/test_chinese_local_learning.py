"""Chinese local correction learning tests.

Verifies the contract in CURRENT_TASK.md §A:

  When a user edits a Chinese sentence replacing a single CJK word with another,
  learn_from_edit should extract a local (character-level) replacement rule
  rather than treating the entire sentence as one token pair.

  Additionally, merge_rules must match on (pattern, replacement) pair — NOT
  just pattern alone — to prevent conflicting replacements from reinforcing
  the wrong rule.

Test approach
-------------
All tests call the correction module functions directly with sample
Chinese/English edits and verify the extracted rules match expectations.
"""
from __future__ import annotations
import copy
import unittest

from domain.correction import (
    _extract_chinese_local_replacement,
    learn_from_edit,
    merge_rules,
    generate_token_rules,
    extract_diffs,
)


class ChineseLocalReplacementTests(unittest.TestCase):
    """Tests for _extract_chinese_local_replacement."""

    # ── 1. Valid single CJK word replacements ─────────────────────

    def test_single_cjk_pair_extracts_rule(self):
        """"很好"→"不错" in a sentence produces a correction rule."""
        rules = _extract_chinese_local_replacement(
            "今天天气很好", "今天天气不错")
        self.assertEqual(len(rules), 1, "should produce exactly one rule")
        self.assertEqual(rules[0]["pattern"], "很好")
        self.assertEqual(rules[0]["replacement"], "不错")

    def test_single_cjk_char_replace(self):
        """Single character replacement: "吗"→"呢"."""
        rules = _extract_chinese_local_replacement(
            "你在干嘛吗", "你在干嘛呢")
        self.assertEqual(len(rules), 1)
        self.assertTrue(
            rules[0]["pattern"] == "吗" or "吗" in rules[0]["pattern"],
            f"pattern should involve '吗', got {rules[0]['pattern']!r}")
        self.assertIn("呢", rules[0]["replacement"])

    def test_city_name_correction(self):
        """"北京"→"上海" in a sentence."""
        rules = _extract_chinese_local_replacement(
            "我想去北京玩", "我想去上海玩")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["pattern"], "北京")
        self.assertEqual(rules[0]["replacement"], "上海")

    # ── 2. Non-CJK edits return empty ─────────────────────────────

    def test_ascii_only_returns_empty(self):
        """Pure ASCII edits should not go through CJK path."""
        rules = _extract_chinese_local_replacement(
            "hello world", "hello there")
        self.assertEqual(rules, [])

    def test_cjk_to_ascii_returns_empty(self):
        """Cross-script replacement (CJK→ASCII) is rejected."""
        rules = _extract_chinese_local_replacement(
            "我喜欢苹果", "我喜欢Apple")
        self.assertEqual(rules, [])

    # ── 3. Multi-segment edits return empty ───────────────────────

    def test_multiple_replacements_returns_empty(self):
        """Two separate CJK replacements in one edit → empty."""
        rules = _extract_chinese_local_replacement(
            "今天北京很好", "明天上海不错")
        self.assertEqual(rules, [])

    def test_insert_returns_empty(self):
        """Insertion (no replacement) returns empty."""
        rules = _extract_chinese_local_replacement(
            "北京", "北京上海")
        self.assertEqual(rules, [])

    # ── 4. Length gating ──────────────────────────────────────────

    def test_too_long_replacement_rejected(self):
        """Replacement longer than 6 CJK chars is rejected."""
        # "很好" → "非常非常非常好" diff gives "非常非常非常" (6 chars) — boundary case
        # Use a clearly too-long replacement where the diff segment exceeds 6
        rules = _extract_chinese_local_replacement(
            "明天去超市",
            "明天去超级市场购物中心")
        # Diff: "超市" → "超级市场购物中心" (7 chars) → rejected
        self.assertEqual(rules, [])

    def test_identical_pattern_replacement_returns_empty(self):
        """No change → empty."""
        rules = _extract_chinese_local_replacement(
            "今天天气很好", "今天天气很好")
        self.assertEqual(rules, [])

    def test_empty_original_returns_empty(self):
        rules = _extract_chinese_local_replacement("", "你好")
        self.assertEqual(rules, [])


class MergeRulesPairTests(unittest.TestCase):
    """Tests for the merge_rules (pattern, replacement) pair fix."""

    def setUp(self):
        self.existing = [
            {"pattern": "北京", "replacement": "上海",
             "confidence": 0.5, "match_count": 2,
             "id": "1", "is_active": True},
        ]

    def test_same_pair_increments_confidence(self):
        """Same (pattern, replacement) → confidence incremented."""
        new = [{"pattern": "北京", "replacement": "上海",
                "confidence": 0.4, "match_count": 1}]
        merged, count = merge_rules(copy.deepcopy(self.existing), new)
        self.assertEqual(count, 1)
        self.assertEqual(len(merged), 1)
        self.assertAlmostEqual(merged[0]["confidence"], 0.65)  # 0.5 + 0.15

    def test_different_replacement_creates_new_rule(self):
        """Same pattern but different replacement → NEW rule (not reinforce old)."""
        new = [{"pattern": "北京", "replacement": "南京",
                "confidence": 0.4, "match_count": 1}]
        merged, count = merge_rules(copy.deepcopy(self.existing), new)
        self.assertEqual(count, 1)
        self.assertEqual(len(merged), 2, "should have old + new rule")
        # Old rule unchanged
        old = [r for r in merged if r["replacement"] == "上海"]
        self.assertEqual(old[0]["confidence"], 0.5)
        # New rule added
        new_rules = [r for r in merged if r["replacement"] == "南京"]
        self.assertEqual(len(new_rules), 1)

    def test_completely_different_rule_adds_new(self):
        """Different pattern + replacement → new rule."""
        new = [{"pattern": "苹果", "replacement": "橘子",
                "confidence": 0.4, "match_count": 1}]
        merged, count = merge_rules(copy.deepcopy(self.existing), new)
        self.assertEqual(count, 1)
        self.assertEqual(len(merged), 2)


class LearnFromEditChineseTests(unittest.TestCase):
    """Tests that learn_from_edit extracts CJK local rules."""

    def test_chinese_word_correction_produces_rules(self):
        """User corrects "很好"→"不错" in a sentence → one rule."""
        rules, count = learn_from_edit(
            "今天天气很好", "今天天气不错",
            existing_rules=[])
        self.assertGreaterEqual(count, 1,
                                "should produce at least one rule")
        patterns = [(r["pattern"], r["replacement"]) for r in rules]
        self.assertIn(("很好", "不错"), patterns,
                      "chinese local replacement should be included")

    def test_chinese_city_correction(self):
        """"北京"→"上海" → correction rule generated."""
        rules, count = learn_from_edit(
            "我想去北京", "我想去上海",
            existing_rules=[])
        self.assertGreaterEqual(count, 1)
        patterns = [(r["pattern"], r["replacement"]) for r in rules]
        self.assertIn(("北京", "上海"), patterns)

    def test_ascii_typo_still_works(self):
        """Existing token-level learning still works for ASCII."""
        rules, count = learn_from_edit(
            "hello wrld", "hello world",
            existing_rules=[])
        self.assertGreaterEqual(count, 1)
        patterns = [(r["pattern"], r["replacement"]) for r in rules]
        self.assertIn(("wrld", "world"), patterns)

    def test_merge_rules_integration(self):
        """learn_from_edit + merge_rules work together."""
        rules, count = learn_from_edit(
            "今天北京天气", "今天上海天气",
            existing_rules=[])
        self.assertGreaterEqual(count, 1)

        # Now merge into existing list
        existing = []
        merged, added = merge_rules(existing, rules)
        self.assertGreaterEqual(added, 1)

        # Same edit again → merge bumps confidence
        rules2, _ = learn_from_edit(
            "今天北京天气", "今天上海天气",
            existing_rules=[])
        merged2, added2 = merge_rules(merged, rules2)
        self.assertGreaterEqual(added2, 1)  # same pair exists → increments


if __name__ == "__main__":
    unittest.main()
from __future__ import annotations

import unittest

import infrastructure.silent_monitor as silent_monitor
from domain.correction import apply_rules_with_stats
from domain.silent_learning import can_start_silent_learning, classify_user_edit


class FakeHotwordsManager:
    def __init__(self, existing: list[str] | None = None):
        self.words = list(existing or [])
        self.add_calls: list[str] = []

    def add_word(self, word: str, pinyin: str = "") -> bool:
        self.add_calls.append(word)
        if word in self.words:
            return False
        self.words.append(word)
        return True


class ContractDatabase:
    updates: list[dict] = []
    merged_rules: list[dict] = []
    rules: list[dict] = []

    def __init__(self):
        pass

    @classmethod
    def reset(cls, rules: list[dict] | None = None):
        cls.updates = []
        cls.merged_rules = []
        cls.rules = list(rules or [])

    def get_rules(self, active_only: bool = False):
        if active_only:
            return [rule for rule in self.rules if rule.get("is_active", True)]
        return list(self.rules)

    def merge_rules(self, rules):
        self.merged_rules.extend(rules)
        self.rules.extend(rules)
        return len(rules)

    def mark_rule_promoted(self, pattern: str, replacement: str) -> bool:
        for rule in self.rules:
            if rule.get("pattern") == pattern and rule.get("replacement") == replacement:
                rule["promoted"] = True
                return True
        return False

    def update_history_edit(self, entry_id, edited_text, status, attempts_delta=1):
        self.updates.append({
            "entry_id": entry_id,
            "edited_text": edited_text,
            "status": status,
            "attempts_delta": attempts_delta,
        })


def legacy_rule(pattern: str, replacement: str, **overrides) -> dict:
    rule = {
        "id": f"{pattern}->{replacement}",
        "pattern": pattern,
        "replacement": replacement,
        "source_type": "user_edit",
        "source_history_id": "old",
        "source_history_ids": ["h1", "h2"],
        "confidence": 0.95,
        "match_count": 3,
        "apply_count": 0,
        "is_active": True,
        "is_regex": False,
        "promoted": False,
    }
    rule.update(overrides)
    return rule


class SilentLearningDictionaryHotwordContractTests(unittest.TestCase):
    def setUp(self):
        self._old_database = silent_monitor.Database
        silent_monitor.Database = ContractDatabase
        ContractDatabase.reset()

    def tearDown(self):
        silent_monitor.Database = self._old_database

    def _learn(self, original: str, edited: str,
               hotwords: FakeHotwordsManager | None = None):
        monitor = silent_monitor.SilentMonitor()
        monitor._history_id = "contract-history"
        monitor._hotwords_mgr = hotwords or FakeHotwordsManager()
        monitor._learn(
            original_text=original,
            edited_text=edited,
            trigger_type="track_timeout",
            stats={"is_large_modify": False},
        )
        return monitor._hotwords_mgr

    def test_single_chinese_term_correction_adds_corrected_term_to_hotwords(self):
        hotwords = self._learn("我今天去了民天广场", "我今天去了明天广场")

        self.assertEqual(hotwords.words, ["明天"])
        self.assertEqual(hotwords.add_calls, ["明天"])
        self.assertEqual(ContractDatabase.merged_rules, [])
        self.assertEqual(ContractDatabase.updates[-1]["status"], "EXTRACTED")

    def test_cross_script_product_name_preserves_case(self):
        hotwords = self._learn("我在用微差调试", "我在用WeChat调试")

        self.assertEqual(hotwords.words, ["WeChat"])
        self.assertEqual(hotwords.add_calls, ["WeChat"])
        self.assertEqual(ContractDatabase.merged_rules, [])

    def test_existing_dictionary_term_is_idempotent(self):
        hotwords = FakeHotwordsManager(existing=["WeChat"])

        result = self._learn("打开微差", "打开WeChat", hotwords=hotwords)

        self.assertEqual(result.words, ["WeChat"])
        self.assertEqual(result.add_calls, ["WeChat"])
        self.assertEqual(ContractDatabase.merged_rules, [])

    def test_sentence_rewrite_is_ignored(self):
        hotwords = self._learn("今天下午开会讨论预算", "预算会我们改到明天下午讨论")

        self.assertEqual(hotwords.words, [])
        self.assertEqual(hotwords.add_calls, [])
        self.assertEqual(ContractDatabase.merged_rules, [])
        self.assertEqual(ContractDatabase.updates[-1]["status"], "NO_RULE")

    def test_multiple_corrections_are_ignored(self):
        hotwords = self._learn("我用微差和豆抱", "我用WeChat和豆包")

        self.assertEqual(hotwords.words, [])
        self.assertEqual(hotwords.add_calls, [])
        self.assertEqual(ContractDatabase.merged_rules, [])

    def test_insertion_or_deletion_is_ignored(self):
        inserted = self._learn("打开豆包", "请打开豆包")
        deleted = self._learn("请打开豆包", "打开豆包")

        self.assertEqual(inserted.words, [])
        self.assertEqual(deleted.words, [])
        self.assertEqual(ContractDatabase.merged_rules, [])

    def test_punctuation_or_formatting_only_change_is_ignored(self):
        hotwords = self._learn("打开豆包", "打开豆包。")

        self.assertEqual(hotwords.words, [])
        self.assertEqual(hotwords.add_calls, [])
        self.assertEqual(ContractDatabase.merged_rules, [])

    def test_stale_or_unverified_target_is_ignored(self):
        self.assertFalse(can_start_silent_learning(
            "attempted_unverified",
            target_verified=False,
            target_hwnd=1001,
        ))
        self.assertFalse(can_start_silent_learning(
            "verified_success",
            target_verified=False,
            target_hwnd=1001,
        ))
        self.assertFalse(can_start_silent_learning(
            "verified_success",
            target_verified=True,
            target_hwnd=0,
        ))

    def test_legacy_rules_do_not_mutate_final_asr_text(self):
        rules = [
            legacy_rule("微差", "WeChat"),
            legacy_rule("WeChat", "微信"),
        ]

        result, applied = apply_rules_with_stats("打开微差", rules)

        self.assertEqual(result, "打开微差")
        self.assertEqual(applied, [])

    # --- P0-1: single-CJK expansion boundary tests (must FAIL on current code) ---

    def test_single_cjk_replacement_must_not_expand_to_neighbor(self):
        """天汽→天气 in '今天天汽很好' must NOT learn '气很'"""
        decision = classify_user_edit("今天天汽很好", "今天天气很好")
        self.assertFalse(decision.eligible,
                         f"Should be ineligible but learned '{decision.corrected_term}': {decision.reason}")

    def test_single_cjk_in_product_name_must_not_expand(self):
        """豆抱→豆包 in '我喜欢豆抱助手' must NOT learn '包助'"""
        decision = classify_user_edit("我喜欢豆抱助手", "我喜欢豆包助手")
        self.assertFalse(decision.eligible,
                         f"Should be ineligible but learned '{decision.corrected_term}': {decision.reason}")

    def test_single_cjk_in_platform_name_must_not_expand(self):
        """百练→百炼 in '阿里云百练平台' must NOT learn '炼平'"""
        decision = classify_user_edit("阿里云百练平台", "阿里云百炼平台")
        self.assertFalse(decision.eligible,
                         f"Should be ineligible but learned '{decision.corrected_term}': {decision.reason}")

    def test_single_cjk_replacement_returns_ambiguous_reason(self):
        """Single CJK replacement without proven boundary → ambiguous_single_cjk"""
        decision = classify_user_edit("天汽", "天气")
        self.assertFalse(decision.eligible)
        self.assertIn("ambiguous", decision.reason.lower())

    def test_clean_2_char_cjk_replacement_still_works(self):
        """Full 2-char CJK replacement (民天→明天) must still be eligible"""
        decision = classify_user_edit("民天", "明天")
        self.assertTrue(decision.eligible, f"Should be eligible: {decision.reason}")
        self.assertEqual(decision.corrected_term, "明天")

    def test_clean_3_char_cjk_replacement_still_works(self):
        """Full 3-char CJK replacement must still be eligible"""
        decision = classify_user_edit("阿巴阿", "阿巴阿巴")
        self.assertTrue(decision.eligible, f"Should be eligible: {decision.reason}")
        self.assertEqual(decision.corrected_term, "阿巴阿巴")

    def test_legacy_rules_do_not_auto_promote_hotwords(self):
        ContractDatabase.reset([
            legacy_rule("微差", "WeChat"),
        ])
        monitor = silent_monitor.SilentMonitor()
        monitor._hotwords_mgr = FakeHotwordsManager()

        promoted = monitor._maybe_promote_hotword(ContractDatabase())

        self.assertIsNone(promoted)
        self.assertEqual(monitor._hotwords_mgr.words, [])
        self.assertFalse(ContractDatabase.rules[0].get("promoted"))


if __name__ == "__main__":
    unittest.main()

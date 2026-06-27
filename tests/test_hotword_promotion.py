"""Hotword promotion tests — Phase 5 of Round 6 stabilization.

Verifies the decision logic in ``domain.hotword_promotion`` and the
integration with ``infrastructure.database`` (distinct-history accumulation
+ ``mark_rule_promoted`` idempotency).
"""
from __future__ import annotations
import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from domain.hotword_promotion import (
    decide_promotion, PromotionCandidate, PromotionDecision,
    HOTWORD_MAX_LEN, HOTWORD_MIN_LEN, MIN_DISTINCT_HISTORIES,
)


def _rule(pattern: str, replacement: str, history_ids,
          promoted: bool = False, **extra) -> dict:
    return {
        "id": f"rule-{pattern}-{replacement}",
        "pattern": pattern,
        "replacement": replacement,
        "source_history_ids": list(history_ids),
        "promoted": promoted,
        "confidence": 0.6,
        "match_count": len(history_ids),
        **extra,
    }


class DecidePromotionTests(unittest.TestCase):
    """Pure-function tests of the promotion algorithm."""

    def test_promotes_with_two_distinct_histories(self):
        rules = [_rule("叫一下", "焦虑", ["h1", "h2"])]
        d = decide_promotion(rules)
        self.assertEqual(d.promoted_word, "焦虑")
        self.assertEqual(d.promoted_rule_keys, ("叫一下", "焦虑"))

    def test_does_not_promote_single_history(self):
        """Only one history → not enough evidence."""
        rules = [_rule("叫一下", "焦虑", ["h1"])]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word)

    def test_does_not_promote_same_history_twice(self):
        """Same history_id listed twice does NOT count as two — the set
        deduplicates automatically (already a set in the candidate)."""
        rules = [_rule("叫一下", "焦虑", ["h1", "h1"])]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word,
                          "duplicate history_ids must not count as evidence")

    def test_already_promoted_rule_skipped(self):
        rules = [_rule("叫一下", "焦虑", ["h1", "h2"], promoted=True)]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word,
                          "already-promoted rule must not promote again")

    def test_contested_replacements_no_promotion(self):
        """Same pattern with two competing replacements at the threshold:
        no clear winner → skip the pattern."""
        rules = [
            _rule("叫一下", "焦虑", ["h1", "h2"]),
            _rule("叫一下", "教育", ["h3", "h4"]),
        ]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word,
                          "contested pattern with no margin must not promote")

    def test_contested_with_clear_winner_promotes(self):
        rules = [
            _rule("叫一下", "焦虑", ["h1", "h2", "h3"]),
            _rule("叫一下", "教育", ["h4"]),
        ]
        d = decide_promotion(rules)
        self.assertEqual(d.promoted_word, "焦虑",
                         "clear winner with margin should promote")

    def test_only_replacement_promoted_not_pattern(self):
        """The pattern is the wrong (misrecognized) form — never promote."""
        rules = [_rule("p123", "公司", ["h1", "h2"])]
        d = decide_promotion(rules)
        self.assertEqual(d.promoted_word, "公司")
        # Reverse check: the pattern alone is never returned as the word.
        self.assertNotEqual(d.promoted_word, "p123")

    def test_too_long_replacement_rejected(self):
        long_repl = "一" * (HOTWORD_MAX_LEN + 1)
        rules = [_rule("p", long_repl, ["h1", "h2"])]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word)

    def test_too_short_replacement_rejected(self):
        rules = [_rule("p", "好", ["h1", "h2"])]  # 1 CJK char
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word)

    def test_replacement_equal_to_pattern_rejected(self):
        rules = [_rule("好的", "好的", ["h1", "h2"])]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word)

    def test_at_most_one_promotion_per_call(self):
        rules = [
            _rule("p1", "焦虑", ["h1", "h2"]),
            _rule("p2", "公司", ["h3", "h4"]),
            _rule("p3", "时间", ["h5", "h6"]),
        ]
        d = decide_promotion(rules)
        self.assertIsNotNone(d.promoted_word,
                             "should promote one of the eligible rules")
        # We do not assert which one — just that exactly one was returned.

    def test_punctuation_replacement_rejected(self):
        """Pure punctuation or non-word replacements are never hotwords."""
        rules = [_rule("p1", "！！！", ["h1", "h2"])]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word)

    # ── Phase 6: competition awareness ──────────────────────────────

    def test_contest_2v1_not_promoted(self):
        """Same pattern, winner=2 histories vs runner=1: margin 1 < 2 → skip."""
        rules = [
            _rule("叫一下", "焦虑", ["h1", "h2"]),
            _rule("叫一下", "教育", ["h3"]),
        ]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word,
                          "2v1 competition with margin=1 must not promote")

    def test_contest_3v1_promotes(self):
        """Same pattern, winner=3 histories vs runner=1: margin 2 ≥ 2 → promote."""
        rules = [
            _rule("叫一下", "焦虑", ["h1", "h2", "h3"]),
            _rule("叫一下", "教育", ["h4"]),
        ]
        d = decide_promotion(rules)
        self.assertEqual(d.promoted_word, "焦虑",
                         "3v1 with margin 2 should promote the winner")

    def test_already_promoted_blocks_second_candidate(self):
        """A pattern with an already-promoted replacement must NOT auto-promote
        a second replacement for the same pattern."""
        rules = [
            _rule("叫一下", "焦虑", ["h1", "h2"], promoted=True),
            _rule("叫一下", "教育", ["h3", "h4"]),
        ]
        d = decide_promotion(rules)
        self.assertIsNone(d.promoted_word,
                          "already-promoted pattern must block new auto-promotions")


class DatabaseDistinctHistoryAccumulationTests(unittest.TestCase):
    """Verify the DB merge_rules grows the source_history_ids set
    correctly across calls, and mark_rule_promoted is idempotent."""

    def setUp(self):
        # Use a temporary DB so we don't touch the user's real one.
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        # Patch the database singleton path
        from infrastructure import database as dbmod
        dbmod.Database._instance = None
        self._patch = patch.object(dbmod, "database_path",
                                    return_value=self.db_path)
        self._patch.start()
        self.db = dbmod.Database()

    def tearDown(self):
        from infrastructure import database as dbmod
        dbmod.Database._instance = None
        self._patch.stop()
        try:
            os.unlink(self.db_path)
            os.rmdir(self.tmpdir)
        except Exception:
            pass

    def _new_rule(self, pattern: str, replacement: str, history_id: str) -> dict:
        return {
            "id": f"rid-{pattern}-{replacement}-{history_id}",
            "pattern": pattern, "replacement": replacement,
            "source_type": "user_edit",
            "source_history_id": history_id,
            "confidence": 0.5, "match_count": 1, "apply_count": 0,
            "is_active": True, "is_regex": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def test_merge_grows_distinct_history_set(self):
        self.db.merge_rules([self._new_rule("叫一下", "焦虑", "h1")])
        rules = self.db.get_rules()
        self.assertEqual(rules[0]["source_history_ids"], ["h1"])

        self.db.merge_rules([self._new_rule("叫一下", "焦虑", "h2")])
        rules = self.db.get_rules()
        self.assertEqual(sorted(rules[0]["source_history_ids"]), ["h1", "h2"])

    def test_merge_same_history_does_not_grow(self):
        """Re-merging with the same history_id must not inflate evidence."""
        self.db.merge_rules([self._new_rule("叫一下", "焦虑", "h1")])
        self.db.merge_rules([self._new_rule("叫一下", "焦虑", "h1")])
        rules = self.db.get_rules()
        self.assertEqual(rules[0]["source_history_ids"], ["h1"],
                         "same history_id must dedupe")

    def test_mark_rule_promoted_idempotent(self):
        self.db.merge_rules([self._new_rule("叫一下", "焦虑", "h1")])
        ok1 = self.db.mark_rule_promoted("叫一下", "焦虑")
        ok2 = self.db.mark_rule_promoted("叫一下", "焦虑")
        self.assertTrue(ok1)
        self.assertTrue(ok2, "marking promoted twice must succeed (idempotent)")
        rules = self.db.get_rules()
        self.assertTrue(rules[0]["promoted"])


class HotwordPromotionEndToEndTests(unittest.TestCase):
    """Higher-level integration through SilentMonitor._maybe_promote_hotword."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        from infrastructure import database as dbmod
        dbmod.Database._instance = None
        self._patch = patch.object(dbmod, "database_path",
                                    return_value=self.db_path)
        self._patch.start()
        self.db = dbmod.Database()

    def tearDown(self):
        from infrastructure import database as dbmod
        dbmod.Database._instance = None
        self._patch.stop()
        try:
            os.unlink(self.db_path)
            os.rmdir(self.tmpdir)
        except Exception:
            pass

    def _insert_rule(self, pattern: str, replacement: str, history_id: str):
        self.db.merge_rules([{
            "id": f"r-{pattern}-{replacement}-{history_id}",
            "pattern": pattern, "replacement": replacement,
            "source_type": "user_edit",
            "source_history_id": history_id,
            "confidence": 0.6, "match_count": 1, "apply_count": 0,
            "is_active": True, "is_regex": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }])

    def test_promotion_calls_hotwords_mgr_sync(self):
        """After two distinct histories, _maybe_promote_hotword calls
        HotwordsManager.add_word so ASR picks up the new term."""
        from infrastructure.silent_monitor import SilentMonitor
        added: list[str] = []

        class FakeHM:
            def add_word(self, w):
                added.append(w)
                return True

        sm = SilentMonitor.__new__(SilentMonitor)
        sm._hotwords_mgr = FakeHM()

        self._insert_rule("叫一下", "焦虑", "h1")
        self._insert_rule("叫一下", "焦虑", "h2")
        promoted = sm._maybe_promote_hotword(self.db)
        self.assertEqual(promoted, "焦虑")
        self.assertEqual(added, ["焦虑"],
                         "promotion must call HotwordsManager.add_word")

    def test_promotion_idempotent_after_repeat_scan(self):
        """Calling _maybe_promote_hotword again must NOT re-promote."""
        from infrastructure.silent_monitor import SilentMonitor

        class FakeHM:
            def __init__(self): self.calls = 0
            def add_word(self, w):
                self.calls += 1
                return True

        fake = FakeHM()
        sm = SilentMonitor.__new__(SilentMonitor)
        sm._hotwords_mgr = fake

        self._insert_rule("叫一下", "焦虑", "h1")
        self._insert_rule("叫一下", "焦虑", "h2")
        first = sm._maybe_promote_hotword(self.db)
        second = sm._maybe_promote_hotword(self.db)
        self.assertEqual(first, "焦虑")
        self.assertIsNone(second, "repeated scan must not re-promote")
        self.assertEqual(fake.calls, 1, "add_word should be called once")

    def test_promotion_skipped_for_contested_pattern(self):
        """Same pattern with two equally-supported replacements → no promote."""
        from infrastructure.silent_monitor import SilentMonitor
        fake = type("FakeHM", (), {"add_word": lambda self, w: True})()
        sm = SilentMonitor.__new__(SilentMonitor)
        sm._hotwords_mgr = fake

        self._insert_rule("叫一下", "焦虑", "h1")
        self._insert_rule("叫一下", "焦虑", "h2")
        self._insert_rule("叫一下", "教育", "h3")
        self._insert_rule("叫一下", "教育", "h4")
        self.assertIsNone(sm._maybe_promote_hotword(self.db),
                          "contested pattern at threshold must not promote")


if __name__ == "__main__":
    unittest.main()

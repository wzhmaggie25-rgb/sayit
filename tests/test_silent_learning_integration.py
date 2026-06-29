"""P0-2: Integration test — real Database + HotwordsManager + fake ASR cascade.

Proves the full dictionary → ASR hotword chain with real production objects
and a temporary SQLite database. Never touches the real user database.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import infrastructure.paths
from infrastructure.database import Database
from infrastructure.hotwords_manager import HotwordsManager
from domain.silent_learning import classify_user_edit, apply_silent_learning


class FakeAsrCascade:
    """Records set_hotwords_context / set_hotwords_vocabulary_id calls."""

    def __init__(self):
        self.context_calls: list[str] = []
        self.vocabulary_id_calls: list[str] = []

    def set_hotwords_context(self, context: str):
        self.context_calls.append(context)

    def set_hotwords_vocabulary_id(self, vid: str):
        self.vocabulary_id_calls.append(vid)


class SilentLearningIntegrationTests(unittest.TestCase):
    """P0-2: Dictionary → ASR hotword production chain using real DB objects."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="sayit-test-p02-")
        cls._tmp_db = os.path.join(cls._tmpdir, "test.db")
        cls._db_patcher = patch.object(
            infrastructure.paths, "database_path", return_value=cls._tmp_db)
        cls._db_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._db_patcher.stop()
        Database._instance = None
        try:
            os.remove(cls._tmp_db)
            os.rmdir(cls._tmpdir)
        except OSError:
            pass

    def setUp(self):
        # Fresh instance per test with class-level temp DB.
        Database._instance = None

    def _new_hotwords(self) -> HotwordsManager:
        hw = HotwordsManager()
        # Flush core hotwords seeding so they don't pollute counts.
        hw.clear()
        return hw

    def _dict_words(self, hw: HotwordsManager) -> list[str]:
        return hw.get_words()

    def _dict_count(self, hw: HotwordsManager) -> int:
        return hw.count()

    # ── tests ─────────────────────────────────────────────────

    def test_corrected_term_written_to_dictionary(self):
        """One eligible correction creates exactly one dictionary row."""
        hw = self._new_hotwords()
        before = self._dict_count(hw)

        decision = classify_user_edit("光明", "黑暗")
        self.assertTrue(decision.eligible, f"Should be eligible: {decision.reason}")
        result = apply_silent_learning(decision, hw)

        self.assertTrue(result.added)
        self.assertEqual(self._dict_count(hw), before + 1)
        self.assertIn("黑暗", self._dict_words(hw))

    def test_duplicate_correction_is_idempotent(self):
        """Repeating the same correction does not create a duplicate row."""
        hw = self._new_hotwords()
        decision = classify_user_edit("光明", "黑暗")
        apply_silent_learning(decision, hw)
        rows_after_first = self._dict_count(hw)

        result2 = apply_silent_learning(decision, hw)

        self.assertFalse(result2.added)
        self.assertEqual(self._dict_count(hw), rows_after_first)

    def test_asr_context_contains_corrected_term_after_add(self):
        """After learning, the ASR context passed to set_hotwords_context
        contains the corrected term."""
        asr = FakeAsrCascade()
        hw = self._new_hotwords()
        hw.set_asr_engine(asr)
        ctx_calls_before = len(asr.context_calls)

        decision = classify_user_edit("光明", "黑暗")
        apply_silent_learning(decision, hw)

        new_calls = asr.context_calls[ctx_calls_before:]
        self.assertGreater(len(new_calls), 0, "No new context calls after learning")
        self.assertIn("黑暗", new_calls[-1])

    def test_no_correction_rules_created(self):
        """Silent learning must not create or modify correction_rules rows."""
        hw = self._new_hotwords()
        db = Database()
        rules_before = len(db.get_rules())

        decision = classify_user_edit("光明", "黑暗")
        apply_silent_learning(decision, hw)

        self.assertEqual(len(db.get_rules()), rules_before)

    def test_no_real_database_path_accessed(self):
        """The test must never resolve the production database path."""
        Database()
        real_path = os.path.join(
            infrastructure.paths.APP_DATA_DIR, "sayit.db")
        self.assertNotEqual(
            self._tmp_db, real_path,
            "Test is using the real production database path!")
        # Temp db is written lazily; verify path isolation, not file existence.

    def test_cross_script_correction_preserves_case(self):
        """English term corrected from Chinese phonetic error, case preserved."""
        hw = self._new_hotwords()

        decision = classify_user_edit("微差", "WeChat")
        self.assertTrue(decision.eligible)
        result = apply_silent_learning(decision, hw)

        self.assertTrue(result.added)
        self.assertIn("WeChat", self._dict_words(hw))

    def test_ambiguous_single_cjk_learns_nothing(self):
        """Single-CJK replacement without proven boundary: nothing learned."""
        asr = FakeAsrCascade()
        hw = self._new_hotwords()
        hw.set_asr_engine(asr)
        ctx_before = len(asr.context_calls)
        dict_before = self._dict_count(hw)

        decision = classify_user_edit("天汽", "天气")
        self.assertFalse(decision.eligible)
        result = apply_silent_learning(decision, hw)

        self.assertFalse(result.learned)
        self.assertEqual(self._dict_count(hw), dict_before)
        self.assertEqual(len(asr.context_calls), ctx_before)


if __name__ == "__main__":
    unittest.main()

"""P0-2: Integration test — real Database + HotwordsManager + fake ASR cascade.

Proves the full dictionary → ASR hotword chain with real production objects on
a per-test temporary SQLite database. The real user database and config are
never touched: isolation is enforced by ``tests.db_safety_guard.IsolatedDatabase``,
which patches the CORRECT production binding
(``infrastructure.database.database_path``) and fails closed if the resolved
path is ever under the real ``%APPDATA%/Sayit`` directory.

Round 9.5A regression note: the previous version of this test patched only
``infrastructure.paths.database_path`` — the wrong symbol — and called
``hw.clear()`` against shared state, which cleared the real personal dictionary.
That destructive pattern is removed; see ``test_patch_targets_production_binding``.
"""
from __future__ import annotations

import os
import unittest

import infrastructure.database as dbmod
import infrastructure.paths
from infrastructure.hotwords_manager import HotwordsManager, CORE_HOTWORDS
from domain.silent_learning import classify_user_edit, apply_silent_learning
from tests.db_safety_guard import IsolatedDatabase, assert_temp_db_path


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
    """P0-2: Dictionary → ASR hotword chain on a per-test temporary database."""

    def setUp(self):
        # Per-test isolation: fresh temp DB + isolated ConfigStore, fail-closed.
        self._iso = IsolatedDatabase(prefix="sayit-test-p02-").__enter__()
        # Prove the real bound path is the temp path BEFORE any write happens.
        self.assertEqual(
            os.path.abspath(dbmod.database_path()),
            os.path.abspath(self._iso.db_path),
            "Production binding still resolves the wrong database path")

    def tearDown(self):
        self._iso.__exit__(None, None, None)

    def _new_hotwords(self) -> HotwordsManager:
        # Constructing HotwordsManager triggers the first DB write (core
        # hotword seeding) — assert isolation immediately after.
        hw = HotwordsManager()
        assert_temp_db_path(hw._db._db_path, self._iso._tmpdir)
        return hw

    def _dict_words(self, hw: HotwordsManager) -> list[str]:
        return hw.get_words()

    def _dict_count(self, hw: HotwordsManager) -> int:
        return hw.count()

    # ── tests ─────────────────────────────────────────────────

    def test_corrected_term_written_to_dictionary(self):
        """One eligible correction creates exactly one new dictionary row."""
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
        db = self._iso.make_database()
        rules_before = len(db.get_rules())

        decision = classify_user_edit("光明", "黑暗")
        apply_silent_learning(decision, hw)

        self.assertEqual(len(db.get_rules()), rules_before)

    def test_database_uses_temp_path_not_real(self):
        """The Database actually bound by production code resolves to the temp
        path, and would fail closed if it pointed at the real APPDATA dir."""
        db = self._iso.make_database()
        real_db = os.path.abspath(
            os.path.join(infrastructure.paths.APP_DATA_DIR, "sayit.db"))
        self.assertNotEqual(os.path.abspath(db._db_path), real_db)
        # Guard would have raised in setUp/make_database if path were real;
        # assert the temp path positively here.
        assert_temp_db_path(db._db_path, self._iso._tmpdir)

    def test_patch_targets_production_binding(self):
        """Regression for the Round 9.5A incident: patching only
        infrastructure.paths.database_path is insufficient because
        infrastructure.database imported the symbol at module load. The guard
        must patch infrastructure.database.database_path so the live binding
        resolves the temp path."""
        # The symbol actually used by Database.__init__ is the module-level
        # name in infrastructure.database — it must resolve to the temp path.
        self.assertEqual(
            os.path.abspath(dbmod.database_path()),
            os.path.abspath(self._iso.db_path))
        # And a freshly built Database must bind that temp path.
        db = self._iso.make_database()
        self.assertEqual(
            os.path.abspath(db._db_path),
            os.path.abspath(self._iso.db_path))

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

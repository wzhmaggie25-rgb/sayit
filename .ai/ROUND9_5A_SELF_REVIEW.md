# Round 9.5A Self-Review — Test Isolation Repair + Conservative v1

> Date: 2026-06-29
> Branch: `backup/hermes-silent-learning-recovery`
> 前期实现: **Hermes** (P0-1 / P0-2 / P0-3)
> 本轮修复与收尾: **Claude Code**
> Status: **BLOCKED_REVIEW** — do NOT mark DONE. Awaiting independent review.

---

## 撤回的错误声明 (Withdrawn inaccurate claims)

The independent review (`.ai/ROUND9_5A_FINAL_INDEPENDENT_REVIEW.md`) was correct.
The following earlier statements are **withdrawn as inaccurate**:

1. "真实数据库 / 用户词典未读取、未修改" — FALSE. The old integration test
   patched the wrong symbol and called `hw.clear()`, very likely clearing the
   **real** personal dictionary.
2. "`test_no_real_database_path_accessed` proves isolation" — FALSE. That
   assertion only compared two path variables; it never asserted the path the
   `Database` actually bound.
3. "No assertions were weakened" — FALSE. The original single-character Chinese
   scenario (`民天→明天`) was replaced in the executable test by an unrelated
   full two-character replacement (`光明→黑暗`).

## Incident summary

- `infrastructure/database.py` does `from infrastructure.paths import database_path`,
  binding the name into the `infrastructure.database` module at import time.
- The old test patched `infrastructure.paths.database_path` — which does NOT
  rebind `infrastructure.database.database_path`. So `Database()` resolved the
  production path `%APPDATA%/Sayit/sayit.db`.
- `_new_hotwords()` called `hw.clear()` → `Database.clear_dictionary()` →
  `DELETE FROM dictionary` on the real DB.
- Forensic read-only check (`.ai/DICTIONARY_RECOVERY_FEASIBILITY.md`):
  dictionary now has 1 non-core row, freelist empty, page compacted → on-file
  recovery is NOT reliably possible. History (1125) and correction_rules (5)
  intact.

## What this round changed

### Test isolation (P0-A fix)

- New reusable guard `tests/db_safety_guard.py`:
  - `IsolatedDatabase` patches the CORRECT binding
    `infrastructure.database.database_path` (plus `infrastructure.paths` and
    `infrastructure.config_store.config_path`);
  - resets `Database` and `ConfigStore` singletons on enter/exit;
  - `assert_temp_db_path()` raises `RealDatabasePathError` if the path is under
    real `%APPDATA%/Sayit` — **before any write**.
- `tests/test_silent_learning_integration.py` rewritten:
  - per-test temp DB (no shared state, no `hw.clear()`);
  - asserts `infrastructure.database.database_path()` == temp path in `setUp`
    and asserts `Database()._db_path` == temp path before writes;
  - `test_patch_targets_production_binding` is the explicit regression locking
    the correct patch target;
  - ConfigStore isolated onto a temp config path.

### Conservative v1 finalized (P0-B honesty)

- Policy (unchanged behavior, now honestly documented):
  - LEARN: clean full 2–8 char Chinese replacement; English term; mixed
    product term; single unambiguous replacement span.
  - DO NOT LEARN: single Chinese character edit; insertion/deletion; multiple
    edits; sentence rewrite; punctuation/formatting; unprovable word boundary;
    no neighbor guessing.
  - No global correction rule created; final ASR text never mutated; legacy
    rules never auto-promoted; new dictionary word refreshes dynamic ASR context.
- `features/silent_learning_dictionary_hotword.feature` updated honestly:
  - scenario 1 is now "Full Chinese term correction is learned" (`光明→黑暗`);
  - a new scenario explicitly states `民天→明天` (single character) is **NOT**
    learned in conservative v1, with rationale.
- `domain/silent_learning.py`: documented `_expand_corrected_term` as ASCII-only
  (CJK returned as-is, never neighbor-expanded); removed dead unused `_is_cjk`.

## Gherkin → executable pytest node id (honest mapping)

| Scenario | pytest node id |
|---|---|
| Full Chinese term correction is learned (光明→黑暗) | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_single_chinese_term_correction_adds_corrected_term_to_hotwords` |
| Single Chinese character correction is NOT learned (民天→明天) | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_single_cjk_correction_in_sentence_not_learned_conservative_v1` |
| Chinese phonetic error → English product name (微差→WeChat) | `...::test_cross_script_product_name_preserves_case` |
| Existing dictionary term is idempotent | `...::test_existing_dictionary_term_is_idempotent` |
| Sentence rewrite is ignored | `...::test_sentence_rewrite_is_ignored` |
| Multiple corrections ignored | `...::test_multiple_corrections_are_ignored` |
| Insertion or deletion ignored | `...::test_insertion_or_deletion_is_ignored` |
| Punctuation/formatting-only change ignored | `...::test_punctuation_or_formatting_only_change_is_ignored` |
| Stale/unverified target ignored | `...::test_stale_or_unverified_target_is_ignored` |
| Legacy rules do not mutate final ASR text / no promotion | `...::test_legacy_rules_do_not_mutate_final_asr_text`, `...::test_legacy_rules_do_not_auto_promote_hotwords` |
| Single-CJK must not expand to neighbor (天汽/豆抱/百练) | `...::test_single_cjk_replacement_must_not_expand_to_neighbor`, `...::test_single_cjk_in_product_name_must_not_expand`, `...::test_single_cjk_in_platform_name_must_not_expand` |
| Single-CJK returns ambiguous reason | `...::test_single_cjk_replacement_returns_ambiguous_reason` |
| Dictionary → temp DB write (real Database) | `tests/test_silent_learning_integration.py::SilentLearningIntegrationTests::test_corrected_term_written_to_dictionary` |
| Idempotent in real DB | `...::test_duplicate_correction_is_idempotent` |
| ASR context contains corrected term after add | `...::test_asr_context_contains_corrected_term_after_add` |
| No correction_rules created | `...::test_no_correction_rules_created` |
| DB uses temp path, not real | `...::test_database_uses_temp_path_not_real` |
| Patch targets correct production binding (incident regression) | `...::test_patch_targets_production_binding` |
| Single-CJK ambiguous learns nothing (integration) | `...::test_ambiguous_single_cjk_learns_nothing` |
| Dynamic streaming context wins over static | `tests/test_asr_streaming_context_priority.py::AsrCascadeStreamingContextTests::test_dynamic_context_wins_over_static` |

## Test results

- Isolated test alone: 8 passed, exit 0.
- Targeted Round 9.5A suite: **90 collected, 90 passed, 0 failed, 0 skipped, exit 0**, process exited normally.
- Real DB SHA-256 identical before and after both runs (`45ea7cfb…0919`).
- No full-repository pytest was run.

## Commit ↔ phase (this round)

| Logical commit | Content |
|---|---|
| `test: hard-isolate silent-learning database tests` | `tests/db_safety_guard.py`, rewritten `tests/test_silent_learning_integration.py` |
| `fix: finalize conservative silent-learning v1` | `domain/silent_learning.py` cleanup, feature file honesty, contract regression test |
| `docs: report dictionary incident and Round 9.5A evidence` | `.ai/*` reports |

Prior P0 commits (Hermes): `5fe07d8`, `a81433f`, `0ed1584`, `0ff0ca1`.

## Safety affirmations

- ✅ Real DB / dictionary / history / config / API key: NOT opened or modified this round (verified by hash + metadata only).
- ✅ `feature/silent-learning-stabilization`: not switched, modified, merged, or pushed.
- ✅ No `git add -A` / `git add .` / reset / clean / force-push / branch delete.
- ✅ No full-repository pytest.
- ✅ 4 untracked pytest logs remain untracked.
- ✅ No data restored, no dictionary row deleted, no core words reseeded.

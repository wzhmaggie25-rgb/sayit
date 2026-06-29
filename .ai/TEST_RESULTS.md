# Test Results — Round 9.5A (Test Isolation Repair + Conservative v1)

> Date: 2026-06-29
> Branch: `backup/hermes-silent-learning-recovery`
> 前期实现: **Hermes** (P0-1/P0-2/P0-3 commits)
> 本轮修复与收尾: **Claude Code** (test isolation repair + conservative v1 + reports)

---

## Final closeout update (global guard + dictionary reset round)

Added a pytest-wide fail-closed DB guard (`tests/conftest.py` +
`tests/db_safety_guard.py`) and proof tests (`tests/test_db_global_safety_guard.py`).

| Run | collected | passed | failed | skipped | exit | process |
|---|---|---|---|---|---|---|
| `test_db_global_safety_guard.py` | 7 | 7 | 0 | 0 | 0 | normal |
| `test_silent_learning_integration.py` | 8 | 8 | 0 | 0 | 0 | normal |
| Round 9.5A targeted (incl. guard file) | **97** | **97** | **0** | **0** | **0** | normal, ~0.92s |

Command for the targeted run:

```bash
python -m pytest \
  tests/test_db_global_safety_guard.py \
  tests/test_silent_learning_dictionary_hotword_contract.py \
  tests/test_silent_learning_integration.py \
  tests/test_asr_streaming_context_priority.py \
  tests/test_silent_monitor.py \
  tests/test_dictionary_safety.py \
  tests/test_hotword_promotion.py \
  tests/test_chinese_local_learning.py \
  -v --tb=short
```

Real DB SHA-256 before == after all test runs: `45ea7cfb…0919`, Modify
2026-06-29 15:53:01 — **unchanged during testing** (verified by file metadata +
hash; live DB never opened via Database/SQLite in tests). No full-repository
pytest was run.

The authorized dictionary reset (separate, post-test step) then changed the live
DB by design — see `.ai/FINAL_CLOSEOUT_REPORT.md`.

---

## 重要更正 (Correction of earlier claims)

Earlier Round 9.5A reports stated "真实数据库/用户词典未读取、未修改" and "No
assertions were weakened". **Those statements were inaccurate** and are
withdrawn:

- The previous `tests/test_silent_learning_integration.py` patched the WRONG
  symbol (`infrastructure.paths.database_path` instead of the live binding
  `infrastructure.database.database_path`) and called `hw.clear()`, so it very
  likely opened and **cleared the real personal dictionary**.
- The earlier "88 passed" run included that unsafe test; it must not be cited as
  merge evidence.

See `.ai/DB_SAFETY_ASSESSMENT_2026-06-29.md` and
`.ai/DICTIONARY_RECOVERY_FEASIBILITY.md`.

---

## Stage 1 — repaired isolated test, run ALONE

**Command:**

```bash
python -m pytest tests/test_silent_learning_integration.py -v --tb=short
```

| Metric | Value |
|---|---|
| collected | 8 |
| passed | 8 |
| failed | 0 |
| skipped | 0 |
| exit code | 0 |
| process exit | normal |
| wall time | 0.31s |

Real DB SHA-256 before == after: `45ea7cfb…0919` (unchanged, Modify 15:53:01).

The repaired test asserts the production binding `infrastructure.database.database_path`
resolves to a per-test temp path **before any write**, and fails closed if it
ever points under `%APPDATA%/Sayit`.

## Stage 2 — Round 9.5A targeted suite

**Command:**

```bash
python -m pytest \
  tests/test_silent_learning_dictionary_hotword_contract.py \
  tests/test_silent_learning_integration.py \
  tests/test_asr_streaming_context_priority.py \
  tests/test_silent_monitor.py \
  tests/test_dictionary_safety.py \
  tests/test_hotword_promotion.py \
  tests/test_chinese_local_learning.py \
  -v --tb=short
```

| Metric | Value |
|---|---|
| collected | **90** |
| passed | **90** |
| failed | **0** |
| skipped | **0** |
| exit code | **0** |
| process exit | normal (not hung) |
| wall time | 0.92s |

> Count is **90, not 88** (do not assume 88): the integration file went 7→8
> tests (added `test_patch_targets_production_binding`, renamed
> `test_no_real_database_path_accessed` → `test_database_uses_temp_path_not_real`),
> and the contract file went 16→17 (added
> `test_single_cjk_correction_in_sentence_not_learned_conservative_v1`).

### Real database integrity around the targeted run

| | SHA-256 | Modify time |
|---|---|---|
| before | `45ea7cfb9981e9563d95d25cfb72c2ac95d9717feefab435cde2347f753f0919` | 2026-06-29 15:53:01 |
| after  | `45ea7cfb9981e9563d95d25cfb72c2ac95d9717feefab435cde2347f753f0919` | 2026-06-29 15:53:01 |

**REAL DATABASE UNCHANGED.** Verified by file metadata + SHA-256 only; the real
DB was never opened via `Database`/SQLite in this round. The `sayit.db-wal`
(0-byte) / `sayit.db-shm` sidecars present are leftovers from the 17:15
read-only forensic inspection (mtime 17:15), not from this test run.

## Per-file result (targeted suite)

| File | Tests | Pass |
|---|---|---|
| `tests/test_silent_learning_dictionary_hotword_contract.py` | 17 | 17 |
| `tests/test_silent_learning_integration.py` | 8 | 8 |
| `tests/test_asr_streaming_context_priority.py` | 2 | 2 |
| `tests/test_silent_monitor.py` | 4 | 4 |
| `tests/test_dictionary_safety.py` | 24 | 24 |
| `tests/test_hotword_promotion.py` | 21 | 21 |
| `tests/test_chinese_local_learning.py` | 17 | 17 |
| **Total** | **90** | **90** |

## Scope / safety

- This is the Round 9.5A **targeted** run. **No full-repository pytest was run.**
- No real DB / dictionary / history / config / API key opened or modified.
- New temp-path protection: `tests/db_safety_guard.py::IsolatedDatabase` patches
  the correct binding, asserts the temp path before writes, and raises
  `RealDatabasePathError` if the path resolves under real `%APPDATA%/Sayit`.
- 4 untracked pytest logs remain untracked, not committed.

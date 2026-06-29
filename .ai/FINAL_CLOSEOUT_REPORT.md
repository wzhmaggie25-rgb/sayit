# Final Closeout Report — Round 9.5A

> Date: 2026-06-29
> Branch: `backup/hermes-silent-learning-recovery`
> Executors: Hermes (prior P0 fixes) + Claude Code (guard, isolation, dictionary reset, reports)
> Status: **BLOCKED_REVIEW** (awaiting ChatGPT independent review) — NOT DONE.

## What this closeout did

1. Added an automatic, pytest-wide fail-closed database guard.
2. Proved no test can open or migrate the real SayIt database.
3. Ran the guard tests, the isolated integration test, and the Round 9.5A
   targeted suite.
4. Confirmed the live database was byte-for-byte unchanged during all tests.
5. Created a fresh pre-reset raw + consistent backup outside the repo.
6. Reset ONLY the live `dictionary` table in one explicit transaction.
7. Removed the single synthetic test row; reseeded the 5 core hotwords.
8. Left `history` (1125) and `correction_rules` (5) unchanged.
9. Created a post-reset consistent backup.

## User decision

The user explicitly selected **Option 3**
(`.ai/USER_DECISION_DICTIONARY_RESET_2026-06-29.md`): accept that the previous
personal dictionary is unrecoverable from the preserved SQLite copies, keep
history and correction rules, remove the synthetic row, reseed the five built-in
core hotwords, and restart personal learning from zero.

## Global pytest database guard

- `tests/db_safety_guard.py` now also provides a process-wide guard: it wraps
  `sqlite3.connect` (the real connection boundary) and rejects any path inside
  the canonical real `%APPDATA%/Sayit` directory, snapshotted at import so later
  per-test path patching cannot move it. `:memory:` and temp-dir paths are
  allowed.
- `tests/conftest.py` installs that guard automatically for the whole pytest
  session (autouse session fixture) and restores the genuine connect at the end.
- Because it guards `sqlite3.connect`, it fires before schema migration,
  CREATE TABLE, INSERT/UPDATE/DELETE, or `PRAGMA journal_mode` — even when a test
  patches the wrong `database_path` symbol.
- Proof: `tests/test_db_global_safety_guard.py` (7 tests) shows an unguarded
  real-path `Database()` fails before connect (mock confirms the genuine connect
  is never called), the wrong-symbol patch is still blocked, temp paths and
  `:memory:` succeed, and `IsolatedDatabase` still works.

## Test results (pre-reset; no full-repo pytest)

| Run | collected | passed | failed | skipped | exit | process |
|---|---|---|---|---|---|---|
| `test_db_global_safety_guard.py` | 7 | 7 | 0 | 0 | 0 | normal |
| `test_silent_learning_integration.py` | 8 | 8 | 0 | 0 | 0 | normal |
| Round 9.5A targeted (incl. guard) | **97** | **97** | **0** | **0** | **0** | normal (~0.92s) |

Real DB SHA-256 before == after all tests: `45ea7cfb…0919`, Modify 15:53:01 —
**unchanged**. Verified by file metadata + hash only; the live DB was never
opened via `Database`/SQLite during tests.

## Dictionary reset (live DB write — authorized, dictionary table only)

Recovery directory (outside repo):
`D:\SayIt-Recovery20260629-185628-dictionary-reset\`
(`pre-reset-raw`, `pre-reset-consistent`, `post-reset-consistent`,
`DICTIONARY_RESET_REPORT.txt`).

| Count | before | after |
|---|---|---|
| dictionary total | 1 | 5 |
| dictionary non-core | 1 | 0 |
| core hotwords present | 0/5 | 5/5 |
| history total | 1125 | **1125 (unchanged)** |
| correction_rules total | 5 | **5 (unchanged)** |
| integrity_check | ok | ok |

| DB hash | value |
|---|---|
| pre-reset live (== raw copy) | `45ea7cfb9981e9563d95d25cfb72c2ac95d9717feefab435cde2347f753f0919` |
| pre-reset consistent backup | `219ca10e91fbba77b3b2b9e2ef17f452e1d935acf4830c172f0dd1ceeee5cb97` |
| post-reset live | `5838b47ebaf5072def17d1873dd4cb5efb7acc5b3a2fcaa2f16777d9e61590a8` |
| post-reset consistent backup | `bad60b533e6e9d616c870d90f5f85fb3fd412ed07d526fbe68cfc1eb2d2b4a3d` |

Method: one transaction `BEGIN IMMEDIATE; DELETE FROM dictionary;` + parameterized
INSERT of the 5 core words (pinyin empty, added_at = reset-time ISO), with a
precondition gate (1/0/1125/5) and in-transaction verification before COMMIT.

Core hotwords reseeded: **Sayit, Typeless, 闪电说, DeepSeek, DashScope**.
Personal dictionary now restarts from zero (only core words present).

## Safety affirmations

- Only the `dictionary` table changed. `history`, `correction_rules`,
  `schema_version` untouched.
- `HotwordsManager` was NOT instantiated; no remote vocabulary sync was run.
- Configuration / API keys NOT read or modified.
- Consistent backups opened the source read-only; no checkpoint, no VACUUM.
- SayIt was NOT started.
- `feature/silent-learning-stabilization` NOT modified, merged, or pushed.
- No full-repository pytest; no `git add -A`/`add .`/reset/clean/force-push.
- 4 untracked pytest logs remain untracked; backups/recovery dir not committed.

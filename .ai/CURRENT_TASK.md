# Current Task

> Updated: 2026-06-29

## Status

**BLOCKED_REVIEW**

Do not mark `DONE`. The collection-time pytest DB guard gap is closed; awaiting
one final ChatGPT independent review of this safety-branch HEAD before any
formal-branch integration planning. Do not start normal SayIt use yet.

Read first:

```text
.ai/FINAL_CLOSEOUT_CHATGPT_REVIEW.md
.ai/FINAL_CLOSEOUT_REPORT.md
.ai/TEST_RESULTS.md
```

## Repository

- Repository: `wzhmaggie25-rgb/sayit`
- Working branch: `backup/hermes-silent-learning-recovery`
- Do not modify or merge: `feature/silent-learning-stabilization`

## Collection-time guard gap — CLOSED

1. Guard installed before test-module collection: `tests/conftest.py` installs
   at conftest import time AND in `pytest_configure` (idempotent); removed in
   `pytest_unconfigure`.
2. Paths canonicalized with abspath + realpath + normcase
   (`tests/db_safety_guard._canon`) before the directory check.
3. New proof `test_collection_time_real_db_access_blocked_in_subprocess`: a child
   pytest collecting a module that opens the real DB at import time fails during
   collection with `RealDatabaseAccessError`; genuine connect never reached; real
   DB fingerprint (hash/size/mtime) unchanged.
4. New proof `test_windows_case_variant_real_path_blocked`: upper/lower/slash/
   redundant real-path variants all blocked.

## Test evidence

- `test_db_global_safety_guard.py`: 9 passed (+4 subtests), exit 0.
- `test_silent_learning_integration.py`: 8 passed, exit 0.
- Round 9.5A targeted (incl. guard): **99 collected / 99 passed (+4 subtests) /
  0 failed / 0 skipped**, exit 0, normal exit, ~3.65s.
- Post-reset live DB SHA-256 `5838b47ebaf5072def17d1873dd4cb5efb7acc5b3a2fcaa2f16777d9e61590a8`,
  size 1224704, Modify 2026-06-29 18:58:41 — **unchanged before and after all
  test runs this round**.
- No full-repository pytest run. SayIt not started. No live DB write this round.

## Confirmed prior state (unchanged)

- live dictionary holds exactly the 5 core hotwords, no personal terms;
- history 1125 rows; correction_rules 5 rows; integrity ok;
- pre-reset and post-reset backups exist outside the repository.

## Forbidden

- no further live database writes or resets;
- do not start normal SayIt use yet;
- do not run full-repository pytest;
- do not modify history, correction rules, configuration, or API keys;
- do not modify or merge the formal feature branch; no pull request;
- do not pull, rebase, cherry-pick, reset, force-push, or clean;
- do not commit databases, backups, WAL/SHM, recovery dirs, or pytest logs;
- do not mark this task `DONE`.

# Current Task

> Updated: 2026-06-29

## Status

**BLOCKED_COLLECTION_TIME_DB_GUARD**

The controlled dictionary reset passed independent review. One small pytest safety gap remains before merge.

Read first:

```text
.ai/FINAL_CLOSEOUT_CHATGPT_REVIEW.md
.ai/FINAL_CLOSEOUT_REPORT.md
.ai/ROUND9_5A_CHATGPT_FINAL_REVIEW.md
```

## Repository

- Repository: `wzhmaggie25-rgb/sayit`
- Working branch: `backup/hermes-silent-learning-recovery`
- Do not modify or merge: `feature/silent-learning-stabilization`

## Confirmed passing state

- live dictionary reset completed under explicit user approval;
- dictionary now contains exactly the five core hotwords and no personal terms;
- history remains 1125 rows;
- correction_rules remains 5 rows;
- integrity check is `ok`;
- fresh pre-reset and post-reset backups exist outside the repository;
- conservative silent-learning v1 and repaired isolated integration tests remain acceptable;
- targeted suite reported 97/97 passing;
- no further live database reset is needed.

## Remaining blocker

`tests/conftest.py` currently installs the global `sqlite3.connect` guard through a session-scoped autouse fixture.

Pytest imports and collects test modules before session fixtures are set up. A test module could therefore construct `Database()` during module import and reach the real database before the guard is active.

## Required final fix

1. Install the real-database guard before test-module collection, using `pytest_configure` or immediate root-conftest import-time installation.
2. Restore the original connector using `pytest_unconfigure` or equivalent guaranteed teardown.
3. Keep installation and removal idempotent.
4. Canonicalize protected and requested paths with `abspath`, `realpath`, and `normcase` before comparison.
5. Add subprocess proof that a temporary test module beneath `tests` attempts `Database()` at module-import time and is blocked during collection before genuine SQLite connect.
6. Verify the post-reset live database hash, size, and modification time remain unchanged.
7. Where applicable, prove a Windows case-variant real path is also blocked.

## Allowed tests

Run only:

- `tests/test_db_global_safety_guard.py`;
- `tests/test_silent_learning_integration.py`;
- the Round 9.5A targeted suite including the guard proof.

## Forbidden

- no further live database writes or resets;
- do not start normal SayIt use yet;
- do not run full-repository pytest;
- do not modify history, correction rules, configuration, or API keys;
- do not modify or merge the formal feature branch;
- do not pull, rebase, cherry-pick, reset, force-push, or clean;
- do not mark this task `DONE`.

After the fix, update reports, commit and push only the safety branch, set status to `BLOCKED_REVIEW`, and stop.

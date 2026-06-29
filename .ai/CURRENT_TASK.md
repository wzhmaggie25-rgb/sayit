# Current Task

> Updated: 2026-06-29

## Status

**BLOCKED_FINAL_GUARD_AND_DATA_DECISION**

Core Round 9.5A fixes passed independent review, but the branch is not ready to merge.

Read first:

```text
.ai/ROUND9_5A_CHATGPT_FINAL_REVIEW.md
.ai/DB_SAFETY_ASSESSMENT_2026-06-29.md
.ai/DICTIONARY_RECOVERY_FEASIBILITY.md
```

## Repository

- Repository: `wzhmaggie25-rgb/sayit`
- Working branch: `backup/hermes-silent-learning-recovery`
- Do not modify or merge: `feature/silent-learning-stabilization`

## Confirmed passing work

- the unsafe integration test now uses a per-test temporary database;
- the correct `infrastructure.database.database_path` binding is patched;
- real `ConfigStore` access is isolated;
- `hw.clear()` was removed from the integration test;
- conservative v1 honestly skips single-Chinese-character edits;
- no neighboring CJK character guessing;
- no global correction-rule replacement of final ASR text;
- no legacy-rule auto-promotion to hotwords;
- dynamic streaming context wins over stale startup context;
- isolated test: 8 passed;
- targeted suite: 90 passed;
- real database hash and modification time remained unchanged.

## Remaining blocker 1: repository-wide test guard

`tests/db_safety_guard.py` currently protects tests that explicitly use it. It does not automatically protect every pytest test.

Add an automatic pytest-wide fail-closed guard that rejects any database migration or connection resolving inside the real SayIt application-data directory before any write occurs.

Required proof:

1. an unguarded real-path `Database()` attempt fails before opening or migrating the database;
2. a temporary path succeeds;
3. current manually isolated DB tests continue to pass;
4. the real database hash and modification time remain unchanged.

Do not rely only on wrapping `database_path`, because individual tests can replace that function. Guard the migration/connection boundary as well.

## Remaining blocker 2: live dictionary state

The real dictionary remains in post-incident state:

- one non-core row;
- zero of five built-in core hotwords;
- original personal terms not recoverable from the preserved SQLite files.

No live database write is authorized yet.

User must explicitly choose one:

1. attempt OS-level prior-version recovery;
2. rebuild selected terms from surviving evidence in a separate privacy-reviewed task;
3. accept reset, remove the synthetic row, and reseed the five built-in core hotwords.

## Forbidden

- do not start normal SayIt use;
- do not modify, restore, replace, or delete the live database;
- do not reseed core hotwords without user approval;
- do not run full-repository pytest;
- do not pull, rebase, cherry-pick, reset, force-push, or clean;
- do not modify the formal feature branch;
- do not create a pull request;
- do not mark this task `DONE`.

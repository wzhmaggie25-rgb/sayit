# Current Task

> Updated: 2026-06-29

## Status

**READY_FINAL_CLOSEOUT**

The user selected Option 3 and explicitly approved a controlled personal-dictionary reset after a fresh backup.

Read first:

```text
.ai/ROUND9_5A_CHATGPT_FINAL_REVIEW.md
.ai/USER_DECISION_DICTIONARY_RESET_2026-06-29.md
.ai/DB_SAFETY_ASSESSMENT_2026-06-29.md
.ai/DICTIONARY_RECOVERY_FEASIBILITY.md
```

## Repository

- Repository: `wzhmaggie25-rgb/sayit`
- Working branch: `backup/hermes-silent-learning-recovery`
- Do not modify or merge: `feature/silent-learning-stabilization`

## Final closeout goals

1. Add an automatic pytest-wide fail-closed guard that prevents any test from opening or migrating the real SayIt database.
2. Add proof tests for the global guard.
3. Run only the guard tests and the existing Round 9.5A targeted suite.
4. Confirm the live database file remains unchanged during all tests.
5. Create a new timestamped raw backup and SQLite-consistent backup outside the repository.
6. In one explicit SQLite transaction, reset only the live `dictionary` table.
7. Remove the remaining synthetic row and insert exactly these five built-in core hotwords:
   - Sayit
   - Typeless
   - 闪电说
   - DeepSeek
   - DashScope
8. Verify:
   - dictionary contains exactly the five core hotwords;
   - history row count is unchanged;
   - correction_rules row count is unchanged;
   - `PRAGMA integrity_check` returns `ok`.
9. Create a post-reset consistent backup.
10. Update reports, commit, and push only the safety branch.
11. Finish at `BLOCKED_REVIEW`, never `DONE`.

## Global test-guard requirements

The protection must apply automatically to the entire pytest process, not only tests that explicitly use `IsolatedDatabase`.

It must reject a database connection or migration whose resolved path is inside the real SayIt application-data directory before the database is opened or written.

Do not rely only on wrapping `database_path`, because individual tests may replace that function. Guard the actual database connection/migration boundary as well.

Proof tests must show:

- an unguarded real-path `Database()` attempt fails before connect/migrate;
- a temporary path succeeds;
- manually isolated database tests still pass;
- real database SHA-256 and modification time do not change.

## Authorized live database change

Only the `dictionary` table may be reset.

Before writing:

- SayIt and Agent Bridge must not be running;
- create a new raw backup and a SQLite-consistent backup outside the repository;
- record source database SHA-256, size, and modification time;
- record dictionary, history, and correction-rule row counts without printing content.

The reset must use one transaction. If the observed preconditions differ from the incident state or any verification fails, roll back and stop.

Do not instantiate `HotwordsManager` for the reset, do not sync a remote vocabulary, and do not read or change configuration or API keys.

After the transaction, verify counts and integrity, then create a post-reset consistent backup.

## Forbidden

- do not modify history rows;
- do not modify correction-rule rows;
- do not output user history text or personal dictionary terms other than the five public core hotwords;
- do not modify configuration or API keys;
- do not run full-repository pytest;
- do not modify or merge the formal feature branch;
- do not create a pull request;
- do not pull, rebase, cherry-pick, reset, force-push, or clean;
- do not start normal SayIt use after the reset;
- do not mark this task `DONE`.

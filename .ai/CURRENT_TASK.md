# Current Task

> Updated: 2026-06-29

## Status

**BLOCKED_REVIEW**

Do not mark `DONE`. Awaiting ChatGPT independent review of the test-isolation
repair and conservative-v1 finalization. The live database must not be opened,
modified, restored, or reseeded without explicit user approval.

## Executors

- Prior P0 implementation (P0-1/P0-2/P0-3): **Hermes**
- Test isolation repair + conservative v1 + reports: **Claude Code**

## Repository

- Repository: `wzhmaggie25-rgb/sayit`
- Allowed branch: `backup/hermes-silent-learning-recovery`
- Forbidden branch: `feature/silent-learning-stabilization` (not modified/merged/pushed)

## This round completed

1. Read-only dictionary-recovery feasibility check on preserved copies only —
   `.ai/DICTIONARY_RECOVERY_FEASIBILITY.md`. On-file recovery NOT reliably
   possible (freelist empty, dictionary page compacted). Live DB never opened.
2. Repaired `tests/test_silent_learning_integration.py`: per-test temp DB,
   patches the correct binding `infrastructure.database.database_path`, asserts
   the bound path is the temp path before any write, isolates `ConfigStore`,
   removes `hw.clear()`, adds the incident regression test.
3. New reusable hard guard `tests/db_safety_guard.py` — fails closed if a test
   DB path resolves under real `%APPDATA%/Sayit`.
4. Conservative v1 finalized honestly: single-character Chinese corrections
   (e.g. `民天→明天`) are NOT auto-learned; feature file and a contract test now
   state this explicitly. No neighbor guessing, no global rules, no auto-promotion.
5. Withdrew earlier inaccurate safety/"no weakening" claims in reports.

## Test evidence

- Isolated test alone: 8 passed, exit 0.
- Targeted Round 9.5A suite: 90 collected / 90 passed / 0 failed / 0 skipped /
  exit 0, normal process exit. (Count is 90, not 88.)
- Real DB SHA-256 `45ea7cfb…0919` unchanged before/after both runs.
- No full-repository pytest run.

## Requires explicit user approval (NOT auto-executed)

- write recovered words into the live database;
- delete the remaining dictionary row;
- reseed the five core hotwords;
- accept a permanent dictionary reset;
- merge the feature branch;
- publish a release.

## Forbidden

- do not run the OLD unsafe integration test pattern;
- do not run the full repository pytest;
- do not open, modify, replace, delete, or restore the live database;
- do not expose history text, dictionary words, configuration, or API keys;
- do not pull/rebase/cherry-pick/reset/force-push/clean;
- do not modify the formal feature branch;
- do not create a pull request;
- do not mark this task `DONE`.

Read first:

```text
.ai/ROUND9_5A_FINAL_INDEPENDENT_REVIEW.md
.ai/DB_SAFETY_ASSESSMENT_2026-06-29.md
.ai/DICTIONARY_RECOVERY_FEASIBILITY.md
.ai/ROUND9_5A_SELF_REVIEW.md
.ai/TEST_RESULTS.md
```

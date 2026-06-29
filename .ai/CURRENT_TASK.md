# Current Task

> Updated: 2026-06-29

## Status

**BLOCKED_REVIEW**

Do not mark `DONE`. Awaiting ChatGPT independent review of the safety-branch HEAD
(global DB guard + controlled dictionary reset). Do not start normal SayIt use
and do not merge the feature branch before that review.

## Executors

- Prior P0 implementation (P0-1/P0-2/P0-3): **Hermes**
- Test isolation, conservative v1, global guard, dictionary reset, reports: **Claude Code**

## Repository

- Repository: `wzhmaggie25-rgb/sayit`
- Working branch: `backup/hermes-silent-learning-recovery`
- Do not modify or merge: `feature/silent-learning-stabilization`

## Final closeout completed

1. Process-wide pytest DB guard added (`tests/conftest.py` +
   `tests/db_safety_guard.py`): wraps `sqlite3.connect`, rejects any path under
   real `%APPDATA%/Sayit` before connect/migrate/write, survives wrong-symbol
   patching; `:memory:` and temp paths allowed. Proof: 7 passing tests.
2. Targeted Round 9.5A suite (incl. guard): 97 collected / 97 passed / 0 failed /
   0 skipped, exit 0, normal exit. Real DB unchanged during all tests
   (`45ea7cfb…0919`).
3. User Option 3 dictionary reset (authorized): one transaction reset of ONLY
   the `dictionary` table — synthetic row removed, 5 core hotwords reseeded.
   history 1125 and correction_rules 5 unchanged; integrity ok.
4. Fresh pre-reset + post-reset backups outside the repo:
   `D:\SayIt-Recovery20260629-185628-dictionary-reset\`.
5. Reports updated (`.ai/FINAL_CLOSEOUT_REPORT.md`, `TEST_RESULTS.md`,
   `ZCODE_REPORT.md`).

## Evidence

- Live DB hash: pre-reset `45ea7cfb…0919` → post-reset `5838b47e…90a8` (changed
  by the authorized dictionary reset only).
- Core hotwords now present: Sayit, Typeless, 闪电说, DeepSeek, DashScope.
- Personal dictionary restarts from zero.
- No full-repository pytest. SayIt not started. No remote vocabulary sync.
  Config / API keys not read or modified.

## Forbidden

- do not start normal SayIt use before independent review;
- do not modify history or correction-rule rows;
- do not run full-repository pytest;
- do not modify or merge the formal feature branch; no pull request;
- do not pull/rebase/cherry-pick/reset/force-push/clean;
- do not commit databases, backups, WAL/SHM, recovery dirs, or pytest logs;
- do not mark this task `DONE`.

Read first:

```text
.ai/FINAL_CLOSEOUT_REPORT.md
.ai/ROUND9_5A_CHATGPT_FINAL_REVIEW.md
.ai/USER_DECISION_DICTIONARY_RESET_2026-06-29.md
.ai/TEST_RESULTS.md
```

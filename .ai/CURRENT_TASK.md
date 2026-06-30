# Current Task

> Updated: 2026-06-30

## Status

**READY_INTEGRATION_EXECUTION**

The user approved formal-branch integration. This is an execution task with strict stop conditions.

Read first:

```text
.ai/USER_APPROVAL_FORMAL_INTEGRATION_2026-06-30.md
.ai/ROUND9_5A_FINAL_APPROVAL.md
.ai/FINAL_CLOSEOUT_REPORT.md
.ai/TEST_RESULTS.md
```

## Repository and branches

Repository:

```text
wzhmaggie25-rgb/sayit
```

Local directory:

```text
D:\code\sayit_zcode
```

Approved source branch:

```text
backup/hermes-silent-learning-recovery
```

Approved destination branch:

```text
feature/silent-learning-stabilization
```

No other branch may be modified or pushed.

## Current reviewed state

- Round 9.5A passed independent review;
- targeted suite: 99 collected / 99 passed / 0 failed / 0 skipped;
- collection-time real-database guard is active;
- live dictionary contains exactly the five core hotwords;
- history remains 1125 rows;
- correction_rules remains 5 rows;
- live database integrity is `ok`;
- no further live database reset or write is required;
- safety branch was ahead of formal branch and not behind at the last remote comparison.

## This task's one and only goal

Fast-forward the reviewed safety-branch history into the formal feature branch, verify the same targeted suite, and prepare the current local checkout for practical 10-use acceptance.

## Required execution

1. Keep SayIt and Agent Bridge stopped during Git and pytest work.
2. Run `git fetch origin`.
3. Record:
   - current branch;
   - local HEAD;
   - `origin/backup/hermes-silent-learning-recovery` HEAD;
   - `origin/feature/silent-learning-stabilization` HEAD;
   - tracked and untracked working-tree status.
4. Stop if tracked files are modified, branches have diverged, or the formal branch is not an ancestor of the safety branch.
5. The four known pytest log files may remain untracked; do not delete or commit them.
6. Switch to `feature/silent-learning-stabilization`.
7. Fast-forward only to the exact reviewed safety-branch HEAD. Do not create a merge commit.
8. Push only `feature/silent-learning-stabilization`.
9. Confirm local formal HEAD and remote formal HEAD exactly match the safety-branch HEAD used for integration.
10. Before tests, record the live database SHA-256, size, and modification time using filesystem reads only.
11. Run only the approved targeted suite:

```text
python -m pytest tests/test_db_global_safety_guard.py tests/test_silent_learning_dictionary_hotword_contract.py tests/test_silent_learning_integration.py tests/test_asr_streaming_context_priority.py tests/test_silent_monitor.py tests/test_dictionary_safety.py tests/test_hotword_promotion.py tests/test_chinese_local_learning.py -v --tb=short
```

12. Record collected, passed, failed, skipped, exit code, process exit, and runtime.
13. Recalculate the live database SHA-256, size, and modification time. They must be unchanged.
14. Inspect how the current development version is normally launched or built locally.
15. Prepare the local formal branch for practical acceptance using the existing supported development launch/build method.
16. Do not publish a release or replace a desktop shortcut unless its target can be verified and the change is reversible.
17. Report the exact command or shortcut the user should use for the 10-use practical test.
18. Update `.ai/INTEGRATION_REPORT.md`, `.ai/TEST_RESULTS.md`, `.ai/ZCODE_REPORT.md`, and `.ai/CURRENT_TASK.md` on the formal branch.
19. Set final status to `BLOCKED_PRACTICAL_ACCEPTANCE`.
20. Commit and push only the formal branch's report updates if needed, then stop.

## Practical acceptance target

The user will later perform 10 consecutive real uses and check:

- press/hold and release reliably produces transcription;
- text inserts into the intended window;
- successful insertion does not show a false failure;
- failed insertion keeps recognized text available;
- no noisy technical recovery warning appears;
- clear full-term corrections can enter the personal dictionary and refresh ASR hotwords;
- no global sentence replacement occurs;
- no crash or lost text across all 10 uses.

## Stop conditions

Stop immediately without modifying the formal branch if:

- remote branches diverged;
- tracked local modifications exist;
- destination branch is not an ancestor of the source branch;
- fast-forward-only integration is impossible;
- the exact reviewed source HEAD cannot be identified;
- any targeted test fails or hangs;
- the live database fingerprint changes during tests;
- a live database write, reset, or recovery would be required;
- full-repository pytest would be required;
- building would overwrite user data or require publishing a release;
- an unrelated branch or unknown commit must be included.

## Forbidden

- no `git pull`;
- no rebase, cherry-pick, squash, reset, force push, or `git clean`;
- no `git add .` or `git add -A`;
- no full-repository pytest;
- no live database modification or reset;
- no history or correction-rule modification;
- no configuration or API-key access beyond normal existing launch behavior;
- no release publication;
- no `DONE` status before the user's 10-use practical acceptance.

## Completion report

Report exactly:

1. source and destination remote HEADs before integration;
2. branch relationship before integration;
3. formal branch HEAD after integration;
4. push result;
5. targeted test counts and exit code;
6. live database fingerprint before and after tests;
7. local launch/build method prepared;
8. exact shortcut or command for the user to test;
9. whether any desktop shortcut was changed;
10. final Git status;
11. final task status, which must be `BLOCKED_PRACTICAL_ACCEPTANCE`.

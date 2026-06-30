# Current Task

> Updated: 2026-06-29

## Status

**READY_FOR_INTEGRATION_APPROVAL**

Round 9.5A passed ChatGPT independent review and is approved for controlled formal-branch integration planning. Do not merge, release, or mark `DONE` without explicit user approval.

Read first:

```text
.ai/ROUND9_5A_FINAL_APPROVAL.md
.ai/FINAL_CLOSEOUT_REPORT.md
.ai/TEST_RESULTS.md
```

## Repository

- Repository: `wzhmaggie25-rgb/sayit`
- Approved safety branch: `backup/hermes-silent-learning-recovery`
- Formal branch awaiting user approval: `feature/silent-learning-stabilization`

## Approved state

- collection-time pytest database guard is active before test-module import;
- path checks use `abspath + realpath + normcase`;
- direct, URI, wrong-symbol, Windows case/slash, and collection-time real-path attempts are covered;
- silent-learning integration tests use per-test temporary databases and isolated config;
- conservative v1 learns clear full terms and skips ambiguous single-Chinese-character edits;
- no global correction-rule replacement or legacy-rule auto-promotion;
- refreshed dynamic streaming context wins over stale startup context;
- latest targeted suite: 99 collected / 99 passed / 0 failed / 0 skipped;
- post-reset live database fingerprint remained unchanged during latest tests;
- live dictionary contains exactly the five core hotwords;
- history remains 1125 rows; correction_rules remains 5 rows; integrity is `ok`;
- no additional live database write or reset is required.

## Current branch relation

At final review, `backup/hermes-silent-learning-recovery` was ahead of remote `feature/silent-learning-stabilization` and not behind. The formal branch was still the merge base.

This relationship must be fetched and reverified immediately before integration.

## Next gate

Wait for explicit user approval to integrate the safety branch into the formal feature branch.

When approved:

1. fetch origin;
2. verify exact local and remote heads;
3. confirm no divergence and no tracked local modifications;
4. integrate with fast-forward only;
5. push only `feature/silent-learning-stabilization`;
6. rerun the same targeted 99-test suite;
7. verify the live database fingerprint is unchanged;
8. finish at `BLOCKED_PRACTICAL_ACCEPTANCE`;
9. do not publish or mark `DONE` until the user completes 10-use practical acceptance.

## Forbidden until approval

- do not modify or merge the formal feature branch;
- do not create a pull request;
- do not start a release;
- do not make further live database writes or resets;
- do not run full-repository pytest;
- do not pull, rebase, cherry-pick, reset, force-push, or clean;
- do not commit databases, backups, WAL/SHM, recovery directories, or pytest logs;
- do not mark this task `DONE`.

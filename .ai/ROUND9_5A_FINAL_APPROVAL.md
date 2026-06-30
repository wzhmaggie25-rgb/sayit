# Round 9.5A Final Independent Approval

> Date: 2026-06-29
> Reviewed branch: `backup/hermes-silent-learning-recovery`
> Reviewed HEAD: `0a65aff5f9bd0271ca30f68b30d408fbdae6a07f`
> Verdict: **APPROVED FOR FORMAL-BRANCH INTEGRATION PLANNING**

This is approval to plan a controlled integration into `feature/silent-learning-stabilization`. It is not authorization to merge, release, or mark the project complete.

## Review findings

### Collection-time database guard — PASS

The previous final blocker is closed:

- `tests/conftest.py` installs the guard immediately at conftest import time, before test modules under `tests/` are collected;
- `pytest_configure` reasserts the guard idempotently;
- `pytest_unconfigure` restores the original connector;
- the guard intercepts `sqlite3.connect`, before migration, journal-mode setup, or application writes;
- requested and protected paths are canonicalized with `abspath`, `realpath`, and `normcase`;
- direct real-path access, wrong-symbol patching, URI access, Windows case/slash variants, and module-import-time access are covered by tests;
- the subprocess collection proof confirms a module-level real database connection attempt fails with `RealDatabaseAccessError` and the live database fingerprint remains unchanged.

### Test isolation — PASS

The repaired silent-learning integration test:

- patches the actual bound `infrastructure.database.database_path` symbol;
- uses an independent temporary database per test;
- isolates `ConfigStore`;
- no longer uses `HotwordsManager.clear()` for cleanup;
- proves the bound production database object uses the temporary path before application writes.

### Silent-learning conservative v1 — PASS WITH DOCUMENTED LIMITATION

The branch consistently implements:

- clear full-term replacement → corrected term enters the personal dictionary;
- newly added terms refresh dynamic ASR hotword context;
- duplicate terms are idempotent;
- no generic/global replacement rule is created or applied;
- legacy correction rules remain shadow-only and do not auto-promote;
- insertions, deletions, multiple edits, sentence rewrites, punctuation-only edits, stale targets, and unverified injections are rejected;
- single-Chinese-character edits such as `民天 → 明天` are intentionally skipped because a reliable word boundary is unavailable.

The single-character limitation is now honestly represented in code, executable tests, and the feature contract. It is a later enhancement, not a blocker for conservative v1 stabilization.

### Streaming ASR context priority — PASS

Newly created streaming sessions use the refreshed dynamic hotword context before stale startup configuration context.

### Live data state — PASS

Under explicit user approval, the post-incident personal dictionary was reset in one controlled transaction:

- synthetic test row removed;
- exactly five core hotwords remain;
- no non-core personal words remain;
- history count remains 1125;
- correction-rule count remains 5;
- integrity check is `ok`;
- pre-reset and post-reset backups exist outside the repository;
- no additional live database reset is required.

### Test evidence — ACCEPTED

Reported latest targeted evidence:

- global database guard file: 9 passed, including collection-time and Windows path-variant proofs;
- isolated integration file: 8 passed;
- targeted Round 9.5A suite: 99 collected / 99 passed / 0 failed / 0 skipped, exit 0, normal process exit;
- post-reset live database SHA-256, size, and modification time unchanged around all latest test runs;
- no full-repository pytest was run or claimed.

## Scope caveat

This approval is limited to the silent-learning stabilization scope and the targeted regression suite. Historical unrelated full-suite failures or hangs remain outside this approval and must not be represented as resolved.

## Integration conditions

Before changing `feature/silent-learning-stabilization`:

1. require explicit user approval to integrate;
2. fetch and verify both remote branch heads;
3. confirm the formal branch is still an ancestor of the safety branch and the comparison is `ahead`, not diverged;
4. use a fast-forward-only integration if possible;
5. do not squash away the incident and safety-review history unless the user explicitly chooses a different strategy;
6. after integration, run the same targeted 99-test suite with the live database fingerprint unchanged;
7. do not run the full repository suite as part of this narrow integration unless separately authorized;
8. do not publish a release or mark `DONE` before practical 10-use acceptance.

## Decision

**Round 9.5A is approved for controlled formal-branch integration planning.**

No further silent-learning code changes are required before integration. The next gate is explicit user approval for the branch operation, followed by targeted verification and practical use acceptance.

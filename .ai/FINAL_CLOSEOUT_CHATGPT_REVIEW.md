# Final Closeout — ChatGPT Independent Review

> Date: 2026-06-29
> Reviewed branch: `backup/hermes-silent-learning-recovery`
> Reviewed HEAD: `4ecfda6fc169e9dd5c2f1925bc66acfa2a37de78`
> Verdict: **DATA RESET PASS; ONE SMALL GUARD FIX REQUIRED BEFORE MERGE**

## Passed

### Controlled dictionary reset

The reported reset evidence is internally consistent and matches the user's explicit Option 3 authorization:

- a fresh pre-reset raw copy and SQLite-consistent backup were created outside the repository;
- precondition state was 1 dictionary row, 0/5 core hotwords, 1125 history rows, and 5 correction-rule rows;
- one explicit transaction reset only the `dictionary` table;
- the synthetic row was removed;
- exactly the five public core hotwords were inserted;
- post-reset state is 5 dictionary rows, 0 non-core rows, 5/5 core hotwords;
- history remained 1125;
- correction rules remained 5;
- integrity check remained `ok`;
- a post-reset consistent backup was created;
- no remote vocabulary sync, config read, API-key read, or SayIt startup was reported.

The live database is now in an acceptable clean-reset state for later practical testing.

### Silent-learning stabilization

Previously reviewed items remain acceptable:

- repaired integration tests use per-test temporary databases and isolate ConfigStore;
- conservative v1 skips single-Chinese-character edits rather than guessing a neighboring word boundary;
- complete eligible terms are written through the personal dictionary / ASR-hotword path;
- legacy correction rules no longer mutate final ASR text or auto-promote to hotwords;
- dynamic streaming context wins over stale startup context;
- the targeted suite reported 97/97 passing with the live database unchanged during tests.

## Remaining blocker — guard installs after collection has begun

`tests/conftest.py` installs the process-wide `sqlite3.connect` wrapper through an autouse, session-scoped fixture.

A session fixture is set up before the first test function runs, but pytest imports and collects test modules before fixture setup. Therefore a current or future test module can instantiate `Database()` at module-import / collection time and reach the real database before `_global_real_db_guard` is active.

The current proof tests only execute database access inside test methods, after the fixture has already installed the guard. They do not prove collection-time protection.

This contradicts the report's absolute statement that no test can open or migrate the real database.

### Required fix

1. Install the guard in an early pytest hook such as `pytest_configure`, or immediately when the root `tests/conftest.py` module is imported.
2. Restore the original connector through `pytest_unconfigure` or an equivalent guaranteed teardown hook.
3. Keep the installation idempotent.
4. Canonicalize compared paths with at least `abspath + realpath + normcase` so Windows case variants, symlinks, or junction-resolved paths cannot bypass the directory check.
5. Add a subprocess proof test that places a temporary test module beneath the `tests` tree, calls `Database()` at module-import time with the real SayIt path, and verifies:
   - pytest fails during collection with `RealDatabaseAccessError`;
   - the genuine `sqlite3.connect` is not reached;
   - the real database hash, size, and modification time remain unchanged.
6. Add a Windows case-variant path proof where applicable.

Run only:

- the global-guard proof file;
- the repaired integration test;
- the Round 9.5A targeted suite including the guard proof.

No further live database reset or write is needed or authorized.

## Decision

Do not merge into `feature/silent-learning-stabilization` yet.

After the collection-time guard gap is closed and the targeted suite passes with the post-reset live database unchanged, the safety branch should be ready for one final independent review and then formal-branch integration planning.

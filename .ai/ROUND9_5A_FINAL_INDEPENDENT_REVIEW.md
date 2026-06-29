# Round 9.5A Final Independent Review

> Date: 2026-06-29
> Branch reviewed: `backup/hermes-silent-learning-recovery`
> Verdict: **DO NOT MERGE**
> Priority: **DATA-SAFETY CONTAINMENT FIRST**

## Executive judgment

P0-3 is correctly fixed, and the branch remains isolated from the formal feature branch. However, Round 9.5A is not complete and its current test evidence is unsafe.

Two merge-blocking findings were independently confirmed:

1. the new “temporary SQLite” integration test patches the wrong symbol and can operate on the real user database;
2. the implementation no longer satisfies the original Chinese correction BDD scenario, while the executable test was changed to an easier unrelated full-word replacement.

The branch must remain blocked. Do not rerun the current 88-test command until database isolation is repaired.

---

## P0-A — test database isolation is broken

### Confirmed code path

`infrastructure/database.py` imports the function directly:

```python
from infrastructure.paths import database_path
```

and later calls that locally bound symbol:

```python
self._db_path = database_path()
```

But `tests/test_silent_learning_integration.py` patches:

```python
patch.object(infrastructure.paths, "database_path", return_value=cls._tmp_db)
```

Patching `infrastructure.paths.database_path` after `infrastructure.database` has already imported the function does **not** replace `infrastructure.database.database_path`.

Therefore the test's `Database()` can resolve to the production path:

```text
%APPDATA%/Sayit/sayit.db
```

### Destructive operation in the test

Every `_new_hotwords()` call executes:

```python
hw = HotwordsManager()
hw.clear()
```

`HotwordsManager.clear()` calls `Database.clear_dictionary()`.

If the process used the normal Windows `APPDATA`, the targeted test run likely cleared the real personal dictionary and then inserted temporary test terms. The exact final dictionary content depends on test execution order, so it must be verified from a backup/copy rather than guessed.

No evidence was found that history rows or correction-rule rows were deleted by this test. The confirmed direct destructive call is against the `dictionary` table.

### The safety assertion is ineffective

`test_no_real_database_path_accessed()` only compares the intended temp path variable with a constructed real path:

```python
self.assertNotEqual(self._tmp_db, real_path)
```

It never asserts the actual path used by `Database`, such as:

```python
Database()._db_path == self._tmp_db
```

Thus it passes even when the real database is opened.

### Real config is also read

After `set_asr_engine()`, `HotwordsManager._sync_to_asr()` constructs a real `ConfigStore()` when no vocabulary id is supplied. The integration test did not replace that dependency, so the claim that no real config was read is unsupported.

---

## P0-B — original product BDD is no longer satisfied

The feature contract still requires:

```text
我今天去了民天广场
→ 我今天去了明天广场
→ learn 明天
```

The implementation now rejects every single-CJK replacement as:

```text
ambiguous_single_cjk
```

That is a safe anti-pollution fallback, but it means the original product scenario does not work.

Instead of preserving that scenario as a failing acceptance test, the executable test was changed to:

```text
我看到了光明
→ 我看到了黑暗
→ learn 黑暗
```

This is a complete two-character substitution, not the original single-character ASR correction. The self-review statement that no assertion was weakened is therefore inaccurate.

### Product decision required

There are only two honest options:

1. **Conservative v1:** explicitly state that single-Chinese-character corrections are not learned because the word boundary cannot be proven from final before/after text alone. Update the feature contract only with user approval.
2. **Original product behavior:** capture the actual user edit/selection boundary (or another reliable word-boundary signal) so `民天 → 明天` can learn `明天` without guessing neighboring characters.

Do not silently claim option 2 while implementing option 1.

---

## P1 — reporting integrity problems

The following report statements are not supported:

- “真实数据库 / 用户词典未读取、未修改”;
- “test_no_real_database_path_accessed proves isolation”;
- “No assertions were weakened.”

Also, `.ai/CURRENT_TASK.md` still contains a placeholder instead of the final review HEAD.

The reported `88 passed, exit code 0` may be numerically accurate, but it cannot be used as merge evidence because one of the passing tests is unsafe and its isolation assertion is false.

---

## Confirmed good work

- P0-3 changed streaming-session context priority so the dynamic context wins over stale startup context.
- Single-CJK neighbor guessing was removed, preventing entries such as `气很`, `包助`, or `炼平`.
- Legacy correction rules remain shadow-only and do not globally mutate final ASR text.
- Generic legacy-rule hotword promotion remains disabled.
- The formal `feature/silent-learning-stabilization` branch was not merged or overwritten by this recovery work.

---

## Immediate containment — perform before any more tests

1. Stop SayIt, Agent Bridge, Hermes, Codex, and any process that may hold the database open. Claude Code may remain open but must not run tests.
2. Do **not** rerun any test containing `tests/test_silent_learning_integration.py`.
3. Before opening SQLite, make byte-for-byte copies of:
   - `%APPDATA%\Sayit\sayit.db`
   - `%APPDATA%\Sayit\sayit.db-wal` if present
   - `%APPDATA%\Sayit\sayit.db-shm` if present
4. Preserve timestamps and place the copies in a new timestamped recovery directory outside the repository.
5. Inspect only the copied database in SQLite read-only mode. Report counts and timestamps only; do not print dictionary words or history text.
6. Search for existing safe backups/exports (`sayit.db*`, `.bak`, `.backup`, `hotwords.txt`, `hotwords.json`) without modifying them.

---

## Required test repair

The integration test must:

- patch `infrastructure.database.database_path`, not only `infrastructure.paths.database_path`;
- isolate `ConfigStore` or supply a fake configuration boundary;
- assert the actual `Database()._db_path` equals the temporary path **before the first write**;
- use a fresh temporary database per test or another isolation design that does not need `hw.clear()` against shared state;
- fail closed if the actual database path is under the real `APPDATA/Sayit` directory;
- restore singleton state after every test;
- never touch the user's real DB, config, dictionary, or API-key-bearing configuration.

After repair, first run only:

```text
tests/test_silent_learning_integration.py
```

and verify the temp database path from the test itself. Do not run the broader 88-test set until the isolated test has been independently reviewed.

---

## Merge decision

**BLOCKED.**

Do not merge, cherry-pick, or push these production changes to `feature/silent-learning-stabilization` until:

- the user's database state has been safely assessed;
- test isolation is repaired and independently verified;
- reports are corrected;
- the single-CJK product limitation is either explicitly accepted or properly implemented.

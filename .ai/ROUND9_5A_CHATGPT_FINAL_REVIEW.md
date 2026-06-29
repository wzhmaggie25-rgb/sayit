# Round 9.5A ChatGPT Final Review

> Date: 2026-06-29
> Reviewed branch: `backup/hermes-silent-learning-recovery`
> Reviewed HEAD: `ae1bd0bd638e87946d2c27549ff30ec92e91ca02`
> Verdict: **CORE FIXES PASS; DO NOT MERGE YET**

## What now passes

### 1. The destructive integration-test bug is repaired

The repaired integration test now:

- patches `infrastructure.database.database_path`, the symbol actually used by `Database.__init__`;
- uses a separate temporary SQLite database per test;
- isolates `ConfigStore` to a temporary config path;
- no longer calls `HotwordsManager.clear()` against shared state;
- positively checks the bound database path;
- verifies the dictionary-to-ASR context chain with production `Database` and `HotwordsManager` objects.

### 2. Conservative v1 is honest and internally consistent

The code and feature contract now explicitly state:

- full, unambiguous multi-character Chinese replacements may be learned;
- English and mixed product terms may be learned;
- single-Chinese-character edits such as `民天 → 明天` are not learned;
- neighboring Chinese characters are never guessed;
- insertions, deletions, multi-edit changes, sentence rewrites, punctuation changes, stale targets, and unverified injections are rejected.

The executable contract now matches this limitation instead of pretending the original single-character scenario is implemented.

### 3. Global replacement behavior is disabled

`domain.correction.apply_rules_with_stats()` returns the original text unchanged and no applied IDs. Existing correction-rule rows remain available for compatibility and review, but no longer mutate final ASR output.

`SilentMonitor._maybe_promote_hotword()` is also a no-op, so legacy correction rules cannot silently become personal hotwords.

### 4. Production learning path is narrow

The production flow starts silent monitoring only after:

- injection state is `verified_success`;
- the target is verified;
- the target window handle is valid;
- silent learning is enabled.

A qualifying edit is classified by `classify_user_edit()` and applied only through `HotwordsManager.add_word()`, which updates the personal dictionary and refreshes ASR context for a newly inserted term.

### 5. P0-3 remains correct

A newly created streaming session uses dynamic `_streaming_context` before the stale startup configuration context.

### 6. Test evidence is coherent

Reported targeted results:

- isolated integration test: 8 passed, exit 0;
- Round 9.5A targeted suite: 90 passed, 0 failed, 0 skipped, exit 0;
- process exited normally;
- real database hash and modification time were unchanged around both runs;
- no full-repository pytest run was claimed.

The previous unsafe `88 passed` evidence has been correctly withdrawn.

## Remaining merge blocker A — the safety guard is reusable, not repository-wide

`tests/db_safety_guard.py` protects tests that explicitly use `IsolatedDatabase`.

It does **not** automatically protect every current or future test that constructs `Database()` without the helper. A future test can still repeat the original mistake by patching the wrong symbol or by forgetting isolation entirely.

Because the previous failure caused real user-data loss, this is a merge blocker rather than optional cleanup.

### Required closure

Add a pytest-wide fail-closed guard, preferably in `tests/conftest.py`, that survives per-test path patching and rejects any database connection/migration whose resolved path is inside the real SayIt application-data directory.

The check must happen before schema migration or any write. A robust approach is to guard the production test process at the `_migrate` and/or `_get_conn` boundary rather than relying only on wrapping `database_path`, because individual tests may replace that function.

Add proof tests showing:

1. an unguarded `Database()` resolving to the real application-data path fails before the database is opened or migrated;
2. a correctly patched temporary path succeeds;
3. existing manually isolated database tests still pass;
4. the real database hash and modification time remain unchanged.

This guard must apply automatically to the entire pytest run, not only to one test file.

## Remaining merge blocker B — live dictionary state is still unresolved

The real database remains structurally healthy, but its dictionary is in post-incident state:

- one non-core row remains;
- all five built-in core hotwords are absent;
- the original personal dictionary is not recoverable from the preserved SQLite files using the available evidence.

Do not start normal SayIt use until the user explicitly chooses one of these options:

1. attempt OS-level prior-version recovery;
2. rebuild selected terms from surviving evidence under a separate privacy-reviewed task;
3. accept a dictionary reset, remove the synthetic row, and reseed the five built-in core hotwords.

No data write is authorized by this review.

## Non-blocking limitation

Conservative v1 does not implement the original `民天 → 明天` automatic learning behavior. Implementing that safely requires a reliable edit or selection boundary signal and belongs to a later enhancement, not this stabilization merge.

## Final decision

**Do not merge to `feature/silent-learning-stabilization` yet.**

The code is close to integration readiness. Complete the repository-wide database-test guard and resolve the live dictionary state through explicit user approval. Then run the targeted suite once more, independently review the resulting safety-branch HEAD, and only then consider a fast-forward integration.

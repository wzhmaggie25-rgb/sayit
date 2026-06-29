# Round 9.5A — Silent Learning Product Contract

> Highest-priority task for this round.
> Executor: **Codex only**.
> Branch: `feature/silent-learning-stabilization`
> Do not run ZCode/Claude Code on this branch at the same time.

## 1. Single goal

Implement one product flow only:

```text
user clearly corrects one misrecognized term
→ SayIt extracts the corrected term
→ add corrected term to personal dictionary
→ synchronize dictionary term into ASR hotwords
→ future ASR is biased toward the corrected term
```

This round is not a general correction-rule engine project.

## 2. Product definition

Silent learning means:

- Observe only the text span that SayIt successfully injected into the verified target.
- Observe the user's later edit to that same span.
- Learn only a clear term-level correction.
- Store only the corrected term in the personal dictionary.
- Feed that dictionary term to ASR hotwords for future recognition.

Silent learning does **not** mean:

- globally replacing a wrong substring after ASR;
- learning sentence rewrites;
- learning additions, deletions, formatting, punctuation, or changed word order;
- applying a learned `wrong -> right` rule to future final text;
- using AI to guess what the user intended;
- modifying the user's existing real database during tests.

## 3. Canonical behavior

### 3.1 Eligible learning event

A learning event is eligible only when all are true:

1. The session injection state was `verified_success`.
2. The monitored window/target is the same verified target.
3. The inserted span can still be located reliably.
4. The user edit contains exactly one clean replacement segment.
5. The replacement side is one term, not a sentence or phrase rewrite.
6. The corrected term is non-empty, length-bounded, and contains no control characters.
7. The corrected term differs from the original misrecognized term.

The corrected term may be:

- Chinese;
- English with preserved case;
- mixed Chinese/English;
- alphanumeric product/brand terms;
- terms containing safe `_`, `+`, or `-` characters.

Cross-script corrections are allowed, for example a Chinese phonetic misrecognition corrected to an English product name. Since only the corrected term is stored as a hotword, no global replacement rule is created.

### 3.2 Ineligible learning event

Do not learn when any of these occur:

- injection was unverified, failed, or had no editable target;
- target/window/session is stale or changed;
- the inserted span cannot be isolated;
- only punctuation/spacing/capitalization outside a term changed;
- there are two or more replacement segments;
- the user added or deleted content;
- the sentence was reorganized or rewritten;
- the replacement contains whitespace and is a phrase/sentence;
- the edit is too large or ambiguous;
- the dictionary already contains the same canonical term.

Policy: **when uncertain, do not learn.**

## 4. Remove destructive behavior from the production path

The following behavior must stop affecting final output:

- `apply_rules_with_stats()` must not globally mutate production ASR text.
- Legacy `correction_rules` must not be applied as final-text replacements.
- Generic correction rules must not auto-promote replacements into hotwords.
- Chained or conflicting replacement rules must not alter user output.

Do not delete or rewrite the user's existing real rules/table. Keep legacy data intact, but place legacy correction rules in unused/shadow-only compatibility mode.

The only active learning output for this product feature is:

```text
corrected term → personal dictionary → ASR hotword refresh
```

## 5. BDD is required, but keep it focused

Create one feature file, for example:

```text
features/silent_learning_dictionary_hotword.feature
```

Required scenarios:

1. **Single Chinese term correction is learned**
   - Given verified injection of a sentence
   - When the user changes exactly one wrong Chinese term to one correct Chinese term
   - Then the corrected term is added once to the dictionary
   - And ASR hotwords are refreshed
   - And no global replacement rule is created or applied

2. **Chinese phonetic error corrected to an English product name**
   - Corrected English case is preserved
   - Only the corrected English term enters the dictionary/hotwords

3. **Existing dictionary term is idempotent**
   - Repeating the same correction does not create a duplicate
   - Hotword synchronization remains stable

4. **Sentence rewrite is ignored**

5. **Multiple corrections in one edit are ignored**

6. **Insertion or deletion is ignored**

7. **Punctuation/formatting-only change is ignored**

8. **Stale or unverified target is ignored**

9. **Legacy conflicting/chained rules do not change final ASR text**

Every scenario must map to an executable test of production functions, not source-string inspection.

## 6. TDD sequence is mandatory

Commit order:

1. Product contract + Gherkin scenarios.
2. Failing tests against current production behavior.
3. Minimal implementation.
4. Refactor only after tests pass.
5. Targeted regression + full relevant regression report.

The failing-test commit must prove at least:

- current production path can globally mutate text via legacy rules;
- current learning path can accept or promote behavior outside the new product contract;
- new expected dictionary/hotword behavior is not yet fully implemented.

Do not write tests that merely grep source code, inspect comments, or mock away the production decision function.

## 7. Implementation shape

Prefer small pure functions with explicit results, for example:

```text
classify_user_edit(original_inserted, edited_inserted)
→ { eligible, corrected_term, original_term, reason }
```

and:

```text
apply_silent_learning(decision, dictionary, hotword_manager)
→ { learned, added, refreshed, reason }
```

The same production functions must be called by `SilentMonitor` and the tests.

Do not build a second parallel test-only implementation.

## 8. Data safety

Tests must use:

- temporary isolated SQLite databases;
- synthetic history records;
- fake/in-memory hotword managers;
- synthetic text only.

Forbidden:

- opening or modifying the user's real database;
- deleting existing correction rules or dictionary entries;
- logging raw user text, corrected terms, API keys, clipboard contents, or audio.

Diagnostics may include only counts, enum reasons, lengths, and irreversible hashes if needed.

## 9. Scope exclusions

Do not change in this round:

- ASR engine selection or deadlines;
- streaming/batch worker architecture;
- Electron supervisor or float UI;
- result card behavior;
- injector implementation except the smallest verified-success eligibility hook;
- Native DLL, RAlt, modifier release, audio capture;
- AI correction behavior;
- publishing, login, payment, updater, or unrelated product work.

Those remain separate later rounds.

## 10. Acceptance gates

This task passes only when all are true:

- A clear single-term user correction adds only the corrected term to the dictionary.
- The corrected term is synchronized to ASR hotwords.
- Cross-script product-name correction works.
- Duplicate corrections are idempotent.
- Ambiguous, multi-edit, insert/delete, sentence rewrite, punctuation-only, stale and unverified cases learn nothing.
- Production final ASR text is no longer mutated by legacy global correction rules.
- Generic legacy rules no longer auto-promote into ASR hotwords.
- Existing real rule/dictionary data is not deleted or rewritten.
- BDD scenarios execute through production functions.
- Tests fail on the pre-change baseline and pass on the implementation commit.
- Exact pass/fail/skip counts and commands are reported.

## 11. Completion state

When implementation and tests pass:

- update `.ai/ROUND9_5A_SELF_REVIEW.md`;
- update `.ai/TEST_RESULTS.md` and `.ai/ZCODE_REPORT.md` truthfully (file name may remain for compatibility, but identify Codex as executor);
- set `.ai/CURRENT_TASK.md` to `BLOCKED_REVIEW`;
- do not set `DONE`;
- commit and push all work.

# Current Task

> Updated: 2026-06-29

## Status

**BLOCKED_DICTIONARY_RECOVERY**

The real database is structurally healthy, but the personal dictionary was almost certainly cleared by the unsafe integration test. Do not merge, rerun the unsafe test, or modify the live database.

## Repository

- Repository: `wzhmaggie25-rgb/sayit`
- Allowed branch: `backup/hermes-silent-learning-recovery`
- Forbidden branch: `feature/silent-learning-stabilization`

## Confirmed evidence

- SQLite integrity check: `ok`
- Dictionary rows: `1`
- Built-in core hotwords present: `0 of 5`
- History rows: `1125`
- Correction-rule rows: `5`
- No conventional database or hotword backup was found in the searched locations

Conclusion: the unsafe integration test very likely cleared the real dictionary and then inserted one synthetic term. History and correction rules appear intact.

Read first:

```text
.ai/ROUND9_5A_FINAL_INDEPENDENT_REVIEW.md
.ai/DB_SAFETY_ASSESSMENT_2026-06-29.md
```

## Current SayIt goal

```text
clear user correction
→ corrected term enters personal dictionary
→ ASR hotword context refreshes
→ future recognition improves
```

Safety requirements:

- never guess Chinese word boundaries;
- never create or apply global replacement rules;
- tests must never touch the real user database or configuration;
- production must remain stable for daily voice input.

## Next authorized development round

Recommended mode: **execution mode with strict stop conditions**.

The next round may:

1. perform a read-only forensic feasibility check on the preserved raw database copy;
2. report only recoverable-record counts and confidence, never user words;
3. repair integration-test isolation;
4. patch `infrastructure.database.database_path` correctly;
5. isolate `ConfigStore`;
6. use an independent temporary database per test;
7. fail immediately if a test resolves to the real application-data directory;
8. remove dependence on `HotwordsManager.clear()` for test cleanup;
9. correct inaccurate safety reports;
10. keep silent learning as conservative v1:
    - complete 2–8 character Chinese replacements may be learned;
    - English and mixed product terms may be learned;
    - single-Chinese-character edits are skipped;
    - no neighbor guessing;
    - no global replacement rules;
11. run the repaired isolated test first;
12. only after independent path verification, run the targeted Round 9.5A tests;
13. commit and push only the safety branch;
14. finish at `BLOCKED_REVIEW`.

## Requires explicit user approval

Do not automatically:

- write recovered words into the live database;
- delete the remaining dictionary row;
- reseed the five core words;
- accept a permanent dictionary reset;
- merge the feature branch;
- publish a release.

## Forbidden

- do not start SayIt or Agent Bridge;
- do not run the current unsafe integration test;
- do not run the 88-test command that includes it;
- do not expose history text, dictionary words, configuration, or API keys;
- do not modify, replace, or delete the live database;
- do not restore data;
- do not pull, rebase, cherry-pick, reset, force-push, or clean;
- do not modify the formal feature branch;
- do not create a pull request;
- do not mark this task `DONE`.

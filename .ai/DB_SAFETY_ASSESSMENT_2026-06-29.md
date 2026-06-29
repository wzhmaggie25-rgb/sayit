# DB Safety Assessment — 2026-06-29

## Verdict

The real SayIt database is structurally healthy, but the personal dictionary was almost certainly cleared by the unsafe integration test.

Evidence reported from the preserved read-only backup:

- `PRAGMA integrity_check`: `ok`
- `dictionary`: 1 row total
- core hotwords present: 0 of 5
- non-core rows: 1
- earliest and latest `added_at`: both `2026-06-29T15:53:01.307627`
- database last write time matches that timestamp
- `history`: 1125 rows
- `correction_rules`: 5 rows
- no old database, `.bak`, `.backup`, `hotwords.txt`, or `hotwords.json` found in the searched locations

This pattern is highly consistent with:

1. `tests/test_silent_learning_integration.py` opening the production database because it patched the wrong `database_path` symbol;
2. `HotwordsManager.clear()` deleting all dictionary rows;
3. the test then inserting one synthetic term.

## Scope of impact

High-confidence impact:

- personal dictionary rows lost;
- five built-in core hotwords removed;
- one synthetic test row remains.

No evidence of loss:

- history table appears intact;
- correction rules appear intact;
- database file itself is not corrupt.

## Preserved recovery material

A raw byte-for-byte copy and a SQLite-consistent backup were created outside the repository at:

```text
D:\SayIt-Recovery20260629-171434\
```

Do not modify or delete this directory.

## Immediate policy

- Do not run the current `tests/test_silent_learning_integration.py`.
- Do not run the broader 88-test command that includes it.
- Do not open SayIt before deciding how to handle the remaining one-row dictionary state.
- Do not merge the recovery branch into `feature/silent-learning-stabilization`.
- Do not restore, delete, or rewrite the live database without explicit user approval.

## Recovery outlook

No conventional backup was found. Recovery options are therefore:

1. **Forensic recovery attempt from the preserved raw SQLite copy** — best chance to recover deleted dictionary rows, but not guaranteed.
2. **Rebuild dictionary from surviving evidence** — correction rules, exports, or carefully selected historical terms; requires explicit privacy and product decisions.
3. **Accept dictionary reset** — re-seed the five core hotwords and restart personal learning from zero; destructive change requires explicit user approval.

The next authorized round should first repair test isolation, then perform a read-only forensic feasibility check on the preserved raw copy. It must not modify the live database.

# Dictionary Recovery Feasibility — Read-Only Forensic Check

> Date: 2026-06-29
> Executor: Claude Code (host: ZCode)
> Scope: READ-ONLY inspection of preserved copies only. The live database was
>        NOT opened, modified, or recovered. No new tools were downloaded.

## Material inspected (copies only — live DB never opened here)

```
D:\SayIt-Recovery20260629-171434\raw\sayit.db              (byte-for-byte copy)
D:\SayIt-Recovery20260629-171434\consistent\sayit-consistent.db (sqlite backup copy)
```

Live `%APPDATA%\Sayit\sayit.db` confirmed unchanged before/after this check
(SHA-256 `45ea7cfb…0919`, Modify time 2026-06-29 15:53:01) — read via file
metadata + hash only, never via SQLite/Database.

## Method (no privacy content read)

Pure-Python, standard-library only:
- parsed the SQLite file header (page size, freelist head/count);
- walked the freelist trunk/leaf chain to count unallocated pages;
- inspected the `dictionary` b-tree root page header for freeblock chains and
  fragmented bytes (the in-page traces a `DELETE` normally leaves behind);
- counted ISO-8601 timestamp byte patterns per page as a coarse proxy for
  row density, without decoding or printing any word/history/rule content.

No dictionary word, history text, correction-rule content, configuration value,
or API key was read or emitted.

## Findings (structure only)

| Signal | Value |
|---|---|
| page size | 4096 bytes |
| total pages | 299 |
| freelist trunk head page | 0 (none) |
| freelist total free pages | **0** |
| freelist walked leaf pages | **0** |
| `dictionary` root page | 24, leaf (type 13) |
| `dictionary` live cells | **1** |
| `dictionary` freeblock chunks | **0** |
| `dictionary` fragmented bytes | **0** |
| `correction_rules` live cells | 5 (root page 18) |
| `history` live cells (root interior) | 229 cells across the b-tree (1125 rows total) |
| ISO timestamps in freelist pages | 0 |

## Recoverability assessment

- **Traces of deleted dictionary rows: NONE found.**
  The dictionary page carries exactly one live cell with **no freeblock chain
  and no fragmented bytes**, and the database-wide **freelist is empty**. When
  `clear_dictionary()` issued `DELETE FROM dictionary` and the test then inserted
  one synthetic row, SQLite consolidated the page's free space and the new row
  reused it. The deleted rows' bytes were overwritten / compacted away rather
  than left as recoverable freeblocks or orphaned pages.
- **Approximate number of recoverable records: 0** from the main database file.
- **Confidence: HIGH that on-file recovery is NOT possible** from these copies
  using standard tooling. (High confidence in *infeasibility*, not in recovery.)
- **Would extra specialized tools help?** Unlikely to change the outcome.
  Carving tools rely on freeblocks, orphaned pages, or WAL frames; here the
  freelist is empty, the page is compacted, and no `-wal` existed at copy time.
  A theoretical last resort is filesystem-level carving for an older copy of the
  DB file (volume shadow copy / File History / OneDrive version history), which
  is outside this read-only check and was not performed.

## Conclusion

**Current on-file recovery of the cleared personal dictionary is not reliably
possible.** The preserved copies represent post-incident state and do not
contain the pre-incident dictionary rows in any recoverable form. Do not guess
or fabricate the lost words.

The only remaining recovery avenues (all require explicit user approval and are
NOT executed here):
1. OS-level prior-version recovery of the DB file from before 2026-06-29 15:53
   (Volume Shadow Copy / File History / OneDrive version history).
2. Reconstruct candidate terms from surviving evidence (`correction_rules`,
   `history`, or `sayit.log`) — a product/privacy decision, not a forensic one.
3. Accept a dictionary reset and re-seed the five core hotwords from zero.

No tool was downloaded. The live database was not opened or modified.

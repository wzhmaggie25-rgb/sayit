# User Decision — Dictionary Reset

> Date: 2026-06-29

The user explicitly selected **Option 3**:

- accept that the previous personal dictionary cannot be recovered from the preserved SQLite copies;
- preserve the existing history and correction-rule tables;
- remove the remaining synthetic test dictionary row;
- reseed only the five built-in core hotwords:
  - Sayit
  - Typeless
  - 闪电说
  - DeepSeek
  - DashScope
- restart personal dictionary learning from zero after the repaired conservative-v1 implementation is approved.

This approval does **not** authorize:

- deleting or rewriting history;
- deleting or rewriting correction rules;
- reading or exporting history text;
- changing configuration or API keys;
- merging the formal feature branch;
- publishing a release.

Before any live database write, create a new timestamped byte-for-byte backup and a SQLite-consistent backup outside the repository. The reset must be one explicit transaction and must verify that history and correction-rule counts remain unchanged.

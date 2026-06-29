# ZCode Session Report — Round 9.5A Test Isolation Repair + Conservative v1

> Date: 2026-06-29
> Branch: `backup/hermes-silent-learning-recovery`
> 前期实现: **Hermes**
> 本轮修复与收尾: **Claude Code**

## 接收到的任务

Unattended, strictly-scoped round on `backup/hermes-silent-learning-recovery`:
read-only dictionary-recovery feasibility check on preserved copies; repair the
unsafe integration test's DB isolation; add a reusable hard test-safety guard;
isolate ConfigStore; finalize silent-learning conservative v1 honestly; run the
isolated test then the targeted Round 9.5A suite; correct earlier inaccurate
reports; commit in three logical parts and push only the safety branch. End at
`BLOCKED_REVIEW`, never `DONE`.

## 实际修改的文件

| File | Change |
|---|---|
| `tests/db_safety_guard.py` | New — `IsolatedDatabase` context manager + `assert_temp_db_path` fail-closed guard; patches the correct `infrastructure.database.database_path` binding |
| `tests/test_silent_learning_integration.py` | Rewritten — per-test temp DB, no `hw.clear()`, asserts real bound path before writes, ConfigStore isolated, incident regression test |
| `domain/silent_learning.py` | Documented `_expand_corrected_term` as ASCII-only (CJK never neighbor-expanded); removed dead `_is_cjk` |
| `features/silent_learning_dictionary_hotword.feature` | Honest conservative-v1 scenarios: full-term learned; single-character `民天→明天` explicitly NOT learned |
| `tests/test_silent_learning_dictionary_hotword_contract.py` | Added `test_single_cjk_correction_in_sentence_not_learned_conservative_v1` |
| `.ai/DICTIONARY_RECOVERY_FEASIBILITY.md` | New — read-only forensic feasibility result |
| `.ai/ROUND9_5A_SELF_REVIEW.md` | Rewritten — withdraws inaccurate claims, honest Gherkin mapping |
| `.ai/TEST_RESULTS.md` | Rewritten — isolated + targeted results, real-DB hash evidence |
| `.ai/ZCODE_REPORT.md` | This file |
| `.ai/CURRENT_TASK.md` | Status → `BLOCKED_REVIEW` |

No production runtime path other than `domain/silent_learning.py` doc/dead-code
cleanup was changed. ASR engine selection, deadlines, fallback order, SDK
lifecycle, injector, float window, native hotkey: untouched.

## 根因判断

`infrastructure/database.py` binds `database_path` at import. Patching
`infrastructure.paths.database_path` does not rebind it, so the old integration
test's `Database()` used the real DB and `hw.clear()` wiped the real dictionary.
The fix patches the correct module attribute and proves the bound path is the
temp path before any write, failing closed on a real-APPDATA path.

## 命令

```bash
git fetch origin
git merge --ff-only origin/backup/hermes-silent-learning-recovery   # 2a2eb54 -> aead778
# read-only forensic on D:\SayIt-Recovery20260629-171434 copies only
python -m pytest tests/test_silent_learning_integration.py -v --tb=short          # 8 passed
python -m pytest <7 targeted files> -v --tb=short                                 # 90 passed
# real-DB SHA-256 compared before/after both runs (file metadata only)
```

## 测试结果

- Isolated test alone: 8 passed, exit 0, normal process exit.
- Targeted Round 9.5A suite: **90 collected / 90 passed / 0 failed / 0 skipped / exit 0**, normal exit.
- Real DB SHA-256 `45ea7cfb…0919` identical before and after (Modify 2026-06-29 15:53:01) — unchanged.
- No full-repository pytest run.

## 未解决的问题

- The real personal dictionary is almost certainly lost (1 non-core row left).
  On-file recovery is not reliably possible (see feasibility report). Recovery
  options (OS prior-version, evidence rebuild, or accept reset) require explicit
  user approval and were NOT executed.
- The historical full-suite hang / pre-existing failures remain out of scope.
- `feature/silent-learning-stabilization` local is ahead of origin by 3 older
  commits — untouched, deferred.

## 风险

- Conservative v1 deliberately does NOT learn single-character Chinese
  corrections (e.g. `民天→明天`). This is a documented product limitation, not a
  bug; original single-character behavior would require an explicit edit/selection
  boundary signal and user approval (option 2 in the independent review).

## 安全声明

Real DB / dictionary / history / config / API key not opened or modified this
round. Feature branch untouched. No `add -A`/`add .`/reset/clean/force-push.
4 untracked pytest logs remain untracked. No data restored or reseeded.

## 状态

`BLOCKED_REVIEW` — awaiting ChatGPT independent review. Not `DONE`.

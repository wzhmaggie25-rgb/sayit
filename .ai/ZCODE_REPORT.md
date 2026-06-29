# ZCode Session Report — Round 9.5A Final Closeout

> Date: 2026-06-29
> Branch: `backup/hermes-silent-learning-recovery`
> 前期实现: **Hermes** (P0-1/P0-2/P0-3)
> 本轮收尾: **Claude Code** (global guard + controlled dictionary reset + reports)

## 接收到的任务

Unattended final closeout on `backup/hermes-silent-learning-recovery`: add an
automatic pytest-wide real-database guard, prove no test can open/migrate the
real DB, run the guard + integration + Round 9.5A targeted suites, confirm the
live DB is unchanged during tests, create fresh pre-reset backups, reset ONLY
the live `dictionary` table (remove the synthetic row, reseed the 5 core
hotwords), keep history/correction_rules unchanged, create post-reset backup,
update reports, commit, push the safety branch. End at `BLOCKED_REVIEW`.

## 实际修改的文件

| File | Change |
|---|---|
| `tests/conftest.py` | New — autouse session fixture installs the process-wide connect guard |
| `tests/db_safety_guard.py` | Added `guarded_connect` / install/uninstall + `RealDatabaseAccessError` (process-wide guard) alongside the existing `IsolatedDatabase` |
| `tests/test_db_global_safety_guard.py` | New — 7 proof tests for the global guard |
| `.ai/FINAL_CLOSEOUT_REPORT.md` | New — closeout evidence |
| `.ai/TEST_RESULTS.md` | Closeout section (97-test run, real-DB unchanged) |
| `.ai/ZCODE_REPORT.md` | This file |
| `.ai/CURRENT_TASK.md` | Status → `BLOCKED_REVIEW` |

No production code changed this round. The dictionary reset used Python stdlib
sqlite3 directly on the live DB (a data operation, not a code change); the
recovery directory and backups live OUTSIDE the repo and are not committed.

## 根因 / 决策

- Guard root cause: the reusable `IsolatedDatabase` only protected opt-in tests.
  The process-wide guard wraps the real `sqlite3.connect` boundary so it fires
  before migrate/write even if a test patches the wrong path symbol.
- Dictionary state: user chose Option 3 (accept reset). Pre-reset state matched
  the incident exactly (dict=1, core=0, history=1125, rules=5); reset committed
  only after in-transaction verification.

## 命令

```bash
git fetch origin
git merge --ff-only origin/backup/hermes-silent-learning-recovery   # ae1bd0b -> 3e6e219
python -m pytest tests/test_db_global_safety_guard.py -v --tb=short          # 7 passed
python -m pytest tests/test_silent_learning_integration.py -v --tb=short     # 8 passed
python -m pytest <8 targeted files> -v --tb=short                            # 97 passed
# pre-reset backups (raw + sqlite backup API, read-only source)
# one-transaction dictionary reset on live DB (stdlib sqlite3)
# post-reset verification + consistent backup
```

## 测试结果

- Guard proof: 7 passed, exit 0.
- Isolated integration: 8 passed, exit 0.
- Round 9.5A targeted (incl. guard): 97 collected / 97 passed / 0 failed / 0 skipped, exit 0, normal exit, ~0.92s.
- Real DB SHA-256 `45ea7cfb…0919` unchanged across all test runs.
- No full-repository pytest run.

## 词典重置结果

dictionary 1→5 (noncore 1→0, core 0/5→5/5); history 1125→1125; rules 5→5;
integrity ok→ok. Core words: Sayit, Typeless, 闪电说, DeepSeek, DashScope.
Live DB hash changed by design `45ea7cfb…`→`5838b47e…`. Backups in
`D:\SayIt-Recovery20260629-185628-dictionary-reset\`.

## 风险 / 未解决

- Personal dictionary restarts from zero (previous terms unrecoverable; accepted).
- Conservative v1 still does not auto-learn single-character Chinese corrections.
- `feature/silent-learning-stabilization` deferred; merge only after independent
  review of this safety-branch HEAD.

## 安全声明

Only the dictionary table modified. HotwordsManager not instantiated; no remote
sync; config/API keys not read or modified; SayIt not started; feature branch
untouched; no full-repo pytest; no `add -A`/`add .`/reset/clean/force-push; DB
backups and recovery dir not committed; 4 pytest logs remain untracked.

## 状态

`BLOCKED_REVIEW` — awaiting ChatGPT independent review. Not `DONE`.

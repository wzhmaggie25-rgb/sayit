# ZCode Session Report — Round 9.5A Final Closeout

> Date: 2026-06-29
> Branch: `backup/hermes-silent-learning-recovery`
> 前期实现: **Hermes** (P0-1/P0-2/P0-3)
> 本轮收尾: **Claude Code** (global guard + controlled dictionary reset + reports)

## 实用ASR重复 P0 修复 Round 2 (2026-06-30, branch `fix-practical-asr-repeat`)

Closed the four ChatGPT review blockers: (1) empty normalized text now raises
`EmptyNormalizedInputError` and the pipeline stops before injection/silent-
learning/history (no raw-garbage fallback); (2) legacy 0.015 noise gate disabled
at runtime (effective 0.0), on-disk config untouched, both values logged; (3)
quality gate rejects only on near-all-zero samples or extremely-low RMS+peak —
quiet continuous speech (RMS ~0.007, high non-zero continuity) is accepted; (4)
real `RecordingPipeline` short-circuit test proves rejected audio aborts
streaming and never reaches batch ASR/corrector/injector/db.add_history/silent-
monitor, plus a normalized-empty pipeline test. Focused 19 passed; prior
targeted suite 99 passed; live DB unchanged. Status → `BLOCKED_REVIEW`. Details
in `.ai/PRACTICAL_ASR_REPEAT_FIX_REPORT.md`.

## 实用ASR重复 P0 修复 (2026-06-30, branch `fix-practical-asr-repeat`)

Built on `feature/silent-learning-stabilization`. Root cause confirmed from the
preserved `sayit_last.wav`: RMS=0.005, zero_fraction=0.968, active_ratio@0.010=
0.032 — effectively silent/over-gated audio (0.015 gate). Fixes: (1) empty-
normalized-input AI guard in `infrastructure/corrector.py` (provider never
called on empty/whitespace/filler-only input); (2) reusable PCM quality metrics
+ fail-closed pipeline gate (`infrastructure/audio_quality.py`,
`application/pipeline.py`) that skips ASR/AI/injection with a microphone message
before any hallucinated text; (3) safe noise gate (default 0.0, clamped to
MAX_NOISE_GATE=0.012, suppression-ratio logging); (4) console UTF-8 logging.
Focused regressions 12 passed; prior targeted suite 99 passed; live DB
unchanged. Status → `BLOCKED_REVIEW`. Details in
`.ai/PRACTICAL_ASR_REPEAT_FIX_REPORT.md`.

## 正式分支整合 (2026-06-30)

Fast-forward-only integration of safety HEAD `838be4f` into
`feature/silent-learning-stabilization` (was `8cc3a49`). Pushed only the formal
branch (`8cc3a49..838be4f`); local == remote == safety HEAD. Targeted suite
re-run on the formal branch: 99 collected / 99 passed / 0 failed / 0 skipped,
exit 0. Live DB unchanged (`5838b47e…`, Modify 18:58:41). Local launch prepared
via `start.bat` (no build, no release, no shortcut change). Status →
`BLOCKED_PRACTICAL_ACCEPTANCE`. Details in `.ai/INTEGRATION_REPORT.md`.

## 后续修复 — collection-time guard gap (latest)

ChatGPT final review found the guard installed via a session autouse fixture,
which runs after pytest collects modules. Fixed: `tests/conftest.py` installs the
guard at conftest import time (+ `pytest_configure`, idempotent) and removes it
in `pytest_unconfigure`; path comparison canonicalized with abspath + realpath +
normcase (`tests/db_safety_guard._canon`). Added a subprocess collection-time
proof and a Windows case-variant proof. Targeted suite now 99 passed (was 97),
exit 0; post-reset live DB unchanged (`5838b47e…`, Modify 18:58:41).

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

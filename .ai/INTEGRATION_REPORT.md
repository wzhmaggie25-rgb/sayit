# Formal Branch Integration Report

> Date: 2026-06-30
> Repository: `wzhmaggie25-rgb/sayit`
> Source (reviewed safety branch): `backup/hermes-silent-learning-recovery`
> Destination (formal branch): `feature/silent-learning-stabilization`
> Executor: Claude Code (host: ZCode), unattended integration task
> Status: **BLOCKED_PRACTICAL_ACCEPTANCE** — NOT DONE.

## Integration summary

Fast-forward-only integration of the reviewed safety-branch HEAD into the formal
feature branch. No merge commit, no rebase, no squash, no force.

| Item | Value |
|---|---|
| Source remote HEAD before (origin/backup) | `838be4f9964fa33ed09e29f8153a1275a48dfbd2` |
| Destination remote HEAD before (origin/feature) | `8cc3a4948dc9fb7a2af51f313f20876bd09130ef` |
| Branch relationship before | origin/feature was a clean ancestor of safety: feature 0 ahead / 32 behind safety (no divergence) |
| Integration method | `git merge --ff-only 838be4f…` on `feature/silent-learning-stabilization` |
| Formal branch HEAD after | `838be4f9964fa33ed09e29f8153a1275a48dfbd2` |
| Push result | `8cc3a49..838be4f  feature/silent-learning-stabilization -> feature/silent-learning-stabilization` |
| Local == remote == safety HEAD | YES, all three equal `838be4f` |

Note: the local `feature` ref had three additional local-only commits
(`541daf3`, `31a6af8`, `9c996d6`) versus `origin/feature`. All three are
ancestors of the safety HEAD `838be4f`, so the fast-forward absorbed them
cleanly and the push over `origin/feature` (`8cc3a49`, also an ancestor) was a
true fast-forward.

## Targeted test verification (post-integration)

Command:

```bash
python -m pytest \
  tests/test_db_global_safety_guard.py \
  tests/test_silent_learning_dictionary_hotword_contract.py \
  tests/test_silent_learning_integration.py \
  tests/test_asr_streaming_context_priority.py \
  tests/test_silent_monitor.py \
  tests/test_dictionary_safety.py \
  tests/test_hotword_promotion.py \
  tests/test_chinese_local_learning.py \
  -v --tb=short
```

| Metric | Value |
|---|---|
| collected | 99 |
| passed | 99 (+4 subtests) |
| failed | 0 |
| skipped | 0 |
| exit code | 0 |
| process exit | normal |
| runtime | ~2.98s |

No full-repository pytest was run.

## Live database fingerprint (filesystem only)

| | SHA-256 | size | Modify |
|---|---|---|---|
| before tests | `5838b47ebaf5072def17d1873dd4cb5efb7acc5b3a2fcaa2f16777d9e61590a8` | 1224704 | 2026-06-29 18:58:41 |
| after tests | `5838b47ebaf5072def17d1873dd4cb5efb7acc5b3a2fcaa2f16777d9e61590a8` | 1224704 | 2026-06-29 18:58:41 |

**LIVE DATABASE UNCHANGED.** Verified by filesystem hash/stat only; the live DB
was never opened via Database/SQLite during this task. The DB still holds exactly
the 5 core hotwords; history 1125; correction_rules 5.

## Local launch method prepared for practical acceptance

The supported development launch (README 方式 A, recommended) requires no build:
`frontend/node_modules` is already present, and the formal branch is checked out
at `838be4f`.

- **Recommended for the 10-use test: double-click `start.bat` in the repo root**
  (`D:\code\sayit_zcode\start.bat`).
  It stops any old SayIt/Electron/backend/port-17890 processes, then launches
  Electron, which manages the Python backend. Fully reversible — close the SayIt
  window (and Ctrl+C the launcher window if it stays open) to stop.
- Equivalent alternative (dev/debug): in `D:\code\sayit_zcode\frontend`, run
  `npx electron .`.

No build/packaging (`electron-packager`) was run; no release was published.

## Desktop shortcut

**No desktop shortcut was created or modified.** The task forbids changing a
shortcut whose target cannot be verified. The README mentions an optional manual
"send `launch_sayit.bat` to desktop" step, but that is left to the user. The
existing desktop shortcut (if any) may still point at an older build — the user
should launch via `start.bat` for this acceptance round rather than rely on a
shortcut.

## Safety affirmations

- Fast-forward-only; no merge commit / rebase / cherry-pick / squash / reset /
  force-push / clean / `git add .` / `git add -A`.
- Only `feature/silent-learning-stabilization` was pushed; `backup/...` and all
  other branches untouched.
- No live database modification or reset; history and correction rules untouched.
- No full-repository pytest; no release published; SayIt/Agent Bridge kept stopped
  during Git and pytest work.
- The 4 known untracked pytest logs remain untracked.

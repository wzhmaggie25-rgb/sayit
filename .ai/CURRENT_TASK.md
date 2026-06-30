# Current Task

> Updated: 2026-06-30

## Status

**BLOCKED_PRACTICAL_ACCEPTANCE**

The reviewed safety branch was fast-forward integrated into the formal branch and
the targeted suite re-verified. Awaiting the user's 10-use practical acceptance
and ChatGPT review. Do not mark `DONE`.

Read first:

```text
.ai/INTEGRATION_REPORT.md
.ai/ROUND9_5A_FINAL_APPROVAL.md
.ai/USER_APPROVAL_FORMAL_INTEGRATION_2026-06-30.md
.ai/TEST_RESULTS.md
```

## Repository and branches

- Repository: `wzhmaggie25-rgb/sayit`
- Formal branch (now integrated): `feature/silent-learning-stabilization` @ `838be4f`
- Source safety branch: `backup/hermes-silent-learning-recovery` @ `838be4f`
- Both local and remote formal HEAD == safety HEAD == `838be4f`.

## Integration result

- Method: fast-forward-only (`git merge --ff-only 838be4f`), no merge commit.
- origin/feature before: `8cc3a49` (clean ancestor of safety; 0 ahead / 32 behind).
- Push: `8cc3a49..838be4f feature/silent-learning-stabilization` (fast-forward).
- Targeted suite on the formal branch: 99 collected / 99 passed / 0 failed /
  0 skipped, exit 0, normal exit.
- Live DB fingerprint unchanged: SHA-256 `5838b47e…90a8`, size 1224704, Modify
  2026-06-29 18:58:41 (5 core hotwords; history 1125; correction_rules 5).
- No full-repository pytest. No live DB write. No release. No shortcut changed.

## How the user runs the 10-use practical acceptance

Launch the integrated dev version (README 方式 A, recommended; no build needed —
`frontend/node_modules` is present):

```text
Double-click:  D:\code\sayit_zcode\start.bat
```

Equivalent dev/debug alternative:

```text
cd D:\code\sayit_zcode\frontend
npx electron .
```

Stop by closing the SayIt window (and Ctrl+C the launcher window if it remains).

### What to check across 10 consecutive real uses

- press/hold then release reliably produces transcription;
- text inserts into the intended window;
- a successful insertion does NOT show a false failure;
- a failed insertion keeps the recognized text available;
- no noisy technical recovery warning appears;
- a clear full-term correction can enter the personal dictionary and refresh ASR
  hotwords;
- no global sentence replacement occurs;
- no crash or lost text across all 10 uses.

## Desktop shortcut

Not created or modified. An existing desktop shortcut may point at an older
build; use `start.bat` for this acceptance round. Changing a shortcut requires a
verifiable, reversible target and explicit confirmation.

## Forbidden

- no `git pull`, merge commit, rebase, cherry-pick, squash, reset, force-push, or
  `git clean`;
- no `git add .` / `git add -A`;
- no full-repository pytest;
- no live database modification or reset; no history / correction-rule change;
- no release publication;
- no desktop-shortcut change without a verified, reversible target;
- do not mark `DONE` before the user's 10-use practical acceptance.

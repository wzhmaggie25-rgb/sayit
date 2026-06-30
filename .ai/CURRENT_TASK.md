# Current Task

> Updated: 2026-06-30

## Status

**BLOCKED_REVIEW**

The four ChatGPT review blockers on the practical-ASR fix are closed and tested.
Awaiting independent review. Do not mark `DONE`.

Read first:

```text
.ai/PRACTICAL_ASR_REPEAT_CHATGPT_REVIEW.md
.ai/PRACTICAL_ASR_REPEAT_FIX_REPORT.md
.ai/PRACTICAL_ASR_REPEAT_LOG_DIAGNOSIS.md
.ai/TEST_RESULTS.md
```

## Repository and branches

- Repository: `wzhmaggie25-rgb/sayit`
- Working branch: `fix-practical-asr-repeat`
- Frozen — do not modify or push: `feature/silent-learning-stabilization`,
  `backup/hermes-silent-learning-recovery`.

## Review blockers closed

1. **Empty normalized text fails closed.** New `EmptyNormalizedInputError`
   (`infrastructure/corrector.py`); the pipeline catches it and stops before
   injection, silent learning, and successful-history, emitting
   `未识别到有效语音内容，请重试` with terminal reason
   `empty_normalized_input`. No raw-garbage fallback.
2. **Legacy 0.015 noise gate disabled at runtime.** `AudioCapture.start()` sets
   the effective gate to 0.0 regardless of on-disk config; configured + effective
   values logged. On-disk config untouched. Fail-closed relies on the
   post-capture quality gate.
3. **Quality gate no longer rejects quiet speech.** `effectively_silent` rejects
   only on near-all-zero samples (`nonzero_fraction < 0.05`) or extremely-low
   RMS+peak (`rms < 0.003 and peak < 0.02`); `active_frame_ratio` is diagnostic
   only. Quiet continuous speech (RMS ~0.007) is accepted; the 97%-zero incident
   fixture is still rejected.
4. **Real pipeline short-circuit proof.** `tests/test_pipeline_short_circuit.py`
   instantiates the real `RecordingPipeline`: rejected audio aborts streaming and
   never calls batch ASR / corrector / injector / `db.add_history` / silent
   monitor, emitting the expected failure events; normalized-empty raw ASR stops
   before injection.

## Test results

- Focused regressions: 19 passed (4 empty-input + 12 audio-quality/gate +
  3 pipeline short-circuit), exit 0.
- Prior targeted suite: 99 collected / 99 passed (+4 subtests) / 0 failed /
  0 skipped, exit 0.
- Live DB unchanged: SHA-256 `bbdea0bd…090bd`, size 1224704, Modify
  2026-06-30 18:54:51 (filesystem hash/stat only; never opened via SQLite).
- No full-repository pytest.

## Forbidden

- no user voice retest yet;
- no full-repository pytest;
- no live DB / dictionary / history / correction-rule / API-key modification;
- no modification or push to frozen branches;
- no release or desktop-shortcut change;
- no broad process-kill commands;
- no `git pull`, rebase, cherry-pick, reset, force push, or `git clean`;
- no `git add .` or `git add -A`;
- do not mark `DONE`.

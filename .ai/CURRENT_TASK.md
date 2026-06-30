# Current Task

> Updated: 2026-06-30

## Status

**BLOCKED_REVIEW**

The practical-ASR-repeat P0 fixes are implemented and tested. Awaiting ChatGPT
independent review. Do not mark `DONE`.

Read first:

```text
.ai/PRACTICAL_ASR_REPEAT_FIX_REPORT.md
.ai/PRACTICAL_ASR_REPEAT_LOG_DIAGNOSIS.md
.ai/PRACTICAL_ASR_REPEAT_INCIDENT_2026-06-30.md
.ai/TEST_RESULTS.md
```

## Repository and branches

- Repository: `wzhmaggie25-rgb/sayit`
- Working branch: `fix-practical-asr-repeat` (built on `feature/silent-learning-stabilization`)
- Frozen — do not modify or push: `feature/silent-learning-stabilization`,
  `backup/hermes-silent-learning-recovery`.

## What was fixed

1. **Empty normalized AI input → fail closed.** `infrastructure/corrector.py`
   returns `(text, None, None)` and never calls any AI provider when normalized
   text is empty/whitespace. No hallucinated text. Regression tests in
   `tests/test_corrector_empty_input_guard.py`.
2. **Audio-quality fail-closed gate.** New `infrastructure/audio_quality.py`
   (RMS, peak, zero/nonzero fraction, active-frame ratio, duration) +
   `application/pipeline.py` gate after capture: on effectively-silent audio
   (nonzero_fraction < 0.05 or active_frame_ratio < 0.05) it aborts streaming,
   emits `未检测到清晰语音，请检查麦克风或提高音量`, and terminates before
   ASR/AI/injection — no invented text, no hallucinated history. Tests in
   `tests/test_audio_quality_gate.py`.
3. **Safe noise gate.** `noise_gate_threshold` added to `DEFAULT_CONFIG`
   (default 0.0); effective gate clamped to `MAX_NOISE_GATE=0.012`; suppression
   ratio logged. Quiet speech is no longer zeroed into near-silence.
4. **Console UTF-8 logging** in `server.py` so Chinese log fields are readable.

## WAV evidence (read-only)

`%USERPROFILE%\Desktop\sayit_last.wav`: RMS=0.0051, zero_fraction=0.968,
active_ratio@0.010=0.032, duration 4.03s → effectively silent/over-gated. This
supported choosing conservative thresholds safely; no second recording required.
Hence status is `BLOCKED_REVIEW` (not `BLOCKED_NEEDS_ONE_CONTROLLED_REPRO`).

## Test results

- Focused P0 regressions: 12 passed (4 empty-input + 8 audio-quality), exit 0.
- Prior targeted suite: 99 collected / 99 passed (+4 subtests) / 0 failed /
  0 skipped, exit 0.
- Live DB unchanged: SHA-256 `bbdea0bd…090bd`, size 1224704, Modify
  2026-06-30 18:54:51 (filesystem hash/stat only; never opened via SQLite).
- No full-repository pytest.

## Forbidden

- no further 10-use acceptance until review;
- no broad phrase blacklist for `设置语言`;
- no full-repository pytest;
- no live DB / dictionary / history / correction-rule / API-key change;
- no modification or push to frozen branches;
- no release or desktop-shortcut change;
- no broad process-kill commands;
- no `git pull`, rebase, cherry-pick, reset, force push, or `git clean`;
- no `git add .` or `git add -A`;
- do not mark `DONE`.

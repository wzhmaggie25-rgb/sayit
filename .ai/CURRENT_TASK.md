# Current Task

> Updated: 2026-06-30

## Status

**READY_P0_FIX_EXECUTION**

The user-provided runtime log identifies two production failures:

1. raw ASR is already wrong on low-quality audio;
2. normalized AI input can become empty, yet DeepSeek is still called and invents output.

Read first:

```text
.ai/PRACTICAL_ASR_REPEAT_LOG_DIAGNOSIS.md
.ai/PRACTICAL_ASR_REPEAT_INCIDENT_2026-06-30.md
.ai/INTEGRATION_REPORT.md
```

## Repository and branches

Repository:

```text
wzhmaggie25-rgb/sayit
```

Local directory:

```text
D:\code\sayit_zcode
```

Only allowed branch:

```text
fix-practical-asr-repeat
```

Frozen — do not modify or push:

```text
feature/silent-learning-stabilization
backup/hermes-silent-learning-recovery
```

## Confirmed evidence

Session `ed165e194aee`:

- streaming ASR produced a short incorrect raw result;
- AI preserved the incorrect result;
- injection later failed.

Session `5b87e455f2e1`:

- streaming ASR produced a 2-character result;
- batch DashScope fallback returned the same short result;
- batch audio log reported `RMS=0.005`;
- runtime noise gate was `0.0150`, gain `1.5x`;
- normalization reduced the AI input to empty;
- DeepSeek was still called with `len=0 input=''` and generated new text;
- injection later failed.

The first known wrong stage is ASR. A second deterministic bug allows AI hallucination from empty normalized input.

## This task's one and only goal

Fix the low-audio / empty-AI-input failure path so SayIt never injects invented text when audio is effectively silent or normalized ASR input is empty.

## Required execution

### 1. Preserve and inspect the existing WAV

Before code changes, inspect `%USERPROFILE%\Desktop\sayit_last.wav` if present.

Report without committing or uploading it:

- SHA-256;
- sample rate, channels, sample width, duration;
- RMS and peak;
- zero/nonzero sample fraction;
- active-frame ratio at multiple RMS thresholds;
- whether speech appears structurally present, clipped, or effectively silent.

Do not require another user recording before this inspection.

### 2. Fix empty normalized AI input

In the correction path:

- retain the original current-session input separately;
- after deterministic normalization, if the normalized text is empty or whitespace, do not build prompts and do not call any AI provider;
- return a non-success correction result that lets the pipeline fail closed rather than accept generated text;
- add a regression test proving the provider function is never called for empty normalized input;
- add a regression test for filler-only input that normalizes to empty;
- do not return provider-generated content when current-session input is empty.

### 3. Add an audio-quality fail-closed gate

Do not rely only on output character length.

Add reusable PCM quality metrics, at minimum:

- RMS;
- peak;
- zero/nonzero fraction;
- active-frame ratio;
- duration.

Use evidence from `sayit_last.wav` to choose a conservative threshold.

When audio is effectively silent or lacks enough active speech:

- skip ASR acceptance, AI correction, and injection;
- preserve no invented final text;
- emit a clear user-facing message such as `未检测到清晰语音，请检查麦克风或提高音量`;
- mark the terminal outcome as an audio-quality failure;
- do not save hallucinated text to history.

### 4. Make the noise gate safe

Current runtime evidence shows `noise_gate=0.0150` while captured overall RMS was `0.005`.

After WAV inspection:

- if speech is present but suppressed, lower or adapt the runtime noise gate;
- measure raw/gained audio before gating and post-gate audio separately;
- do not silently zero most speech;
- avoid directly editing the user's config unless a documented, reversible migration is necessary;
- log the effective threshold and suppression ratio without logging audio content.

### 5. Keep session safety

- each recording must use fresh audio buffers and a fresh streaming session;
- no prior-session partial/final result may be reused;
- keep active-session checks in frontend/backend routing;
- add a focused regression test if a stale-session path is found during inspection.

### 6. Fix log encoding for diagnosis

Ensure Chinese log fields written to the persistent log remain valid UTF-8 and readable, including:

- audio device name;
- raw ASR text;
- AI request/response summary;
- injection preview.

Do not expose secrets or full unrelated user content.

### 7. Focused tests, then prior targeted suite

Run focused tests for:

- empty normalized input never calling AI;
- filler-only input;
- low/silent PCM rejection;
- valid quiet speech not being rejected if fixture evidence supports it;
- no injection and no invented history record on audio-quality failure;
- fresh session state.

Only after focused tests pass, run the prior approved 99-test targeted suite.

Do not run full-repository pytest.

### 8. Safety evidence

Before and after tests, compare the live database using filesystem SHA-256, size, and modification time only. It must remain unchanged.

Do not modify:

- live database;
- dictionary;
- history;
- correction rules;
- API keys or endpoints;
- desktop shortcuts;
- formal or safety branches.

## Completion

Update:

```text
.ai/PRACTICAL_ASR_REPEAT_FIX_REPORT.md
.ai/TEST_RESULTS.md
.ai/ZCODE_REPORT.md
.ai/CURRENT_TASK.md
```

Commit and push only `fix-practical-asr-repeat`.

Final status:

```text
BLOCKED_REVIEW
```

If WAV evidence is missing or thresholds cannot be chosen safely, do not guess. Fix the empty-input AI bug, document the missing audio evidence, set:

```text
BLOCKED_NEEDS_ONE_CONTROLLED_REPRO
```

and stop.

## Forbidden

- no further 10-use acceptance;
- no broad phrase blacklist for `设置语言`;
- no full-repository pytest;
- no live DB write/reset/restore;
- no modification or push to frozen branches;
- no release or desktop-shortcut change;
- no broad process-kill commands;
- no `git pull`, rebase, cherry-pick, reset, force push, or `git clean`;
- no `git add .` or `git add -A`;
- do not mark `DONE`.

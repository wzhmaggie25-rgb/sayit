# Practical Acceptance Incident — Repeated Wrong Output

> Date: 2026-06-30
> Base formal branch: `feature/silent-learning-stabilization`
> Investigation branch: `fix-practical-asr-repeat`
> Severity: **P0 practical acceptance failure**

## User-observed failure

During the first practical acceptance attempt, the user spoke two different utterances. Both were transcribed/injected as the same incorrect phrase:

```text
设置语言
```

The 10-use acceptance is stopped. Neither attempt counts as a pass.

## Current judgment

Two different utterances producing the same identical wrong result is not ordinary recognition accuracy drift. High-priority hypotheses are:

1. stale ASR partial/final text reused across sessions;
2. the application captured the wrong input device, near-silence, or unrelated system audio;
3. a new Electron frontend connected to an unexpected/stale backend process;
4. raw ASR text was changed by the AI-correction stage into the repeated phrase;
5. session or event routing replayed a prior result.

The literal phrase `设置语言` is not present in the reviewed repository source, so a fixed source-code string is not currently supported by evidence.

## Evidence already available in the code

The runtime log should distinguish the stages:

- `[AUDIO-DEVICE]` — actual default input device;
- `Pipeline: captured ... PCM bytes` — captured size/duration;
- `[ASR-STREAM] final text` or batch engine logs — engine result;
- `[ASR-RAW] provider=... text=...` — raw ASR output;
- AI result / provider — corrected final output;
- history debug info — engine and streaming flag.

The application may also write the latest captured WAV to:

```text
%USERPROFILE%\Desktop\sayit_last.wav
```

## Safety

- Freeze `feature/silent-learning-stabilization`.
- Do not continue practical acceptance.
- Do not modify or reset the live database.
- Do not expose API keys or unrelated user history.
- Diagnose from the two existing failed sessions before asking for another spoken test.

# Practical ASR Repeat — Log Diagnosis

> Date: 2026-06-30
> Branch: `fix-practical-asr-repeat`
> Evidence: user-provided runtime log covering two failed practical sessions
> Verdict: **root cause narrowed; production fix required**

## Confirmed findings

### 1. The first wrong stage is ASR, not injection

Session `ed165e194aee`:

- captured about 126,976 PCM bytes over about 3 seconds;
- streaming ASR completed;
- `[ASR-RAW]` was already a short incorrect result;
- DeepSeek largely preserved that short incorrect result;
- injection later failed.

Session `5b87e455f2e1`:

- captured about 129,024 PCM bytes over about 3 seconds;
- streaming ASR returned a 2-character result;
- the existing short-output gate fell back to batch DashScope;
- batch DashScope returned the same short result;
- `[ASR-RAW]` was already wrong before AI and injection.

Therefore stale frontend injection is not the first known failure stage.

### 2. Captured audio quality is suspiciously low

For the second session, the batch ASR log reports:

```text
RMS=0.005
```

The runtime also reports:

```text
noise_gate=0.0150
gain=1.5x
```

`AudioCapture` zeros chunks whose RMS is below the configured noise-gate threshold. A 0.015 gate is high relative to the observed 0.005 overall RMS and can suppress quiet speech into near-silence. This is a high-confidence contributor, but the preserved WAV must be measured before choosing the final threshold or migration behavior.

### 3. A separate deterministic AI bug is confirmed

In the second session:

- `[ASR-RAW]` contained a short result;
- deterministic normalization reduced the AI input to an empty string;
- the code still called DeepSeek with `len=0 input=''`;
- DeepSeek returned newly generated text;
- the generated text was then used as the final output candidate.

This is never acceptable for a voice-input product. The AI layer must not invent text when normalized input is empty.

### 4. The two sessions do not support a simple stale-result theory

The logged raw ASR values differ between the two sessions, and the second session's streaming and batch engines agreed on its short result. This does not prove session routing is perfect, but it makes a single cached prior result less likely than low-quality audio plus unsafe AI fallback.

### 5. Console/log text encoding is broken

Chinese content and the microphone device name appear as mojibake in the captured console text. This limits exact phrase comparison and must be fixed or logged to UTF-8 safely, but it is not by itself sufficient to explain the wrong recognition.

### 6. Injection also failed

Both sessions later reached injection fallback failure against `sunbrowser.exe`. This is separate from the recognition root cause and should not be mixed into the ASR fix. Preserve recognized text for the user when injection fails.

## Required production behavior

1. Never call an AI provider with empty normalized input.
2. Never accept AI-generated text that is not traceable to non-empty current-session ASR input.
3. On low-quality or effectively silent audio, fail closed with a clear microphone message instead of injecting hallucinated text.
4. Measure raw and post-gate audio quality separately.
5. Do not rely only on output character count as the streaming quality gate.
6. Do not add a phrase blacklist for `设置语言`.
7. Do not modify the live database, dictionary, history, correction rules, or API configuration.

## Remaining evidence needed before selecting the noise-gate fix

Inspect the preserved `sayit_last.wav` and report:

- duration, sample rate, channels, sample width;
- RMS, peak, zero fraction, nonzero fraction;
- active-frame ratio at several frame-RMS thresholds;
- whether speech is audible / structurally present;
- whether the current 0.015 noise gate likely removed most speech.

If speech is present but quiet, lower or adapt the runtime gate safely. If the WAV is effectively silence or unrelated audio, diagnose the selected input device and add an explicit device check/selection path.

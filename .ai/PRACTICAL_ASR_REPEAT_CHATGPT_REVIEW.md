# Practical ASR Repeat — ChatGPT Independent Review

> Date: 2026-06-30
> Reviewed branch: `fix-practical-asr-repeat`
> Reviewed HEAD: `67c6ab8fae504976e46ac4876d6695455620c858`
> Verdict: **CHANGES REQUIRED — PRACTICAL RETEST NOT AUTHORIZED**

## Accepted work

- The preserved WAV evidence is useful and supports the diagnosis that the incident recording was heavily zeroed / over-gated.
- The provider-level empty-input guard correctly prevents calling an AI provider with empty normalized text.
- The new PCM metrics are useful for diagnostics.
- The pipeline now has an early audio-quality decision point.
- Focused tests and the prior 99-test targeted suite are reported passing.
- The formal and safety branches remain frozen.

## Blocking finding 1 — empty normalized input does not actually fail closed

`infrastructure.corrector.correct_text()` returns `("", None, None)` when normalized input is empty.

However, `application.pipeline.RecordingPipeline.run()` initializes `final_text = raw_text` and only replaces it when `corrected` is non-empty. Therefore an empty normalized result causes the pipeline to retain the original short/garbled ASR text and continue toward injection.

This prevents DeepSeek from inventing new text, but it does not prevent invalid current-session ASR text from being injected. The report's claim that this path is fail-closed is not accurate.

### Required fix

Introduce an explicit empty-normalized-input outcome that the pipeline can distinguish from ordinary provider failure. A custom exception, typed result, or explicit status is acceptable.

On this outcome the pipeline must:

- stop before injection;
- not start silent learning;
- not present the raw garbled text as a successful final result;
- emit a clear user-facing message such as `未识别到有效语音内容，请重试`;
- terminate with a specific non-success reason;
- avoid creating a successful/final-text history row.

Add a pipeline-level regression test using non-empty raw ASR text that normalizes to empty and prove that AI provider, injector, silent monitor, and successful history are not reached.

## Blocking finding 2 — the user's existing 0.015 noise gate remains effectively active

The new default is `0.0`, but defaults do not replace an existing user value. The incident runtime already showed an existing configured value of `0.015`.

The implementation computes:

```text
effective_gate = min(configured_gate, 0.012)
```

Thus the user's existing value becomes `0.012`, which is still more than twice the incident WAV's overall RMS of about `0.0051`. There is no evidence that this cap preserves the user's quiet speech. The same over-gating failure can recur.

### Required fix

For this P0 recovery, disable chunk-level zeroing for legacy/high configured gates rather than guessing another high threshold. The safest narrow behavior is:

- keep the user's on-disk setting untouched;
- make the effective runtime noise gate `0.0` for the current recovery version, or explicitly treat legacy values at/above the incident range as disabled;
- log configured and effective values;
- rely on the post-capture quality gate for fail-closed behavior.

Adaptive/noise-floor-based gating can be designed later with real pre-gate audio evidence.

Add a regression test proving that a configured value of `0.015` does not zero a quiet valid signal in the recovery version.

## Blocking finding 3 — the quality gate can reject valid quiet speech

`AudioQuality.effectively_silent` currently rejects when either:

```text
nonzero_fraction < 0.05
OR
active_frame_ratio < 0.05
```

`active_frame_ratio` uses a fixed frame RMS threshold of `0.010`. A continuous, non-zero, quiet voice signal around RMS `0.005–0.009` can therefore be rejected solely because it is below `0.010`, even when it was not zeroed and contains real speech.

### Required fix

Do not use low active-frame ratio as an independent rejection condition at this fixed threshold. Use combined evidence, for example:

- near-all-zero samples (the incident signature), or
- extremely low RMS and peak together, or
- another conservative combination that does not reject a continuous quiet signal merely for being below `0.010`.

Keep active-frame ratio as a diagnostic metric unless validated against real quiet speech.

Add a quiet-signal regression fixture with approximately incident-level RMS but high non-zero continuity and prove it is not rejected. The incident-like 97%-zero fixture must still be rejected.

## Blocking finding 4 — tests do not prove the production pipeline short-circuits

`PipelineAudioQualityGateTests` only call `measure_pcm()` and `should_reject_audio()`. The file explicitly says it does not instantiate the full pipeline. Therefore the claims that ASR, AI, injection, history, and silent learning are not reached are inferred from source layout rather than executable regression proof.

### Required fix

Add a focused pipeline test with fakes/mocks proving for rejected audio:

- streaming session is aborted;
- batch ASR is not called;
- corrector is not called;
- injector is not called;
- `db.add_history` is not called;
- silent monitor is not called;
- the expected user-facing and terminal error events are emitted.

Also add the normalized-empty pipeline test described in finding 1.

## Test expectations after repair

Run:

1. focused empty-normalized-input tests;
2. focused audio capture/noise-gate tests;
3. focused audio-quality tests including valid quiet signal;
4. focused production-pipeline short-circuit tests;
5. the prior approved 99-test targeted suite.

Do not run the full repository suite. Verify the live database SHA-256, size, and modification time remain unchanged around tests.

## Decision

The AI provider hallucination bug is partially fixed, but the current branch can still inject raw garbage and can still suppress or reject the user's quiet speech. Do not ask the user to perform another voice test yet.

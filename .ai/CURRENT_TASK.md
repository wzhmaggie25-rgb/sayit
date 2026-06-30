# Current Task

> Updated: 2026-06-30

## Status

**BLOCKED_REVIEW_FIX_REQUIRED**

ChatGPT independent review found four blocking gaps. Practical voice retest is not authorized yet.

Read first:

```text
.ai/PRACTICAL_ASR_REPEAT_CHATGPT_REVIEW.md
.ai/PRACTICAL_ASR_REPEAT_FIX_REPORT.md
.ai/PRACTICAL_ASR_REPEAT_LOG_DIAGNOSIS.md
```

## Repository and branches

- Repository: `wzhmaggie25-rgb/sayit`
- Only working branch: `fix-practical-asr-repeat`
- Frozen: `feature/silent-learning-stabilization`, `backup/hermes-silent-learning-recovery`

## Accepted state

- preserved WAV evidence confirms the incident recording was heavily zeroed / over-gated;
- empty normalized text no longer reaches an AI provider;
- PCM quality metrics and an early pipeline decision point exist;
- focused tests and prior 99-test targeted suite were reported passing;
- formal and safety branches remain unchanged.

## Blocking gap 1 — empty normalized text still falls back to raw garbage

`correct_text()` returns an empty string, but the pipeline keeps its initial `final_text = raw_text` when corrected text is empty. This can still inject the short/garbled raw ASR result.

Required:

1. add an explicit empty-normalized-input outcome (custom exception, typed result, or explicit status);
2. pipeline must stop before injection and silent learning;
3. emit `未识别到有效语音内容，请重试` or equivalent;
4. do not create a successful/final-text history row;
5. add a real pipeline test proving provider, injector, silent monitor, and successful history are not reached.

## Blocking gap 2 — existing 0.015 gate still becomes 0.012

The user's existing config is not replaced by the new default. `min(0.015, 0.012)` still leaves an effective gate well above the incident RMS (~0.0051), so speech can still be zeroed.

Required for this recovery version:

1. keep on-disk config untouched;
2. disable chunk-level zeroing at runtime (`effective_gate=0.0`) or explicitly disable legacy/high values in the incident range;
3. log configured and effective values;
4. rely on post-capture quality checks;
5. add a regression proving configured `0.015` does not zero a quiet valid signal.

Do not guess another high fixed threshold. Adaptive gating belongs to a later task with pre-gate evidence.

## Blocking gap 3 — fixed active-frame threshold can reject quiet valid speech

The current rule rejects whenever `active_frame_ratio < 0.05`, where active means frame RMS >= 0.010. Continuous quiet speech around RMS 0.005–0.009 can be rejected even with high non-zero continuity.

Required:

1. do not use low active-frame ratio as an independent rejection condition at the fixed 0.010 threshold;
2. reject using combined conservative evidence such as near-all-zero samples or extremely low RMS+peak;
3. retain active-frame ratio as diagnostic unless validated;
4. add a quiet continuous fixture around incident-level RMS with high non-zero continuity and prove it is accepted;
5. retain rejection of the incident-like 97%-zero fixture.

## Blocking gap 4 — no executable production-pipeline short-circuit proof

Current tests only test helper functions and explicitly avoid instantiating the full pipeline.

Add a focused pipeline test proving rejected audio:

- aborts the streaming session;
- does not call batch ASR;
- does not call corrector;
- does not call injector;
- does not call `db.add_history`;
- does not call silent monitor;
- emits the expected user-facing and terminal failure events.

Also add the normalized-empty pipeline test from gap 1.

## Required test sequence

Run only:

1. empty-normalized-input unit and pipeline tests;
2. audio capture/noise-gate tests;
3. audio-quality tests including valid quiet audio;
4. production-pipeline short-circuit tests;
5. prior approved 99-test targeted suite.

Do not run full-repository pytest.

Before and after tests, verify the live database SHA-256, size, and modification time using filesystem reads only. It must remain unchanged.

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

## Forbidden

- no user voice retest yet;
- no full-repository pytest;
- no live database/dictionary/history/correction-rule/API-key modification;
- no modification or push to frozen branches;
- no release or desktop-shortcut change;
- no broad process-kill commands;
- no `git pull`, rebase, cherry-pick, reset, force push, or `git clean`;
- no `git add .` or `git add -A`;
- do not mark `DONE`.

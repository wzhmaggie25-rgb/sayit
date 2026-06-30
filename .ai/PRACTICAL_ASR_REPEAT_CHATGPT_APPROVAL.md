# Practical ASR Repeat — ChatGPT Review Approval

> Date: 2026-06-30
> Reviewed branch: `fix-practical-asr-repeat`
> Reviewed implementation HEAD: `4145e7aa647e9456e030471564059502a1fbd996`
> Verdict: **APPROVED FOR ONE CONTROLLED PRACTICAL RETEST**

## Code-review decision

The four previous blockers are closed sufficiently for one controlled real-device reproduction:

1. empty normalized text raises `EmptyNormalizedInputError` and the production pipeline stops before injection, history success, or silent learning;
2. the legacy configured noise gate is disabled at runtime (`effective=0.0`) without changing the user's on-disk config;
3. quiet continuous audio is no longer rejected solely because it is below the fixed active-frame threshold;
4. real `RecordingPipeline` short-circuit tests prove rejected audio and normalized-empty text do not reach injection/history/silent learning.

Focused tests report 19 passed; the prior targeted suite reports 99 passed; the live database fingerprint remained unchanged during tests.

The fix branch is a clean descendant of `feature/silent-learning-stabilization` with no divergence.

## Non-blocking test-quality notes

These should be cleaned up later but do not block the single controlled retest:

- some unit-test `assert_not_called()` statements are placed after the expected exception and are therefore unreachable;
- pipeline tests catch broad exceptions before asserting the expected terminal state;
- the normalized-empty pipeline test injects the explicit exception through a fake corrector rather than using the real corrector implementation end-to-end.

Source inspection plus the combined unit/pipeline coverage is sufficient for one controlled retest, but these tests should not be described as exhaustive production proof.

## Authorization boundary

Authorized now:

- prepare the local `fix-practical-asr-repeat` checkout;
- verify the exact backend path and port owner;
- start the development version from the fix branch;
- perform exactly one user-spoken test in Windows Notepad;
- preserve the resulting log and WAV evidence;
- stop immediately after that one test.

Not authorized:

- merging into `feature/silent-learning-stabilization`;
- starting the 10-use acceptance;
- publishing/building a release;
- modifying desktop shortcuts;
- modifying/resetting the live database;
- running full-repository pytest;
- performing repeated exploratory voice tests.

## Controlled phrase and pass criteria

Target application: Windows Notepad with the text cursor active.

Speak exactly or approximately:

```text
今天下午三点开会
```

Pass requires:

1. the captured result substantially matches the spoken phrase;
2. it does not output `设置语言` or unrelated generated content;
3. runtime log shows the configured noise gate and effective runtime gate `0.0`;
4. readable UTF-8 audio-device and ASR logs;
5. no AI request with empty normalized input;
6. text is inserted into Notepad or, if injection alone fails, the correct recognized text remains recoverable without being replaced by invented content;
7. no crash.

On any failure, stop after the first attempt and preserve the relevant log/WAV. Do not retry until reviewed.

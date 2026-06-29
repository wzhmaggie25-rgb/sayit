# Stable Baseline Regression Comparison

> Compared code baseline: `0d69a989f03e214b47899173148eb64389bc02be`
> Current runtime code baseline: `3d6549faddb58733517b82518d1c111c72eae904`
> Current branch task HEAD when written: `42c9fed5410c444ce7483ea3fed649e3b3279dc8`
> Date: 2026-06-29

## Executive conclusion

The current branch is not a small stabilization patch over the stable backup. It is 144 commits ahead and contains a partial rewrite of the runtime path.

Across the most important production files alone, the comparison contains roughly:

- 3,605 added lines;
- 664 deleted lines;
- 4,269 touched production lines.

Largest runtime changes include:

- `infrastructure/injector.py`: 988 changed lines;
- `native/context_helper/src/keyboard_helper.cpp`: 570 changed lines;
- `infrastructure/keyboard_helper_dll.py`: 503 changed lines;
- `frontend/main.js`: 489 changed lines;
- `application/orchestrator.py`: 390 changed lines;
- `application/pipeline.py`: 335 changed lines;
- `domain/correction.py`: 259 changed lines;
- `server.py`: 251 changed lines.

The regression pattern is therefore architectural accumulation, not one isolated typo.

---

## 1. Why the older build felt more stable

The stable frontend primarily reacted to:

- `recording_started`;
- `recording_stopped`;
- `pipeline_done`;
- generic `error`.

WebSocket close/error only reconnected and did not independently overwrite the float.

The current runtime has overlapping session-ending mechanisms:

- `pipeline_done`;
- `pipeline_terminal`;
- generic `error`;
- `ws_close`;
- `ws_error`;
- watchdog timeout;
- 500 ms recording poll fallback.

Both `pipeline_done` and `pipeline_terminal` independently update the float. Generic error and WebSocket close may update it again. This allows a valid completion to be followed by an error-looking state.

The new backend supervisor also visibly reports restart messages and destroys the result card after recovery. The old build only logged backend exit and did not expose technical recovery wording.

### Judgment

The reported “text appeared, then float said recognition failed” is a structural multi-terminal regression.

The yellow “backend recovery” text is newly introduced behavior and proves the backend process exited abnormally; it is not an ASR quality message.

---

## 2. Why recognition accuracy can now appear much worse

There is no single proven cause without inspecting the user's private runtime data and per-session stage metrics. The code comparison shows four concrete risk multipliers.

### A. Wrong-but-long streaming output is accepted as final

Both baseline and current pipeline trust streaming output when it is non-empty and long enough for recording duration. The gate does not compare streaming against batch ASR and does not measure semantic quality.

A completely wrong sentence of plausible length therefore bypasses the better batch path.

### B. Current finalization is more aggressive

Stable behavior:

- streaming `finish()` timeout was at least 45 seconds;
- cascade engines were not constrained by one 30-second global budget.

Current behavior:

- streaming finalization is capped at 8 seconds;
- streaming, batch cloud engines, lazy local model load and inference share a nominal 30-second ASR budget;
- DashScope batch is capped at 15 seconds or the smaller remaining budget;
- later fallback engines receive progressively less time.

This can create:

- incomplete streaming finalization;
- more fallback transitions;
- cloud batch timeout followed by a lower-quality secondary/local result;
- complete failure after the shared budget is exhausted.

### C. Learned corrections can rewrite a good provider result

Current code added local Chinese replacement extraction for short CJK edits. Active rules still use unrestricted `str.replace()` over the full sentence once confidence/match thresholds are met.

The current database also stores rules by `(pattern, replacement)`, allowing multiple replacements for the same pattern to coexist. Rule application is sequential, so broad or chained replacements can alter multiple unrelated positions.

This means poor final text may be created after ASR, even when the provider raw text was better.

### D. Learned replacements can become ASR hotwords

Current code added automatic hotword promotion after evidence from two distinct history sessions. A promoted replacement is pushed into the personal dictionary and biases later ASR requests.

A wrong learned term can therefore move from post-processing into the recognition layer and persist across sessions.

### Important data caveat

The stable Git commit protects source code, not the user's runtime database, correction rules, dictionary, history, config or provider state.

Rolling code back to `0d69a98` while keeping the current runtime data may therefore not restore the old accuracy.

The real database/dictionary must not be deleted or rewritten during diagnosis.

---

## 3. What is probably not the main cause

`audio_capture.py` changed stream-close ordering and may lose a final fraction of a chunk around stop. That can cut a final syllable, but it does not plausibly explain an entire sentence becoming mostly wrong characters.

The AI correction prompt files were not changed in the stable-to-current comparison. AI can still over-edit because any non-empty output is accepted, but prompt-code regression is not currently the strongest explanation.

---

## 4. Why recent tests did not protect the user

The last implementation commit changed ASR streaming/deadline, frontend terminal handling, injector routing and native key handling in one commit.

Several new frontend tests inspected source strings instead of executing the production event handler. One ASR deadline test asserted known stale behavior as success. The test report also listed names that did not match committed tests.

Therefore a green test count did not represent the real user path.

---

## 5. Required differential diagnosis before more patching

Round 9.5 must begin with a stable-vs-current golden-path comparison.

Use isolated test fixtures only; do not read or alter the user's real database, dictionary, history, clipboard, audio or API keys.

### A. Same synthetic provider responses

Run both code paths with identical mocked responses for:

- streaming wrong-but-long candidate;
- batch correct candidate;
- batch timeout plus usable streaming fallback;
- AI timeout with usable pre-AI text;
- injection failure with usable final text.

Capture stage outputs:

1. streaming candidate;
2. batch candidate;
3. selected raw ASR;
4. local correction candidate;
5. AI candidate;
6. final selected text;
7. injection state;
8. canonical terminal;
9. float action;
10. result-card action.

### B. Isolated correction-rule fixtures

Prove current behavior on synthetic rules:

- repeated substring replacement;
- conflicting replacements;
- chained replacement;
- Chinese short-fragment replacement;
- bad rule promoted to hotword after two synthetic histories.

Then prove the corrected behavior preserves raw ASR when uncertain.

### C. Production event sequence comparison

Replay identical event sequences through:

- stable event mapping;
- current production controller.

Prove that one completion cannot later become recognition failure because of `pipeline_done`, `pipeline_terminal`, generic error, WS close or watchdog.

### D. Redacted runtime observability

Add non-content metrics only:

- selected engine/source;
- raw/final lengths;
- non-reversible hashes;
- rule replacement count/edit ratio;
- AI edit ratio;
- terminal reason;
- backend exit code/signal;
- last completed stage;
- worker/process cleanup result.

Do not log text content.

---

## 6. Repair strategy

Do not reset the branch wholesale to the stable commit. The old build also contained unsafe learning behavior and missing injection protections.

Use the stable version as a behavior reference, then restore simplicity selectively:

1. batch ASR is canonical when available;
2. streaming is progress plus strictly gated fallback;
3. learned rules are shadow-only until bounded safety gates pass;
4. AI output requires a conservative candidate safety gate;
5. exactly one terminal controls the float;
6. injection failure with usable text shows existing “完成” and opens the existing result card;
7. idle backend recovery is silent;
8. stable float appearance remains unchanged;
9. blocking SDK/local inference is placed behind a genuinely killable boundary.

The goal is not “make current complexity pass tests.” The goal is to recover the stable user's simple contract while retaining only proven safety improvements.

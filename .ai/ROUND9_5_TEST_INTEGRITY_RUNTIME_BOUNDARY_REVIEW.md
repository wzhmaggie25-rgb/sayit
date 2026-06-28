# Round 9.5 Independent Review — Test Integrity and Runtime Boundaries

> Date: 2026-06-29
> Reviewed branch: `feature/silent-learning-stabilization`
> Reviewed HEAD: `3d6549faddb58733517b82518d1c111c72eae904`
> Baseline: `a9ff7b0cabaa3faea28182c6755d367df60d5e66`

## Decision

**Round 9.4 is rejected. Do not begin user validation and do not resume feature development.**

The commit contains useful partial fixes, notably removal of Python `force=True`, correction of the stale `editable` branch, and monotonic arithmetic in parts of the pipeline. However, the claimed `42/42 PASS` does not demonstrate the requested production guarantees. Several new tests explicitly accept known-bad behavior, inspect source text rather than executing production paths, or leave permanent blocked threads behind.

The current status must return to `ZCODE_READY`.

---

## P0-1 — The test report is materially inaccurate

The names recorded in `.ai/TEST_RESULTS.md` do not match the actual test functions in the committed files. Examples:

- the report lists `test_native_dll_no_key_pressed_conditional_release`, but `tests/test_modifier_release_regression.py` contains no native-DLL runtime test;
- the report lists `test_remaining_never_negative`, but the actual third ASR test asserts that engine 2 **is called with the stale original remaining value**;
- the report lists production-handler behavior, but `frontend/_test_production_handler.js` only reads `main.js` as text.

The full-suite result is written as “All PASS” without an exact pass/skip/fail count or duration.

Required evidence files were also omitted:

- `.ai/ROUND9_4_SELF_REVIEW.md` was not created;
- `.ai/PROJECT_STATE.md` was not updated;
- `.ai/CURRENT_TASK.md` still states the old commit `a9ff7b0...`, not actual HEAD `3d6549f...`.

---

## P0-2 — Streaming stop isolation creates an unbounded thread leak

`DashScopeStreamingASRSession._exec_stop()` creates a fresh `ThreadPoolExecutor(max_workers=1)` for every call, submits `recognition.stop()`, then calls `shutdown(wait=False)`.

A running Python thread cannot be cancelled by `Future.cancel()`. If `stop()` never returns:

- the executor worker remains alive;
- every later timeout can create another permanently blocked worker;
- process/interpreter shutdown can wait for ThreadPoolExecutor workers;
- the design avoids one poisoned shared worker by accumulating one poisoned worker per failure.

The new tests use `time.sleep(999)` inside executor workers but only check that later calls use different executors. They do not assert thread growth, backend shutdown, callback isolation, or cleanup. Therefore they prove cross-session bypass, not bounded cleanup.

This directly violates the Round 9.4 acceptance requirement.

---

## P0-3 — The global ASR deadline is still not a hard runtime boundary

Partial improvement: `AsrCascade.transcribe()` subtracts elapsed time between engines.

Remaining blockers:

1. `_get_engine(level_name)` runs **before** remaining time is recomputed. Lazy local-model construction can therefore consume unbounded time outside the deadline.
2. `OnnxLocalASR.transcribe()` only checks whether remaining is already `<= 0`; ONNX/PyTorch inference then runs synchronously with no bound.
3. DashScope batch ASR still runs `Recognition.call()` in a new ThreadPoolExecutor. Timeout + `future.cancel()` cannot stop a running call, so repeated provider hangs accumulate workers.
4. Streaming `finish()` still uses `time.time()` rather than `time.monotonic()`.
5. No test proves streaming + cloud fallback + local load/inference stays within one absolute deadline with no surviving worker.

The third test in `tests/test_asr_deadline_global.py` is especially invalid: despite its comments saying engine 2 should be skipped, it asserts engine 2 **was called** and received approximately the original `5.0` seconds. That is the bug, not the desired behavior.

---

## P0-4 — Modifier release is only partially fixed

### Python injector

Removing `force=True` is useful, but `_release_modifiers()` still loops through left, right, and generic aliases independently:

- `VK_RMENU`, `VK_LMENU`, `VK_MENU`;
- left/right/generic Ctrl;
- left/right/generic Shift.

On Windows, one physical modifier may make both a side-specific and generic `GetAsyncKeyState` appear down. Current code can therefore synthesize duplicate releases for one physical key. It also emits `wScan=0` and no extended-key flag for RAlt.

### Native helper

`ConditionalReleaseAlt()` still loops through all three Alt aliases and may release duplicates. The earlier pre-emptive path still separately releases `VK_MENU` and `VK_LMENU` during a physical RAlt event.

Missing required protections:

- no fixed SayIt `dwExtraInfo` marker;
- no exact side-specific scan/extended flags;
- no native runtime test export verifying zero events when up and one correct event for RAlt;
- no controlled Win32 Edit/RichEdit 10-run exact-text test;
- no Chinese-IME evidence.

Source compilation alone does not prove the running process loaded the rebuilt DLL. GitHub contains source changes but no verifiable runtime identity/hash evidence for the locally loaded DLL.

---

## P0-5 — Frontend tests still do not execute the production event handler

`frontend/_test_production_handler.js` says it “cannot require” `main.js`, reads the file as text, and checks for substrings. It does not execute the WebSocket message handler, timers, window adapter, result-card state, or stale-session guards.

It also explicitly treats bad architecture as passing conditions:

- asserts `pipeline_done` and `pipeline_terminal` remain separate switch cases;
- only checks that `isSessionTerminal(` appears in source;
- confirms `_test_result_card_race.js` still duplicates state instead of importing production logic.

Production code still has these violations:

- `isSessionTerminal(evt.event)` is called only in a no-op block;
- legacy `pipeline_done` still stops the watchdog and calls `sayitOnPipelineDone`, so it still owns canonical session reset;
- watchdog timeout still clears `pendingResultCardPayload`, contrary to the preservation requirement;
- there is no exported session controller/reducer used by both `main.js` and tests.

---

## P0-6 — Per-session hotkey diagnostics remain unfixed

Only `terminal_count` was moved into `_emit_terminal()`.

`application/orchestrator.py` was not modified. It still copies these fields after `pipeline.run()` returns:

- hotkey start;
- hotkey stop;
- ignored toggle;
- native emitted;
- fallback stop.

But `RecordingPipeline.run().finally` already wrote the `[SESSION]` log before returning. The logged fields therefore remain their initialized zero values.

The copied counters are also cumulative process totals, not per-session deltas. No baseline is captured at session start.

The new terminal test does not verify emitted log text. One test contains a loop with no assertion; another explicitly asserts the source still contains `'?'` defaults. These tests cannot prove diagnostics correctness.

---

## P0-7 — Exactly-one terminal coverage is incomplete

The new tests do not run the real orchestrator wrapper for all required outcomes. Many checks are source-string inspections rather than event-count assertions.

Missing real-path proof includes:

- database/history exception;
- uncaught exception through `_pipeline_wrapper`;
- abort/cleanup failure;
- every failure path asserting `len(pipeline_terminal_events) == 1`;
- final diagnostic line asserting `terminal_count == 1` plus correct per-session counter deltas.

---

## P1 — No-target metadata can still be stale

`_inject_locked()` calls `_assess_target_editability()` and can return `no_editable_target` before refreshing `last_target_hwnd/proc/class/title`.

Result-card eligibility later consults the injector's last target metadata, so a prior SayIt-owned target can influence the current no-target decision.

Current target metadata must be refreshed or explicitly cleared before every early return.

---

## P1 — Other correctness/documentation issues

- `ai_degraded` is set `True` on the successful AI-correction branch.
- One giant commit was used instead of logical checkpoints requested by the task.
- Test comments repeatedly say “current code is buggy” after the supposed fix, making future audit unreliable.
- The task required no relevant Windows runtime skip, but no exact skip list/count is documented.

---

## Development Gate

Do not run user validation yet. Do not add release, login, payment, updater, installer, subscription, or other product features.

Feature development may resume only after:

1. false-positive tests are replaced by direct production-path tests;
2. blocking ASR/streaming operations have a genuinely killable boundary;
3. modifier event generation is side-specific and deduplicated;
4. one production frontend controller is used by both `main.js` and tests;
5. per-session diagnostics are logged after correct delta calculation;
6. ChatGPT independently accepts the next commits;
7. a short physical Notepad/RAlt validation passes.

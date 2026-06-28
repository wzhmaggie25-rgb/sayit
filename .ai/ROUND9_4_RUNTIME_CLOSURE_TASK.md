# Round 9.4 P0 Runtime Closure Task

> Executor: ZCode GUI → Claude Code
> Branch: `feature/silent-learning-stabilization`
> Read first: `.ai/ROUND9_4_RUNTIME_CLOSURE_REVIEW.md`
> Start from the latest remote branch head. Do not reset or discard Round 9.3.

## Mission

Complete the final runtime-stability closure in one development pass. Fix the reproduced modifier-garbage regression and close the production/test gaps left by Round 9.3.

This is a **stabilization task only**. Do not add new product features.

At completion, the only permitted remaining work is a short user physical validation. Final state must be `BLOCKED_USER_VALIDATION`, never `DONE`.

---

## Safety Rules

1. Work only on `feature/silent-learning-stabilization`.
2. Do not merge `main`.
3. No force push, `reset --hard`, `git clean`, destructive checkout, or rewriting backup history.
4. Do not modify/delete tag `local-working-2026-06-25` or backup commit `0d69a98`.
5. Do not read or alter real user database contents, dictionary entries, history text, audio transcripts, clipboard contents, API keys, or personal files.
6. Tests may use generated text only, for example `SayItRound94Test` and `测试文本九四`.
7. Do not launch Agent Bridge. The user is using ZCode GUI only.
8. Do not solve the garbage bug by filtering known strings such as `FEVHLBIGKOPS` or `fevhlbigktcps`.
9. Do not weaken assertions merely to make tests pass.
10. Preserve the verified non-destructive injection and clipboard guarantees from earlier rounds.

---

## Phase A — Add Failing Production-Path Tests First

Before implementation, add tests that fail on the current branch and directly exercise the production functions/classes that will be changed.

### A1. Modifier release regression

Add a dedicated test module, for example `tests/test_modifier_release_regression.py`.

Required cases:

1. All modifiers physically up:
   - call production `Injector._release_modifiers()`;
   - assert `SendInput` is called zero times.
2. `force=True` compatibility path, if retained:
   - it must still call `SendInput` zero times when all keys are up;
   - `force` must never mean “release unpressed keys”.
3. Only RAlt physically down:
   - emit only the minimum correct RAlt release sequence;
   - do not emit unrelated LAlt/generic Alt/Win/Ctrl/Shift releases;
   - no duplicate aliases for one physical key.
4. Multiple genuinely pressed modifiers:
   - release only those pressed;
   - deterministic order;
   - no duplicate release for generic + left/right aliases.
5. Ten consecutive clean calls with all keys up:
   - zero keyboard events.
6. Production injection into a controlled temporary Win32 Edit/RichEdit target:
   - injected text equals expected text exactly;
   - no prefix/suffix garbage;
   - run at least 10 times.
7. Native helper test path:
   - `ForceReleaseAlt` replacement must not emit release events for keys reported up;
   - verify injected/synthetic events cannot re-enter as physical toggles.

Tests must inspect actual generated `INPUT`/VK/scan/flags or a native test export. Do not only assert a mock method returned `True`.

### A2. Tri-state production routing

Add tests that call production `_inject_locked()` and prove:

- `editable_verified` reaches `_inject_win32_selection_aware()` for a real/controlled Edit target;
- `editable_probable` proceeds to strategy selection;
- `no_editable_verified` is the only state that returns `no_editable_target` before dispatch;
- no stale literal `"editable"` remains in executable state comparisons;
- target process/class/title metadata is current for every result-card eligibility decision.

### A3. True global ASR deadline

Add tests with an absolute monotonic deadline and fake engines that consume real wall-clock time.

Required cases:

1. Engine 1 consumes part of the budget and fails; engine 2 receives the recomputed smaller remaining time.
2. Engine 1 exhausts the deadline; engines 2 and 3 are never called.
3. Lazy local-model construction is inside the budget.
4. Local ONNX/PyTorch inference cannot outlive the total deadline from the pipeline's perspective and cannot leave an unbounded worker behind.
5. A cloud SDK call that never returns does not leave a growing thread/process count over repeated sessions.
6. Total streaming + batch cascade elapsed time stays within budget plus a small documented scheduler tolerance.

Do not accept a test that checks only that a `remaining` parameter exists.

### A4. Poisoned streaming stop

Add a test where `recognition.stop()` blocks forever on an event that is never released.

Prove all of the following:

- current session returns/terminalizes within its budget;
- a second and third session can still stop normally;
- thread/process count does not grow per failure;
- backend/interpreter shutdown is not blocked by a poisoned worker;
- callbacks and audio-queue ownership from the failed session cannot affect a later session.

### A5. Frontend real-handler tests

Refactor as needed so tests invoke the same event reducer/handler used by `main.js`.

Required cases with fake timers and fake window adapters:

- 5-minute recording: no watchdog timeout while recording;
- `recording_stopping`: watchdog starts exactly once;
- `pipeline_terminal` for all five outcomes stops watchdog and resets float correctly;
- `pipeline_done` alone does not perform the canonical terminal reset;
- WS close/error terminates the visible waiting state and preserves any already-created result-card payload;
- show → terminal → renderer-load race preserves exact text;
- stale previous-session events cannot alter the active session;
- test imports/calls production handler, not copied switch logic.

### A6. Exactly-one terminal and diagnostics

Using the real `SayitOrchestrator` wrapper path where practical, prove exactly one `pipeline:terminal` event for:

- success;
- no target;
- attempted unverified;
- audio start failure;
- too-short audio;
- streaming failure + batch failure;
- injector exception;
- database/history exception;
- uncaught pipeline exception;
- stop/abort path.

Every assertion must be `== 1`, not `>= 1`.

Also prove the final `[SESSION]` diagnostic line contains per-session deltas for start, stop, ignored toggle, native emit, fallback stop, and terminal count.

---

## Phase B — Fix Modifier Release at the Source

### B1. Python injector

Refactor `Injector._release_modifiers()` so the following invariant is impossible to violate:

> SayIt must never synthesize a key-up for a modifier that is not currently down for the corresponding physical/logical key.

Requirements:

1. Remove `force=True` bypass semantics. Either delete the argument or redefine it so physical-state checks are still mandatory.
2. Do not release all left/right/generic aliases for one pressed key.
3. Deduplicate aliases. One physical RAlt press must not produce three Alt key-up events.
4. Use correct scan/extended flags where required for RAlt.
5. Log only redacted diagnostics:
   - reason;
   - number of releases;
   - released VK/scan/flags;
   - before/after boolean states.
   Never log user text.
6. Update every terminal-before/after-paste call site.
7. Ensure ordinary Notepad/editor injection performs no modifier preamble when no modifier is down.

### B2. Native keyboard helper

Replace unconditional `ForceReleaseAlt()` behavior in `native/context_helper/src/keyboard_helper.cpp`.

Requirements:

- only release an Alt key whose corresponding state is actually down;
- avoid emitting LAlt/generic Alt releases for a physical RAlt unless independently required and proven down;
- tag SayIt synthetic events with a fixed non-personal `dwExtraInfo` marker;
- the hook must ignore SayIt-generated events and all `LLKHF_INJECTED` events for toggle parsing;
- preserve RAlt swallowing so menus/characters do not leak to the foreground app;
- preserve one toggle per physical down edge and the existing fallback watcher contract;
- bump helper version/build id and rebuild the DLL through the repository's documented build path;
- add/update native test exports only under existing test-mode protections.

### B3. Regression proof

Use the controlled scratch target to prove:

- English keyboard layout: 10 injections, exact text only;
- Chinese IME active if safely automatable without altering user data: 10 injections, exact text only;
- paste path and SendInput path are both clean;
- RAlt start/stop parser tests remain green;
- no Alt-stuck/menu activation event is generated by test instrumentation.

If Chinese IME cannot be safely automated, document that single physical check for user validation; do not claim it passed.

---

## Phase C — Make Editability States Impossible to Drift

1. Replace raw state strings with module constants or an enum-like type shared by assessment and routing.
2. Fix the stale `if editability == "editable"` branch.
3. `editable_verified` must use the verified selection-aware Win32 insertion path when a focused Edit/RichEdit exists.
4. `editable_probable` must continue through known-app strategy selection.
5. Only positive proof of no target may produce `no_editable_verified`.
6. Unknown/UIA failure/read-only/inconclusive states remain probable, not verified absence.
7. Capture current foreground process/class/title before any result-card eligibility decision. Do not use previous-session metadata.
8. Preserve:
   - no destructive `SetValue`/`WM_SETTEXT`/DocumentRange selection;
   - no second injection after an unverified dispatch;
   - SilentMonitor only after `verified_success + target_verified + hwnd`.

---

## Phase D — Enforce One Absolute Monotonic ASR Deadline

1. Create one monotonic absolute deadline at the start of ASR finalization.
2. Pass the deadline, not a stale remaining snapshot, through:
   - streaming finish;
   - `AsrCascade`;
   - DashScope;
   - Volcengine v1/v3;
   - lazy local model load;
   - ONNX/PyTorch inference.
3. Recompute remaining time immediately before every blocking operation and before every fallback engine.
4. Skip later engines when remaining time is exhausted.
5. Replace `time.time()` deadline arithmetic with `time.monotonic()`.
6. Do not claim a hard deadline by merely calling `future.cancel()` on a running thread.
7. For SDK calls without a trustworthy native timeout, use an execution boundary that can actually be terminated, such as an isolated helper process. The chosen design must:
   - be bounded;
   - be cleaned up;
   - not accumulate workers;
   - not block backend shutdown;
   - avoid passing secrets through logs or command-line arguments.
8. Keep temporary audio files private and delete them on success, failure, timeout, and process termination.
9. Emit one terminal reason code that clearly distinguishes total-budget exhaustion from provider failure.

---

## Phase E — Make Streaming Finish/Abort Recoverable After a Permanent SDK Wedge

1. Remove or redesign the single `_STOP_EXECUTOR` poison point.
2. A running, blocked `recognition.stop()` must not permanently occupy the only cleanup worker.
3. Do not create an unbounded new thread per session.
4. Use a killable isolation mechanism or a provider-specific close path that has a real bound.
5. Introduce explicit session ownership/generation for audio chunk callbacks:
   - an old session may clear only its own callback;
   - an old session may never consume/send chunks belonging to a new session.
6. On finish/abort, close the session exactly once and make later calls idempotent.
7. Ensure worker, queue, callback, socket/session handle, and cleanup boundary reach a known final state.
8. Preserve pipeline terminal emission even if cleanup fails.

---

## Phase F — Use One Frontend Session State Machine in Production and Tests

1. Move the canonical event transition logic into one production module.
2. `main.js` must call that module for recording, stopping, terminal, error, and WS disconnect events.
3. Remove duplicate watchdog constants and unused imports.
4. Watchdog starts only at `recording_stopping`.
5. `pipeline_terminal` is the canonical session terminal reset.
6. Legacy `pipeline_done` may still be forwarded for history/UI compatibility, but must not independently own/reset the active session.
7. All five terminal outcomes must leave the float in a stable non-waiting state.
8. WS close/error must visibly exit waiting and schedule reconnect.
9. Do not clear a valid result-card payload on terminal/error/watchdog; clear only on explicit close, copy completion, or a new session.
10. Tests must invoke the same exported handler/reducer that `main.js` invokes.

---

## Phase G — Terminal Ownership and Per-Session Diagnostics

1. Keep `RecordingPipeline._emit_terminal()` as the sole terminal emitter and latch owner.
2. Real orchestrator exception handling must call the same method.
3. Add a top-level pipeline exception boundary if needed so database/history or other late exceptions still terminalize exactly once.
4. Populate `final_text_available` from the actual final usable text state.
5. Capture orchestrator/native counter baselines at session start and compute deltas at session end.
6. Populate metrics before the `[SESSION]` line is written.
7. Required per-session fields:
   - `hotkey_start_count`;
   - `hotkey_stop_count`;
   - `toggle_ignored_count`;
   - `native_emitted_count`;
   - `fallback_stop_count`;
   - `terminal_count`.
8. `terminal_count` must be exactly 1 for every completed/failed/aborted session.
9. Diagnostics must contain no user text, clipboard content, audio, API keys, or history text.

---

## Phase H — Full Gates and Evidence

Run all applicable checks on the local Windows environment.

Minimum required commands/evidence:

```text
python -m pytest tests/ -v --timeout=45
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
node frontend/_test_result_card_race.js
node frontend/_test_session_lifecycle.js
```

Also run the new modifier, ASR deadline, streaming poison, frontend production-handler, terminal, and controlled Win32 integration tests explicitly.

Required acceptance results:

1. Zero failing tests.
2. No relevant module skipped merely because it is difficult; Windows runtime modules must execute on this Windows machine.
3. Controlled Edit/RichEdit injection is exact for 10 consecutive runs.
4. No generated modifier event when all modifiers are up.
5. No stale `"editable"` executable comparison.
6. Each fallback engine receives recomputed deadline/remaining.
7. Permanent stop/SDK wedge test does not poison subsequent sessions or block shutdown.
8. Exactly one terminal event in every tested path.
9. Frontend test invokes the production event handler.
10. `[SESSION]` log shows correct per-session counter deltas.

---

## Deliverables

1. Production code and tests committed in logical checkpoints.
2. `.ai/ROUND9_4_SELF_REVIEW.md` containing:
   - each independent-review finding;
   - root cause;
   - exact production fix;
   - tests that would fail before the fix;
   - limitations honestly remaining;
   - checkpoint SHAs.
3. Update `.ai/TEST_RESULTS.md` with commands and exact pass/skip/fail counts.
4. Update `.ai/PROJECT_STATE.md` with Round 9.4 status.
5. Update `.ai/ZCODE_REPORT.md` with actual changed files and unresolved risks.
6. Update `.ai/CURRENT_TASK.md` to `BLOCKED_USER_VALIDATION` only after all gates pass.
7. Push all commits to `feature/silent-learning-stabilization`.

## Final Response Contract

At the end, report:

- final remote HEAD;
- commit list;
- exact tests and counts;
- whether native DLL was rebuilt and which build id loaded;
- whether controlled English and Chinese-IME injection gates actually ran;
- any remaining physical-only checks.

Do not state “all fixed” or “no remaining issues” unless the permanent-wedge, production-handler, modifier-event, and exact-terminal gates all passed.

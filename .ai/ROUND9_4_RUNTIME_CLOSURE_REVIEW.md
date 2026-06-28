# Round 9.4 Runtime Closure — Independent Review

> Date: 2026-06-28
> Branch: `feature/silent-learning-stabilization`
> Baseline reviewed: Round 9.3 implementation through `344b52f` plus the following documentation commit.

## Decision

**Round 9.3 is not accepted for user validation and the project is not ready for new product requirements yet.**

The user reproduced a prior production bug while testing: normal text injection produced the fixed garbage prefix `FEVHLBIGKOPS`. This is the same failure family documented in `CHANGELOG.md` on 2026-06-13 (`fevhlbigktcps`): synthetic modifier key-up events escaped as ordinary characters.

Round 9.3 did improve watchdog timing, terminal payloads, editability fallback, and ASR budget plumbing, but several production-path gaps remain.

## P0 Findings

### P0-1 — Modifier release regression is still reachable

- `Injector._release_modifiers(force=True)` bypasses `GetAsyncKeyState` and emits key-up events for every entry in `_MODIFIER_RELEASE_ORDER`.
- The order contains 12 virtual-key entries; the reproduced garbage contains 12 characters.
- Current terminal paths still call `force=True` before paste, after successful paste, and after failed paste.
- Native `ForceReleaseAlt()` also sends unconditional key-up events for `VK_RMENU`, `VK_LMENU`, and `VK_MENU`.
- The 2026-06-13 fix explicitly required never sending key-up for an already-up modifier.

This must be fixed at the event source. Filtering the text `FEVHLBIGKOPS` is forbidden.

### P0-2 — Tri-state editability rename left a dead production branch

Round 9.3 renamed editability states to:

- `editable_verified`
- `editable_probable`
- `no_editable_verified`

But `_inject_locked()` still gates selection-aware Win32 insertion with:

```python
if editability == "editable":
```

Therefore the verified Edit/RichEdit path is unreachable in production. Tests passed because they did not assert that the real renamed state reaches `_inject_win32_selection_aware()`.

All state names must be centralized and every production branch must use them consistently.

### P0-3 — ASR total budget is not globally enforced across the cascade

- Pipeline computes one remaining value and passes it once to `AsrCascade.transcribe()`.
- `AsrCascade.transcribe()` passes that same stale value to every engine; it does not recompute remaining time after each failure.
- Local model lazy loading and ONNX/PyTorch inference are only skipped when the initial `remaining <= 0`; they are not bounded by the deadline.
- DashScope wraps an uninterruptible SDK call in a new `ThreadPoolExecutor`. Timing out and cancelling the future does not terminate a running call, so background work can survive the budget.
- Deadline code says monotonic but uses `time.time()` in multiple places.

A hard budget requires an absolute monotonic deadline and a genuinely interruptible execution strategy.

### P0-4 — Streaming stop executor can be permanently poisoned

`_STOP_EXECUTOR(max_workers=1)` bounds the caller wait, but a running `recognition.stop()` cannot be cancelled. One permanent SDK wedge occupies the only worker forever; all later finish/abort calls queue behind it and time out. The current tests:

- use finite 5s/30s waits rather than a never-released block;
- count only daemon threads named `dashscope-streaming-asr`;
- do not count or terminate the executor worker;
- do not prove clean interpreter/backend shutdown after a poisoned stop.

The implementation must not claim leak-free cleanup while a live unkillable worker remains.

### P0-5 — Frontend tests are not wired to the production event handler

- `_session_lifecycle.js` contains pure decisions, but `main.js` manually duplicates watchdog behavior and a second `SESSION_WATCHDOUT_MS` constant.
- `decideWatchdogAction()` and `isSessionTerminal()` are imported but unused.
- The test file explicitly says it tests pure functions only.
- `pipeline_done` still directly resets the float before `pipeline_terminal`, so terminal is not truly the sole frontend session reset.

The real handler used by `main.js` must be testable and invoked by the tests; duplicated decision logic must be removed.

### P0-6 — Required hotkey diagnostics are written after the session log

`RecordingPipeline.run().finally` writes the `[SESSION]` log before returning. The orchestrator copies native/hotkey/fallback/terminal counters into `_session_metrics` only after `run()` returns. Therefore the emitted session log still contains zero/default values.

The counters are also cumulative process totals, not per-session deltas. This prevents the intended diagnosis of one physical recording cycle.

## P1 Test/Documentation Gaps

- Several terminal failure tests still assert `>= 1` instead of exactly one.
- The orchestrator uncaught-exception path is not exercised through the real wrapper/thread lifecycle.
- Some test comments still describe pre-fix code and can mislead later reviews.
- The self-review states “None. All gate tests pass” despite no live Windows/IME proof and the reproduced corruption.
- `BLOCKED_USER_VALIDATION` is invalid while the known runtime corruption remains.

## Development Gate

Do not start release, account, payment, subscription, updater, installer, or additional product features yet.

The project may resume feature development only after:

1. Round 9.4 code/tests pass;
2. the garbage-character regression is fixed at source;
3. one short Windows physical validation confirms clean Notepad injection and reliable RAlt start/stop;
4. ChatGPT independently reviews the resulting commits.

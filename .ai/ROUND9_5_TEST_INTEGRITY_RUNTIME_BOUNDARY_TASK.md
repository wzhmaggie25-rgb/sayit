# Round 9.5 P0 Task — Test Integrity and Killable Runtime Boundaries

> Executor: ZCode GUI → Claude Code
> Branch: `feature/silent-learning-stabilization`
> Read first: `.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_REVIEW.md`
> Starting HEAD includes the Round 9.5 review commit. Pull before editing.

## Mission

Replace the false-positive Round 9.4 gates with honest production-path tests and implement the missing runtime guarantees.

This is still stabilization work. Do not add product features.

Final state may become `BLOCKED_USER_VALIDATION` only when all gates below pass with exact evidence. Never set `DONE`.

---

## Safety Rules

- Work only on `feature/silent-learning-stabilization`.
- Do not merge `main`.
- No force push, `reset --hard`, `git clean`, destructive checkout, or backup-history rewrite.
- Do not modify stable backup commit `0d69a98` or tag `local-working-2026-06-25`.
- Do not read or alter real user history, database text, dictionary entries, audio content, clipboard content, API keys, or personal files.
- Test text must be synthetic.
- Agent Bridge stays off.
- Do not filter `FEVHLBIGKOPS` or any known garbage string.
- Do not make a blocked thread “acceptable” by renaming it, making it daemon, or excluding it from thread counts.
- Do not keep tests that assert known-bad behavior.

---

## Phase A — Repair Test Integrity Before Production Changes

Delete or rewrite misleading Round 9.4 tests. Every corrected test must fail against commit `3d6549f` for the intended reason.

### A1. ASR deadline tests

Rewrite `tests/test_asr_deadline_global.py` so it asserts desired behavior only:

- engine 2 receives a smaller recomputed remaining value;
- if engine 1 exhausts the deadline, engine 2 is not called;
- lazy local-engine construction is inside the deadline;
- local inference is inside the deadline;
- a cloud call that never returns leaves no surviving worker/process after timeout;
- total streaming + batch + local elapsed time is bounded by one monotonic deadline plus a small documented tolerance.

Remove the current assertion that engine 2 is called with stale `5.0` remaining.

### A2. Streaming poison tests

Rewrite `tests/test_streaming_poison.py` to use a genuinely never-returning operation and prove:

- first session terminalizes within budget;
- second and third sessions work;
- active thread/process count returns to baseline;
- backend/interpreter shutdown is not blocked;
- no old callback/queue can affect a later session.

The test must fail if one blocked worker is leaked per timeout.

### A3. Frontend production-handler tests

Replace source-string inspection with an exported production controller/reducer that is imported by both `main.js` and the test.

Tests must execute real transition logic with fake timers/window adapters for:

- 5-minute recording with no watchdog timeout;
- recording_stopping starts one watchdog;
- all five terminal outcomes stop watchdog and exit waiting;
- legacy pipeline_done does not own canonical terminal reset;
- WS close/error exits waiting and preserves valid result payload;
- show → terminal → renderer-load preserves exact text;
- stale session events are ignored;
- watchdog timeout does not destroy an already-created valid result payload.

### A4. Modifier/native tests

Add direct event-level tests for Python and the loaded native helper:

- all modifiers up → zero events;
- physical RAlt → exactly one side-specific RAlt release with correct scan/extended flags;
- generic aliases do not produce duplicates;
- SayIt-generated events carry a fixed `dwExtraInfo` marker;
- injected events never emit toggles;
- controlled Win32 Edit/RichEdit target receives exact synthetic text 10 consecutive times with no prefix/suffix;
- runtime diagnostics prove the loaded DLL version/build/path/hash.

### A5. Terminal and diagnostics tests

Use the real orchestrator wrapper where possible. For every required path, assert exactly one terminal event:

- success;
- no target;
- attempted unverified;
- audio start failure;
- too short;
- ASR budget exhausted;
- cloud + local failure;
- injector exception;
- database/history exception;
- uncaught pipeline exception;
- cleanup/abort failure.

Capture the emitted `[SESSION]` log and assert real per-session deltas, not initialized defaults or cumulative totals.

### A6. Test-report integrity gate

Add a script/test that compares `.ai/TEST_RESULTS.md` listed test names/counts with actual collected tests or command output. It must fail on invented or stale test names.

---

## Phase B — Implement a Genuinely Killable Blocking-Operation Boundary

A Python thread is not killable. `Future.cancel()` is not a solution after work begins.

### Required design

Use one of these acceptable approaches:

1. provider-supported cancellation/close with a proven native timeout; or
2. an isolated child process that owns the blocking SDK/session and can be terminated and joined.

If the installed DashScope SDK has no trustworthy bounded close/cancel, move the **entire relevant SDK operation/session ownership** into a child process. Do not attempt to pass a live recognition object to another process.

### Required coverage

The killable boundary must cover:

- streaming start/send/finalize/abort when provider stop can wedge;
- DashScope batch `Recognition.call()`;
- lazy local-model load;
- ONNX/PyTorch inference.

### Process/IPC constraints

- Do not put API keys or user text in command-line arguments or logs.
- Use IPC/pipe/queue with structured messages.
- Keep logs redacted.
- On deadline: terminate, join, close handles, delete temp files, and return a typed timeout/failure.
- Reuse a healthy persistent worker only if it can be forcibly replaced after timeout; otherwise use a per-request worker with strict cleanup.
- No zombie processes and no surviving worker threads.
- Backend shutdown must complete after a simulated permanent provider wedge.

---

## Phase C — One Absolute Monotonic Deadline Everywhere

- Create one absolute `time.monotonic()` deadline at ASR finalization start.
- Pass the absolute deadline through streaming, cascade, provider worker, local-model load, and inference.
- Recompute remaining immediately before every blocking operation.
- `_get_engine()` lazy construction must not happen before the budget check.
- Do not call another engine when remaining `<= 0`.
- Distinguish `asr_total_budget_exceeded` from provider-specific failures.
- Replace remaining `time.time()` deadline arithmetic in streaming finish/abort.
- Prove total elapsed time across all fallback stages stays bounded.

---

## Phase D — Correct and Deduplicate Modifier Releases

### Python

Create a canonical physical-modifier representation. Do not independently release generic and side-specific aliases.

Requirements:

- one physical RAlt → one RAlt key-up;
- correct scan code and `KEYEVENTF_EXTENDEDKEY` for RAlt;
- deterministic order for multiple physical modifiers;
- no release for an up key;
- log reason + released VK/scan/flags/count only, never user text;
- remove stale alias-loop behavior.

### Native

Update both native keyboard implementations consistently:

- side-specific conditional release;
- fixed non-personal `dwExtraInfo` marker for SayIt synthetic events;
- hook parser ignores SayIt marker and injected events for toggle generation;
- remove pre-emptive generic/LAlt duplicate release for a physical RAlt;
- preserve RAlt swallowing and one toggle per physical down edge;
- bump helper version/build id;
- rebuild using documented build commands;
- verify the actual runtime loader loads the new file and report its path, version, build id, and SHA-256.

Do not claim native success from source grep alone.

---

## Phase E — One Production Frontend Session Controller

Extract a production module, for example `frontend/session_controller.js`, that owns:

- active session id;
- watchdog lifecycle;
- terminal transition;
- WS disconnect transition;
- result-card payload preservation;
- stale-event rejection;
- float action decisions.

`main.js` must call this module for the real WebSocket event path. Tests import the same module.

Rules:

- watchdog starts only at `recording_stopping`;
- `pipeline_terminal` is canonical terminal ownership;
- legacy `pipeline_done` may be forwarded for compatibility but must not reset session/watchdog/float independently;
- `isSessionTerminal` must affect behavior, not appear in a no-op block;
- timeout/error/terminal must not erase a valid pending result-card payload;
- duplicate constants/state logic must be removed.

---

## Phase F — Correct Per-Session Diagnostics and Terminal Ownership

- Capture orchestrator/native/fallback counter baselines at session start.
- Compute deltas at session end.
- Populate metrics before the final session log is emitted, or move final session logging to the owner that has complete metrics.
- Do not log cumulative totals as per-session values.
- Required fields: start, stop, ignored toggle, native emitted, fallback stop, terminal count.
- `terminal_count` must be exactly 1.
- Keep `RecordingPipeline._emit_terminal()` as sole terminal latch/emit owner.
- Real orchestrator exception path must use it.
- Add a top-level failure boundary so late database/history exceptions still terminalize exactly once.
- Fix the successful AI branch incorrectly setting `ai_degraded=True`.

---

## Phase G — Clear Stale Target Metadata

Before editability assessment/early return:

- capture or clear current foreground hwnd/proc/class/title;
- never leave previous-session target metadata on a no-target result;
- result-card SayIt-window eligibility must use current-session metadata only;
- centralize editability states as constants/enum-like values to prevent string drift.

Preserve all non-destructive injection and SilentMonitor gates.

---

## Phase H — Evidence, Documentation, and Commits

Run full Windows gates and record exact output:

```text
python -m pytest tests/ -v --timeout=45
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
node frontend/_test_result_card_race.js
node frontend/_test_session_lifecycle.js
node frontend/_test_production_handler.js
```

Also run explicit killable-boundary, modifier-native, controlled Win32 injection, exact-terminal, and diagnostics tests.

Acceptance requires:

- exact pass/skip/fail counts and duration;
- no invented test names;
- no relevant Windows module skipped;
- no blocked thread/process after permanent wedge tests;
- backend test process exits normally;
- 10 exact controlled Win32 injections;
- actual loaded native helper identity/hash;
- exactly one terminal for every required path;
- emitted session log contains correct deltas;
- frontend tests import the same production controller used by `main.js`.

Create/update:

- `.ai/ROUND9_5_SELF_REVIEW.md`;
- `.ai/TEST_RESULTS.md`;
- `.ai/PROJECT_STATE.md`;
- `.ai/ZCODE_REPORT.md`;
- `.ai/CURRENT_TASK.md`.

Use logical checkpoint commits, then push.

Only after every gate passes may `.ai/CURRENT_TASK.md` become `BLOCKED_USER_VALIDATION`. Otherwise leave it `ZCODE_READY` and document blockers honestly.

Final report must include remote HEAD, commit list, exact test counts, worker/process cleanup evidence, loaded DLL identity/hash, and any genuinely physical-only check remaining.

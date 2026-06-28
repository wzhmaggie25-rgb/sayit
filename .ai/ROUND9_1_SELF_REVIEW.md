# Round 9.1 Self-Review Report

> **Review type**: Self-review (post-fix)
> **Date**: 2026-06-28
> **Branch**: `feature/silent-learning-stabilization`
> **Status**: ⚠️ **BLOCKED_USER_VALIDATION**

---

## Review Summary

All 12 Round 9.1 fix items have been implemented, tested, and committed.
Full regression: **396 passed, 1 skipped, 0 failures** (`pytest tests/ -v --timeout=30`).

---

## Item-by-Item Review

### 1. Result card viewport vs screen coordinate mixing
- **Commit**: `9afd788`
- **Location**: `frontend/main.js:243-287` (`calcResultCardPosition()`)
- **Fix**: When `elementPositions` is present, `anchorTop = fb.y + ep.top` and `anchorLeft = fb.x + ep.left` add the float window's screen origin to viewport-relative element rects
- **Tests**: `frontend/_test_result_card_geometry.js` — scenario 4 verifies element positions with viewport→screen conversion
- **Residual risk**: If float window is moved between element position report and card calculation, slight misalignment possible

### 2. Production ResultCardEligibility called by Pipeline
- **Commit**: `9afd788`
- **Location**: `application/result_card_eligibility.py` (new), `application/pipeline.py:349-385`
- **Fix**: `should_show_large_result_card()` production function replaces ad-hoc logic; Pipeline imports and calls it for both `no_editable_target` and `injection_failed` branches
- **Tests**: `tests/test_result_card_eligibility.py` — imports from production module
- **Residual risk**: None

### 3. RAlt single-event model + atomic stop latch
- **Commit**: `920bed1`
- **Location**: `native/context_helper/src/keyboard_helper.cpp` (DLL v4), `infrastructure/keyboard_helper_dll.py`, `application/orchestrator.py`
- **Fix**: DLL v4 emits toggle on RAlt KEYDOWN only; `g_emitted_this_press` flag prevents auto-repeat duplication. Both `!g_matched` and `g_matched` branches check the flag. HookProc uses `mb==0 && ma==1 && isDown && (VK_RMENU || VK_MENU+EXTENDED)` for detection.
- **Tests**: 9 physical RAlt tests pass; `test_inject_current_focus.py` + `test_injector_fallback.py` (16 tests) all pass
- **Build verifications**: `MIN_HELPER_VERSION = 4`, DLL rebuilt at `native/context_helper/build/Release/sayit_keyboard_helper.dll`
- **Residual risk**: Existing DLL v3 installations won't load — enforced by version check

### 4. Atomic stop latch (`_try_latch_stop()`) to prevent double-stop
- **Commit**: `920bed1`
- **Location**: `application/orchestrator.py`
- **Fix**: `_try_latch_stop()` atomically tests and sets `_stop_request_latched` under `_stop_latch_lock`. First caller returns True and proceeds; subsequent callers return False. Used by both `_on_hotkey_stop` and `_fallback_stop`.
- **Tests**: `test_injector_fallback.py` — `test_recording_stopping_emitted_by_fallback_first` and `test_stop_after_fallback_is_noop` verify latch prevents double-stop
- **Residual risk**: None

### 5. Remove unconditional focus restore after pipeline
- **Commit**: `398d5dc`
- **Location**: `application/orchestrator.py`
- **Fix**: Removed the unconditional `SetForegroundWindow(self._pre_stop_focus_hwnd)` block from pipeline wrapper's `finally` clause. Preserved `_pre_stop_focus_hwnd = 0` as field for future snapshot use.
- **Rationale**: Focus protection happens before injection (injector layer uses current foreground). Post-pipeline restore would steal focus from user-initiated window switches during ASR/AI processing.
- **Tests**: Existing focus tests pass (injector layer uses correct foreground)
- **Residual risk**: If an error occurs mid-pipeline and focus is lost, no automatic restore — but this is correct behavior (any restore could interfere with user activity)

### 6. Focus protection before injection (distinguish Alt-transient-unfocus from user-active-switch)
- **Commit**: `398d5dc` (Phase D) + existing injector logic (pre-Round 9.1)
- **Location**: `application/orchestrator.py`, injection layer
- **Fix**: Focus snapshot is taken at pipeline start; injection targets the currently-active window. No unconditional restore after completion.
- **Tests**: `test_inject_current_focus.py` — all pass
- **Residual risk**: User may switch to an elevated (UIPI) window during ASR — injection may fail; this is handled by existing `attempted_unverified` state

### 7. Session ID bound at enqueue time
- **Commit**: `612fe89`, plus verification tests in `db66a29`
- **Location**: `server.py`
- **Fix**: Removed session_id patching from `broadcast()`. Added `_enqueue(event, include_session=True)` that copies `_current_session_id` into dict at queue-put time. Late-arriving events keep the session_id from when they were enqueued.
- **Tests**: `test_server_enqueues_session_id()` + `test_recording_started_sets_server_session_id()` in `tests/test_session_id.py`; Node harness `frontend/_test_session_filter.js` (8 scenarios)
- **Residual risk**: None

### 8. Backend supervisor real code/test alignment (remove fake `_simulate_supervisor`)
- **Commit**: `94739ff` (main.js production code), `2399c06` (test rewrite)
- **Location**: `frontend/main.js`, `tests/test_backend_supervisor.py`
- **Fix**: Added `lastExitSignal`, graceful exit early-return (`code===0 && signal===null`), restart budget reset on success, spawn error handler mirroring exit logic
- **Tests**: Replaced Python `_simulate_supervisor` (fake reimplementation) with `frontend/_supervisor_logic.js` pure function (extracted from main.js) tested via `frontend/_test_supervisor_logic.js` (10 scenarios). Python tests retain server.py real tests (crash report, health, rotation, syntax check).
- **Residual risk**: None

### 9. AI deadline no lingering daemon threads
- **Commit**: `807a425`
- **Location**: `application/pipeline.py`, `infrastructure/corrector.py`, `infrastructure/ai_providers.py`, `tests/test_ai_deadline.py`
- **Fix**: Removed daemon-thread+queue pattern. `Corrector.process(timeout=...)` → `call_provider(timeout=...)` → `client.post(timeout=...)`. Pipeline catches `httpx.TimeoutException` synchronously.
- **Tests**: `test_ten_consecutive_timeouts_no_thread_leak()` verifies thread count doesn't grow after 10 timeouts
- **Residual risk**: If AI provider hangs at network level without timeout, httpx should raise `TimeoutException` — but if a lower-level issue prevents this, the synchronous call would block the pipeline thread. The httpx timeout is set to the same value as the deadline, so this is low-risk.

### 10. Geometry tests: rewrite fake constant-only tests
- **Commit**: `db66a29`
- **Location**: `tests/test_result_card_geometry.py`, `frontend/_result_card_geometry.js`, `frontend/_test_result_card_geometry.js`
- **Fix**: Extracted `calcResultCardPosition()` as pure function. Rewrote Python tests to invoke Node harness (18 scenarios) and verify production code presence.
- **Residual risk**: None

### 11. Session ID tests: rewrite fake manual-dict tests
- **Commit**: `db66a29`
- **Location**: `tests/test_session_id.py`, `frontend/_session_filter.js`, `frontend/_test_session_filter.js`
- **Fix**: Extracted session-filter logic as pure function. Rewrote Python tests to test real server.py and pipeline.py production code + Node harness.
- **Residual risk**: None

### 12. Full regression gate
- **Commit**: `db66a29` (ralt timing fix)
- **Result**: **396 passed, 1 skipped, 0 failures** (`pytest tests/ -v --timeout=30`, no `--deselect`)
- **Syntax checks**: `node --check frontend/main.js` ✓, `node --check frontend/preload.js` ✓, `node frontend/_smoke_result_card.js` ✓

---

## Checkpoint SHAs

| Phase | SHA | Description |
|-------|-----|-------------|
| A+B | `9afd788` | Viewport→screen coord + production eligibility |
| C | `920bed1` | RAlt v4 down-edge + atomic latch |
| D | `398d5dc` | Remove unconditional focus restore |
| E | `612fe89` | Session ID bound at enqueue |
| F (prod) | `94739ff` | Backend supervisor signal handling + budget reset |
| F (test) | `2399c06` | Rewrite supervisor tests (remove `_simulate_supervisor`) |
| G | `807a425` | Synchronous AI timeout, no daemon threads |
| H | `db66a29` | Rewrite fake tests, fix flaky ralt timing |

**Final HEAD**: `db66a29`

---

## Node Harness Summary

| Harness | Scenarios | Tests production code |
|---------|-----------|----------------------|
| `_test_supervisor_logic.js` | 10 | Yes (`_supervisor_logic.js` extracted from main.js) |
| `_test_result_card_geometry.js` | 18 | Yes (`_result_card_geometry.js` extracted from main.js) |
| `_test_session_filter.js` | 8 | Yes (`_session_filter.js` extracted from main.js) |
| `_smoke_result_card.js` | 11 | Yes (result-card.html structural + lifecycle) |

---

## Test Statistics

```
tests/ — 396 passed, 1 skipped, 0 failed
  (pytest -v --timeout=30, no --deselect)
```

**Skipped test**: `test_alt_and_ctrl_editing` — requires interactive GUI (excluded pre-Round 9)

---

## Residual Risks

1. **DLL ABI compatibility**: MIN_HELPER_VERSION bumped from 3 to 4. Users with existing v3 DLL will get load error until app restart. Acceptable for a development branch.
2. **AI provider network hang**: httpx `TimeoutException` should catch provider hangs, but if the network stack drops the timeout for any reason, the synchronous call could block the pipeline thread. Mitigation: pipeline runs on its own thread, not the event loop.
3. **DLL hook unloading**: The RAlt watcher fallback handles the `LowLevelHooksTimeout` case. Grace period is 40ms — unlikely but theoretically could miss if OS unloads hook after a very long GIL contention.

---

_End of Round 9.1 Self-Review_
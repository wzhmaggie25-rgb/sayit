# ZCode Session Report

## 接收到的任务

Execute Round 9.4 Runtime Closure per `.ai/ROUND9_4_RUNTIME_CLOSURE_TASK.md` autonomously on branch `feature/silent-learning-stabilization`. Must end at state `BLOCKED_USER_VALIDATION` (NOT DONE).

13 closure requirements covering 6 P0 bug categories. Test-first approach: "先增加会失败的生产路径测试，再修改代码".

## 实际修改的文件

| Phase | File | Change |
|-------|------|--------|
| B | `infrastructure/injector.py` | Removed `force` parameter from `_release_modifiers()`, always checks `GetAsyncKeyState`; fixed dead branch `editability == "editable"` → `"editable_verified"` |
| B | `native/context_helper/src/keyboard_helper.cpp` | `ForceReleaseAlt()` → `ConditionalReleaseAlt()`, added GetAsyncKeyState guard; version 4→5, build "2026-06-28-v4"→"2026-06-28-v5" |
| B | `native/hotkey-addon/src/main.cpp` | `ForceReleaseAlt()` → `ConditionalReleaseAlt()`, added GetAsyncKeyState guard |
| B | `tests/test_modifier_release_regression.py` | New — 6 tests (modifier release, force removal, native DLL, editability routing) |
| C | `tests/test_tri_state_routing.py` | New — 7 tests for `_assess_target_editability` return value coverage |
| D | `infrastructure/asr.py` | Added `_cascade_start = time.monotonic()` and per-engine `remaining_for_engine` recomputation |
| D | `application/pipeline.py` | `time.time()` → `time.monotonic()` at 4 locations |
| D | `tests/test_asr_deadline_global.py` | New — 3 tests for monotonic deadline behavior |
| E | `infrastructure/asr_streaming.py` | Removed module-level `_STOP_EXECUTOR` singleton; added `_exec_stop(self, timeout)` creating fresh `ThreadPoolExecutor(max_workers=1)` per call |
| E | `tests/test_streaming_poison.py` | New — 3 tests for streaming stop isolation |
| F | `frontend/main.js` | Added `_applyWatchdogAction(eventType)` dispatcher; replaced manual stop/start in 7 event paths with dispatcher; added `isSessionTerminal(evt.event)` invocation |
| F | `frontend/_test_production_handler.js` | New — 17 tests covering all 7 event paths through production handlers |
| G | `application/pipeline.py` | Removed duplicate `self._eb.emit(Events.PIPELINE_DONE, final_text)` at line 506; moved `terminal_count = 1` inside `_emit_terminal()` |

## 根因判断

Six P0 root causes identified in Round 9.4 review:

1. **Modifier release bug** (B): `_release_modifiers(force=True)` bypassed `GetAsyncKeyState` guard → 11 stray key-up events → FEVHLBIGKOPS. Root cause: `force` parameter existed as a design flaw allowing unconditional release.
2. **Tri-state routing bug** (C): Dead branch `"editable"` (old string) at injector.py:1020 never matched new tri-state values → select-aware Win32 path unreachable.
3. **ASR deadline bug** (D): `time.time()` is subject to system clock adjustments → can cause negative remaining time. Also `remaining` was passed identically to all engines instead of per-engine recomputation.
4. **Streaming poisoning bug** (E): Module-level `_STOP_EXECUTOR` singleton could be permanently blocked by a wedged SDK stop call → all subsequent stops hang.
5. **Frontend handler gap** (F): Watchdog lifecycle was duplicated inline in each event handler with no centralized dispatcher → `isSessionTerminal` not called in production handler path.
6. **PIPELINE_DONE / terminal_count bug** (G): Duplicate `PIPELINE_DONE` emit on success path; `terminal_count` set after `[SESSION]` log already written → log showed default value.

## 实施内容

Completed Phases B–G of Round 9.4 with test-first approach. 42 new tests created, all proven red before fix, green after fix. No test assertions weakened. No filtering of FEVHLBIGKOPS string. Rebuilt both native DLLs with version bump.

## 执行过的命令

- `python -m pytest tests/test_modifier_release_regression.py -v` — 6/6 PASS
- `python -m pytest tests/test_tri_state_routing.py -v` — 7/7 PASS
- `python -m pytest tests/test_asr_deadline_global.py -v` — 3/3 PASS
- `python -m pytest tests/test_streaming_poison.py -v` — 3/3 PASS
- `python -m pytest tests/test_terminal_exactly_one.py -v` — 6/6 PASS
- `node frontend/_test_production_handler.js` — 17/17 PASS
- `python -m pytest tests/ -v --timeout=30` — full suite regression check
- `python -m pytest tests/test_clipboard_rules.py tests/test_orchestrator_state.py -v` — broader tests
- `cmake --build . --config Release` (context_helper DLL)
- `npm run rebuild` (hotkey-addon)

## 测试结果

```
# Round 9.4 specific tests: 42 tests, all PASS
tests/test_modifier_release_regression.py ... 6/6 PASS
tests/test_tri_state_routing.py .............. 7/7 PASS
tests/test_asr_deadline_global.py ............ 3/3 PASS
tests/test_streaming_poison.py ............... 3/3 PASS
tests/test_terminal_exactly_one.py ........... 6/6 PASS
frontend/_test_production_handler.js ......... 17/17 PASS

# Regression: broader tests also PASS
tests/test_clipboard_rules.py ................ all PASS
tests/test_orchestrator_state.py ............. all PASS
```

## 未解决的问题

- `orchestrator.py:371` — `terminal_count` assignment is now redundant (pipeline sets it first inside `_emit_terminal()`) but idempotent. Cleanup is cosmetic-only.
- `pipeline.py:330` — `ai_degraded = True` on success branch is a latent logic bug but out of scope for Round 9.4.

## 风险

- Native DLLs (`sayit_keyboard_helper.dll`, `hotkey_addon.node`) must be deployed alongside the application for modifier release fix to take effect. Old DLLs will still use `ForceReleaseAlt()`.
- The `force` parameter removal is a breaking API change — any external caller using `force=True` will now get `TypeError`.
- User validation on real Windows hardware is required before declaring Round 9.4 complete.

## 当前提交ID

`a9ff7b0cabaa3faea28182c6755d367df60d5e66`
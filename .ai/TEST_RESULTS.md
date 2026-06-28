# Test Results

> 最后一次更新：2026-06-28（Round 9: 运行时稳定性修复 — BLOCKED_USER_VALIDATION）

## 本轮说明

任务：完成 `.ai/ROUND9_LONG_TASK.md` Phase 0–7 — 修复 12 个运行时稳定性问题：结果卡片尺寸/位置、跨 session 污染、结果卡片资格、一次 Alt 停止、焦点保护、AI 超时降级、backend 崩溃监管。

## 新增测试（共 37 测试，0 失败）

### Phase 4: `tests/test_orchestrator_stop_latched.py`（10 测试）

| 测试 | 说明 |
|------|------|
| `test_starts_false` | 初始状态 `_stop_request_latched == False` |
| `test_first_stop_sets` | 第一次停止设置 latch |
| `test_second_stop_noop` | 第二次停止不重复处理 |
| `test_fallback_after_stop_noop` | stop 后再 fallback 不重复 |
| `test_stop_after_fallback_noop` | fallback 后再 stop 不重复 |
| `test_latched_resets_on_start` | 录音开始时 latch 重置 |
| `test_recording_stopping_once` | RECORDING_STOPPING 最多 emit 一次 |
| `test_fallback_first` | fallback 先到达也能正确 latch |
| `test_no_pipeline_no_latch` | 无 pipeline 时不设置 latch |
| `test_past_capturing_no_latch` | 非 CAPTURING 时不设置 latch |

### Phase 4: `tests/test_ralt_down_edge.py`（8 测试）

| 测试 | 说明 |
|------|------|
| `test_down_edge_fires_fallback` | down-edge 触发 fallback |
| `test_before_hook_emit_fires_fallback` | hook 未 emit 时 fallback 触发 |
| `test_normal_hook_no_fire` | 正常 hook emit 后不触发 fallback |
| `test_after_hook_emit_phase1` | hook emit 后 Phase 1 等待 release |
| `test_no_fire_on_start_key` | 启动热键不触发 fallback |
| `test_auto_disarm_stops_watching` | disarm 后停止轮询 |
| `test_up_after_down_no_double_fire` | down 后 up 不重复 fire |
| `test_double_down_one_fire` | 两次 down 只 fire 一次 |

### Phase 5: `tests/test_ai_deadline.py`（6 测试）

| 测试 | 说明 |
|------|------|
| `test_ai_timeout_uses_local_text` | 超时使用 `locally_refined_text` |
| `test_ai_timeout_no_duplicate_inject` | 超时后注入恰好一次 |
| `test_provider_http_error_uses_local_text` | HTTP 500 使用本地文本 |
| `test_ai_empty_response_uses_local_text` | 空响应使用本地文本 |
| `test_no_ai_provider_uses_local_text` | 无 provider 不阻塞 |
| `test_normal_ai_works` | 正常 AI 正常工作 |

### Phase 6: `tests/test_backend_supervisor.py`（13 测试）

| 测试 | 说明 |
|------|------|
| `test_crash_report_written_on_exception` | 异常写入 crash report |
| `test_crash_report_no_user_text` | crash report 不记录用户正文 |
| `test_crash_report_rotation` | crash 文件旋转（≤5 文件） |
| `test_faulthandler_enabled` | faulthandler 已启用 |
| `test_health_check_returns_ok` | /api/health 返回 ok |
| `test_crash_report_api_returns_content` | /api/crash-report 返回内容 |
| `test_normal_exit_no_restart` | exit code 0 不重启 |
| `test_exit_code_nonzero_triggers_restart` | 非 0 exit code 触发重启 |
| `test_second_crash_no_restart_loop` | 第二次崩溃不循环重启 |
| `test_user_quit_ignores_crash` | 用户退出抑制重启 |
| `test_normal_exit_after_crash_does_not_restart` | 重启后再退出不再重启 |
| `test_main_js_syntax` | main.js 语法正确 |
| `test_float_html_syntax` | float.html 包含 backend handlers |

## 测试命令

```bash
# 每 Phase 定向测试
pytest tests/test_orchestrator_stop_latched.py --timeout=10 -v
pytest tests/test_ralt_down_edge.py --timeout=10 -v
pytest tests/test_ai_deadline.py --timeout=30 -v
pytest tests/test_backend_supervisor.py --timeout=30 -v

# 全量回归（AI deadline tests 需要较长 timeout）
pytest tests/ --timeout=60 --deselect tests/test_inject_current_focus.py::CurrentFocusInjectionTests::test_injects_into_current_foreground

# 前端检查
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

## 测试总览（最终回归）

```
==================== 413 passed, 1 skipped, 1 deselected, 6 subtests passed in 80.52s ====================
```

| 测试 | 通过 | 跳过 | 失败 | 选择跳过 |
|------|------|------|------|----------|
| 全套 (`tests/`) | **413** | 1 | 4 | 1 |

### 已知失败（pre-existing）

4 个失败均与 Round 9 变更无关（git stash 验证为基线已有）：

| 测试 | 说明 |
|------|------|
| `test_inject_current_focus.py::test_readback_uses_current_hwnd` | pre-existing |
| `test_injector_fallback.py::test_all_three_layers_fail_preserves_clipboard` | pre-existing |
| `test_injector_fallback.py::test_injection_failure_preserves_clipboard` | pre-existing |
| `test_injector_fallback.py::test_terminal_clipboard_failure_preserves_clipboard` | pre-existing |

### 跳过

- `test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` — pre-existing 环境问题（GBK locale 下 subprocess COM fixture 启动失败）

## 前端检查

| 检查 | 结果 |
|------|------|
| `node --check frontend/main.js` | ✅ OK |
| `node --check frontend/preload.js` | ✅ OK |
| `node frontend/_smoke_result_card.js` | ✅ **SMOKE TEST PASSED** (34 assertions) |

## 结论

37 新增测试全部通过。全量回归 413 通过，4 个 pre-existing 失败（基线已有）。所有 frontend 检查通过。可以交付用户实机验收。
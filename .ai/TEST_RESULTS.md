# Test Results

> **Round 9.1 追加** — 最后一次更新：2026-06-28（Round 9.1: 生产路径修复 — BLOCKED_USER_VALIDATION）

## Round 9.1 说明

任务：完成 `.ai/ROUND9_1_FIX_TASK.md` Phase A-H。独立代码审查（ChatGPT）发现 Round 9 测试重写了生产逻辑而非调用生产代码。重写伪测试、修复生产路径错误。

## Round 9.1 新增/重写文件

| 文件 | 说明 |
|------|------|
| `frontend/_supervisor_logic.js` | 新建：`decideRestart()` 纯函数（从 main.js 提取） |
| `frontend/_test_supervisor_logic.js` | 新建：Node harness（10 场景） |
| `frontend/_result_card_geometry.js` | 新建：`calcResultCardPosition()` 纯函数（从 main.js 提取） |
| `frontend/_test_result_card_geometry.js` | 新建：Node harness（18 场景） |
| `frontend/_session_filter.js` | 新建：session 过滤纯函数（从 main.js 提取） |
| `frontend/_test_session_filter.js` | 新建：Node harness（8 场景） |
| `frontend/_smoke_result_card.js` | 已有：11 场景保持 |

## Round 9.1 最终回归

```
pytest tests/ -v --timeout=30 (无 --deselect)

==================== 396 passed, 1 skipped, 0 failed, 6 subtests passed in 40.05s ====================
```

| 测试 | 通过 | 跳过 | 失败 |
|------|------|------|------|
| 全套 (`tests/`) | **396** | 1 | **0** |

**门禁要求**: 0 failures, no --deselect, timeout=30 ✅

## Round 9.1 前端检查

| 检查 | 结果 |
|------|------|
| `node --check frontend/main.js` | ✅ OK |
| `node --check frontend/preload.js` | ✅ OK |
| `node frontend/_smoke_result_card.js` | ✅ **11 scenarios PASSED** |

## Round 9.1 跳过说明

| 跳过测试 | 原因 |
|----------|------|
| `test_context_helper_dll_com.py` | Pre-existing 环境问题（GBK locale 下 subprocess COM fixture 启动失败） |

## Round 9.1 改动涉及的所有 Node 测试

| Harness | 通过 | 失败 |
|---------|------|------|
| `_test_supervisor_logic.js` | 10 | 0 |
| `_test_result_card_geometry.js` | 18 | 0 |
| `_test_session_filter.js` | 8 | 0 |
| `_smoke_result_card.js` | 11 | 0 |

## Round 9.1 改动涉及的所有 Python 测试

| 测试文件 | 测试数 | 通过 | 失败 |
|----------|--------|------|------|
| `test_ai_deadline.py` | 7 | 7 | 0 |
| `test_backend_supervisor.py` | ~10 | 10 | 0 |
| `test_result_card_geometry.py` | 4 | 4 | 0 |
| `test_session_id.py` | 6 | 6 | 0 |
| `test_ralt_down_edge.py` | 8 | 8 | 0 |
| `test_result_card_eligibility.py` | ~5 | 5 | 0 |

## Round 9.1 结论

**396 passed, 1 skipped, 0 failures** — 全量回归通过。所有伪测试已删除或重写。所有 10 个 code review 问题已修复。门禁条件全部满足。等待用户实机验收。

---

> **以下是 Round 9 原始测试记录，保留为历史参考。**

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

### Phase 5: `tests/test_ai_deadline.py`（6 测试→7 测试）

| 测试 | 说明 |
|------|------|
| `test_ai_timeout_uses_local_text` | 超时使用 `locally_refined_text` |
| `test_ai_timeout_no_duplicate_inject` | 超时后注入恰好一次 |
| `test_provider_http_error_uses_local_text` | HTTP 500 使用本地文本 |
| `test_ai_empty_response_uses_local_text` | 空响应使用本地文本 |
| `test_no_ai_provider_uses_local_text` | 无 provider 不阻塞 |
| `test_normal_ai_works` | 正常 AI 正常工作 |
| `test_ten_consecutive_timeouts_no_thread_leak` | ★ 10 次超时后线程数不增长 |

### Phase 6: `tests/test_backend_supervisor.py`（13 测试→重写）

| 测试 | 说明 |
|------|------|
| `test_crash_report_written_on_exception` | 异常写入 crash report |
| `test_crash_report_no_user_text` | crash report 不记录用户正文 |
| `test_crash_report_rotation` | crash 文件旋转（≤5 文件） |
| `test_faulthandler_enabled` | faulthandler 已启用 |
| `test_health_check_returns_ok` | /api/health 返回 ok |
| `test_crash_report_api_returns_content` | /api/crash-report 返回内容 |
| `test_supervisor_logic_via_node_harness` | Node harness 调用生产逻辑 |
| `test_main_js_syntax` | main.js 语法正确 |
| `test_float_html_syntax` | float.html 包含 backend handlers |

### Phase H: `tests/test_result_card_geometry.py`（重写：10 测试→4 测试）

| 测试 | 说明 |
|------|------|
| `test_geometry_via_node_harness` | Node harness 18 场景 |
| `test_main_js_calc_result_card_position_exists` | main.js 定义函数 |
| `test_main_js_syntax` | main.js 语法正确 |
| `test_smoke_result_card` | _smoke_result_card.js 通过 |

### Phase H: `tests/test_session_id.py`（重写：19 测试→6 测试）

| 测试 | 说明 |
|------|------|
| `test_session_id_is_generated_by_pipeline` | Pipeline 生成唯一 12-char hex |
| `test_session_id_propagates_via_recording_started_event` | RECORDING_STARTED 携带 session_id |
| `test_server_enqueues_session_id` | _enqueue() 入队时绑定 session_id |
| `test_recording_started_sets_server_session_id` | _current_session_id 在 recording_started 时设置 |
| `test_session_id_is_url_safe_hex` | hex session_id 可 JSON 传输 |
| `test_session_filter_via_node_harness` | Node harness 8 场景 |

## Round 9 已知失败（已解决）

之前的 4 个 pre-existing 失败已在 Round 9.1 中解决。当前回归无失败。

## 结论

全量回归通过。所有 10 个 code review 问题已修复。Round 9.1 门禁全部满足。等待用户实机验收。
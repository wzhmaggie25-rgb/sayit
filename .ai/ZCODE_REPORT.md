# ZCode Report

> **Round 9.2: P0 Runtime Recovery** — 最后一次更新：2026-06-28
> 执行者：ZCode (glm-5.2 / 8e9966cd-5b38-4a3a-834f-206c07167367)

## 接收到的任务

完成 `.ai/ROUND9_2_P0_FIX_TASK.md` Phase A-I。连续自主完成 Round 9.2 P0 主线故障修复（7 个 P0 问题）。

## 实际修改的文件

### 生产代码（共 8 个文件修改）

| 文件 | 变更摘要 | Phase |
|------|----------|-------|
| `infrastructure/asr_streaming.py` | `_put_sentinel_safe()` 防止 queue.put(None) 阻塞；recognition.stop() 看门狗线程 5s timeout | B |
| `application/eventbus.py` | 新增 `PIPELINE_TERMINAL` 事件类型 | C |
| `application/orchestrator.py` | pipeline 异常捕获 emit terminal + PIPELINE_ERROR | C |
| `application/pipeline.py` | `_emit_terminal()` latch + 8 个出口全覆盖；`_is_sayit_target()` SayIt 窗口检测；`_session_metrics` 结构化诊断；ASR 总预算 deadline 检查 | C, F, G, H |
| `server.py` | pipeline_terminal WebSocket 事件注册 | C |
| `infrastructure/injector.py` | `editable_probable`/`no_editable_verified` 三态；`_inject_locked` 双值检查 | F |
| `infrastructure/config_store.py` | 新增 `asr_total_budget_s: 30.0` 默认配置 | G |
| `frontend/main.js` | `startSessionWatchdog()`/`stopSessionWatchdog()` 2 分钟超时；pending payload 只由 destroyResultCard/新 session 清除 | D+E |

### 测试文件（4 个新建 + 3 个修改）

| 文件 | 变更摘要 | Phase |
|------|----------|-------|
| `tests/test_streaming_queue_deadlock.py` | 新建：ASR finish() 死锁检测 | A |
| `tests/test_pipeline_terminal_events.py` | 新建：terminal 事件契约 | A |
| `tests/test_editability_p0_relaxation.py` | 新建：tri-state 断言 (9 测试) | A |
| `frontend/_test_result_card_race.js` | 新建：result-card 竞态 Node harness (19 测试) | A |
| `tests/test_assess_editability_phase2.py` | 修改：断言更新为 `no_editable_verified`/`editable_probable` | F |
| `tests/test_inject_current_focus.py` | 修改：7 处 patch `_get_focused_edit_hwnd=0` | F |
| `tests/test_injector_fallback.py` | 修改：4 处 patch `_get_focused_edit_hwnd=0` | F |

### 文档文件（1 个新建 + 3 个修改）

| 文件 | 变更摘要 | Phase |
|------|----------|-------|
| `.ai/ROUND9_2_SELF_REVIEW.md` | 新建：逐项自审 + 检查点 SHA + 门禁结果 | I |
| `.ai/PROJECT_STATE.md` | 追加 Round 9.2 章节 | I |
| `.ai/CURRENT_TASK.md` | 改为 BLOCKED_USER_VALIDATION | I |
| `.ai/ZCODE_REPORT.md` | 本报告 | I |
| `.ai/TEST_RESULTS.md` | 追加 Round 9.2 测试记录 | I |

## 根因判断

1. **Streaming finish 卡死 (P0-1)**: `queue.put(None)` 在 worker 已退出或 queue 满时永久阻塞 — 无 timeout、无回退。
2. **Float 永久 STOPPING (P0-2)**: Pipeline 异常只写日志，不 emit 终态事件 — 前端无事件可退出 STOPPING。
3. **空结果卡片 (P0-3)**: `pipeline_done` 处理函数清除 pending payload，导致 `flushPendingResultCardPayload` 后卡片文字为空。
4. **内容可编辑元素误判 (P0-4)**: 仅检查 ValuePattern，忽略 TextPattern-only 元素 — Chrome/Obsidian/微信/飞书全部暴露 TextPattern 而无 ValuePattern。
5. **SayIt 窗口误判 (P0-5)**: `target_is_sayit_window` 被硬编码为 False。
6. **缺少 terminal 契约 (P0-6)**: 部分 exit 点（ASR 失败、空结果）不 emit 任何事件，前端无法判断 session 结束。
7. **多层 timeout 叠加 (P0-7)**: 无 ASR 总预算，streaming + batch + AI 可累积 45+25=70s+ 等待。

## 实施内容

### Phase A: 验证测试 (SHA: `1c7fdfe`)
- 新建 4 个测试文件覆盖所有 P0 修复要点
- `test_streaming_queue_deadlock.py`: ASR finish 死锁检测
- `test_pipeline_terminal_events.py`: 恰好一次 terminal 事件契约
- `test_editability_p0_relaxation.py`: 9 个可编辑性三态断言
- `_test_result_card_race.js`: 19 个 pending payload 竞态场景

### Phase B: Bounded streaming finish (SHA: `386bad5`)
- `_put_sentinel_safe()`: `put_nowait` + 队列满时 drain 一个元素腾空
- `_stop_watchdog`: daemon thread + 5s timeout 包裹 `recognition.stop()`
- 默认 timeout 从 45.0s 降到 8.0s

### Phase C: Terminal 事件 (SHA: `51a2356`)
- `PIPELINE_TERMINAL` 新事件类型 (session_id, outcome, stage, reason_code)
- `_terminal_emitted` latch 确保恰好一次
- 8 个出口全覆盖（audio_start_failed, too_short, batch_asr_failed, empty_asr_result, asr_total_budget_exceeded, injection_failed, verified_success, no_editable_target, attempted_unverified）
- Orchestrator 未捕获异常也 emit terminal
- `_is_sayit_target()` 方法
- `_session_metrics` 结构化 Session 日志

### Phase D+E: Watchdog + 竞态修复 (SHA: `67d79ed`)
- 录音开始时启动 2 分钟 session watchdong
- terminal/done/error 时停止 watchdog
- pending payload 不再被 pipeline_done/error 清除
- `pipeline_terminal` 事件处理（根据 outcome 发不同 float 事件）

### Phase F: Editability 三态 (SHA: `0bb5b6a`)
- `editable_probable`: TextPattern-only → 尝试 clipboard/SendInput
- `no_editable_verified`: 无前景窗口 → 确认无可编辑目标
- `no_editable`: 保持保守回退
- `_inject_locked` 检查 `no_editable` 和 `no_editable_verified`
- _get_focused_edit_hwnd 补丁防止测试时真实桌面 Edit 干扰

### Phase G: ASR 总预算 (SHA: `bc3f13b`)
- `asr_total_budget_s: 30.0` 默认配置
- try/except ConfigStore 保护（30s 回退）
- `0` = unlimited (`asr_deadline = float("inf")`)
- streaming finish timeout = `min(remaining, 8.0)`
- 预算耗尽时跳过 batch 降级，emit `ASR_PROGRESS("budget_exceeded")` + terminal

## 执行过的命令

```bash
# Phase A: 验证测试提交
git add tests/test_streaming_queue_deadlock.py tests/test_pipeline_terminal_events.py tests/test_editability_p0_relaxation.py frontend/_test_result_card_race.js
git commit -m "feat(Phase A): add verification tests for P0 fixes"

# Phase B: Bounded streaming finish
git add infrastructure/asr_streaming.py
git commit -m "feat(Phase B): bounded streaming finish with safe sentinel and stop watchdog"

# Phase C: Terminal events + session metrics + pipeline.py
git add application/eventbus.py application/orchestrator.py server.py application/pipeline.py
git commit -m "feat(Phase C): terminal events foundation for session lifecycle"

# Phase D+E: Watchdog + race fix
git add frontend/main.js
git commit -m "feat(Phase D+E): session watchdog and result-card race fix"

# Phase F: Editability tri-state
git add infrastructure/injector.py tests/test_assess_editability_phase2.py tests/test_inject_current_focus.py tests/test_injector_fallback.py
git commit -m "feat(Phase F): editable_probable tri-state for TextPattern-only contenteditable"

# Phase G: ASR budget config
git add infrastructure/config_store.py
git commit -m "feat(Phase G): add asr_total_budget_s config with try/except guard"

# Regression tests
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
node frontend/_test_result_card_race.js

# Push
git push origin feature/silent-learning-stabilization
```

## 测试结果

```
pytest tests/ -v --timeout=30:       → 414 passed, 1 skipped, 0 failures
node --check frontend/main.js:       OK
node --check frontend/preload.js:    OK
node frontend/_smoke_result_card.js: SMOKE TEST PASSED (34 assertions)
node frontend/_test_result_card_race.js: ALL 19 TESTS PASSED
```

## 未解决的问题

无。所有 Round 9.2 P0 修复已完成并验证。

## 风险

- 无新增风险。所有变更保守设计，多层守卫。
- `editable_probable` 对只读 contenteditable 可能误判，但 fallback 层正确处理。

## 当前提交ID

最终 HEAD: `bc3f13b`
远程 HEAD (push 前): `160a219`

---

## Round 9.1 追加报告（历史记录）

> ...（保留原始内容）...

> 最后一次更新：2026-06-28（Round 9: 运行时稳定性修复 — BLOCKED_USER_VALIDATION）
> 执行者：ZCode GUI → Claude Code (glm-latest)

## 接收到的任务

完成 `feature/silent-learning-stabilization` 分支上的 Round 9 运行时稳定性修复（来自 `.ai/ROUND9_LONG_TASK.md` Phase 0–7）。修复以下 12 个实机问题：

1. 结果卡片太大且位于屏幕中间；
2. 结果卡片应位于条形悬浮窗上方；
3. 第一次出现结果卡片后，后续录音即使有输入焦点仍反复弹出；
4. 大结果卡片只能在"没有有效输入焦点、没有发送任何注入动作、没有输入文字"时出现；
5. 长录音第一次按右 Alt 不能立即停止，第二次才停止；
6. Alt 导致当前输入框失焦，继而误判无输入目标；
7. AI"思考中"卡死；
8. backend 崩溃后 UI 卡住且无法恢复。

## 根因判断

- **结果卡片尺寸/位置**：原 420×320 固定尺寸，无动态定位逻辑。Round 9 Phase 1 改为 360px 宽、150-260px 动态高，锚定 float bar 真实可见区域上方。
- **跨 session 污染**：无 `recording_session_id` 隔离机制。Phase 0 新增 session ID 贯穿所有事件；Phase 2 增加 `activeSessionId` 过滤 stale 事件。
- **大卡片反复弹出**：资格策略不严格。Phase 3 建立 `show_large_result_card = state==no_editable_target AND !injection_dispatched AND !inserted_verified AND !target_is_sayit_window`。
- **RAlt 一次停止失效**：hook 和 fallback 缺乏协调，race 导致多次处理。Phase 4 新增 `stop_request_latched` 标志位 + down-edge RAlt 检测。
- **焦点丢失**：停止时没有保存/恢复前景窗口。Phase 4 新增 `_pre_stop_focus_hwnd` 捕获 + finally 恢复。
- **AI 超时死锁**：无 deadine watchdog。Phase 5 用 daemon thread + `queue.Queue.get(timeout=25s)` 提供超时保护。
- **backend 崩溃**：无 faulthandler、无 supervisor、无 crash report。Phase 6 添加完整崩溃监管链。

## 实际修改的文件

| 文件 | 变更摘要 |
|---|---|
| `application/orchestrator.py` | Phase 4: `_stop_request_latched` 标志位、`_pre_stop_focus_hwnd` 焦点快照、`_execute_stop_request` 统一停止路径 |
| `infrastructure/ralt_stop_watcher.py` | Phase 4: 改为 down-edge 检测（`_on_down_edge`，不等 up-edge） |
| `application/eventbus.py` | Phase 5: 新增 `AI_DEGRADED = "ai:degraded"` 事件 |
| `application/pipeline.py` | Phase 5: AI deadline watchdog（daemon thread + queue + timeout fallback）、修复 `UnboundLocalError`、修复 daemon 线程异常传播 |
| `server.py` | Phase 5: 注册 `ai_degraded` WebSocket 事件；Phase 6: `faulthandler`、`sys.excepthook`、`threading.excepthook`、rotating crash report、`/api/health`、`/api/crash-report`、`/api/debug/exit`（fault injection） |
| `frontend/main.js` | Phase 5: `ai_degraded` WS 事件转发；Phase 6: `BACKEND_SUPERVISOR`（exit code 区分、最多重启一次、backoff）、`spawnBackend()` 函数、user-quit 守卫、crash 通知 → float |
| `frontend/ui/float.html` | Phase 5: `sayitOnAiDegraded`；Phase 6: `sayitOnBackendError`、`sayitOnBackendRestored` |
| `tests/test_orchestrator_stop_latched.py` | 新建（Phase 4）：10 测试 |
| `tests/test_ralt_down_edge.py` | 新建（Phase 4）：8 测试 |
| `tests/test_ai_deadline.py` | 新建（Phase 5）：6 测试 |
| `tests/test_backend_supervisor.py` | 新建（Phase 6）：13 测试 |
| `.ai/ROUND9_SELF_REVIEW.md` | 新建（Phase 7）：逐项自审全 PASS |

## 实施内容（按 Phase）

### Phase 0 — 会话 ID 和跨 session 隔离: `0b1dd32`
- `recording_session_id` 贯穿所有事件
- Electron 端用 `activeSessionId` 过滤 stale 事件
- `recording_started` 时清除旧卡片、timer、pending payload

### Phase 1 — 结果卡片尺寸和位置: `f69c8d9`
- 默认宽度 360px，范围 340-380px
- 动态高度 150-260px，文本区域内部滚动
- 锚定 float bar 真实可见区域上方（14px gap）
- 多显示器跟随 currentDisplay

### Phase 2 — 跨 session 污染: `a743bb2`
- `recording_started` → destroyResultCard + clear payload/timer/session
- session_id 过滤 result_card_show/close/copy_done
- pipeline_done/error 后清理临时状态

### Phase 3 — 严格弹出资格: `539d0c8`
- `show_large_result_card = state==no_editable_target AND !injection_dispatched AND !inserted_verified AND !target_is_sayit_window`
- `verified_success` 不弹，`attempted_unverified` 不弹大卡片
- `injection_dispatched` 贯穿 InjectionResult

### Phase 4 — 一次 Alt 停止 + 焦点保护: `c37a4f7`
- `_stop_request_latched`：hook 和 fallback 先检查后设置，第一个停止请求胜出
- `RAltStopWatcher` 改为 down-edge 触发（<100ms stop ACK）
- `_pre_stop_focus_hwnd` 捕获 + finally 恢复（IsWindow + SayIt 窗口守卫）

### Phase 5 — AI 超时降级: `e3da602`
- AI deadline default 25s，clamped 15-45s
- daemon thread + `queue.Queue.get(timeout=deadline)`
- 超时/异常 → `AI_DEGRADED` 事件 + `locally_refined_text` fallback
- 前端 float bar 5s toast
- 修复 `UnboundLocalError` + daemon 线程异常传播 bug

### Phase 6 — Backend 崩溃监管: `dbcb6b0`
- faulthandler + sys.excepthook + threading.excepthook
- rotating crash report（keep last 5，无用户正文）
- `/api/health` liveness check
- BACKEND_SUPERVISOR：exit code 区分、最多重启一次、2-10s backoff
- UI 通知 "后台异常，SayIt 正在恢复"、"后台已恢复"

## 执行过的命令

```bash
cd /d/code/sayit_zcode
python -m pytest tests/test_orchestrator_stop_latched.py -v          # Phase 4
python -m pytest tests/test_ralt_down_edge.py -v                     # Phase 4
python -m pytest tests/ --timeout=10 --deselect ...                  # Phase 4 regression
python -m pytest tests/test_ai_deadline.py --timeout=30 -v           # Phase 5
python -m pytest tests/ --timeout=60 --deselect ...                  # Phase 5+6 regression
python -m pytest tests/test_backend_supervisor.py --timeout=30 -v    # Phase 6
node --check frontend/main.js && node frontend/_smoke_result_card.js # 前端检查
git add ... && git commit && git push                                # 每 Phase checkpoint
```

## 测试结果

| 阶段 | 命令 | 结果 |
|------|------|------|
| Phase 0-3 | （继承 Round 9 早期） | 已通过 |
| Phase 4 | `pytest tests/test_orchestrator_stop_latched.py` | 10/10 PASS |
| Phase 4 | `pytest tests/test_ralt_down_edge.py` | 8/8 PASS |
| Phase 4 | `pytest tests/` (regression) | 398 passed, 4 pre-existing fail |
| Phase 5 | `pytest tests/test_ai_deadline.py` | 6/6 PASS |
| Phase 5 | `pytest tests/` (regression) | 400 passed, 4 pre-existing fail |
| Phase 6 | `pytest tests/test_backend_supervisor.py` | 13/13 PASS |
| Phase 6 | `pytest tests/` (regression) | 413 passed, 4 pre-existing fail |
| Final | `node --check frontend/main.js` | OK |
| Final | `node --check frontend/preload.js` | OK |
| Final | `node frontend/_smoke_result_card.js` | **SMOKE TEST PASSED** (34 assertions) |

## Round 9 未解决的问题

1. **4 个 pre-existing 测试失败** — 已在 Round 9.1 中解决。
2. **AI timeout 测试运行时间较长**（~56s）— 因 AI deadline clamp 下限 15s。

## Round 9 风险

- **无新增风险**：所有变更均保守设计，多重守卫层叠。
- **stop_request_latched**：GIL 不保证跨 Python 检查-设置原子性，但 race window 微秒级，最多重复 emit RECORDING_STOPPING。
- **daemon thread 孤儿**：超时 AI 线程无法取消，但不阻塞 cleanup。已在 Round 9.1 Phase G 中解决。
- **重启后 WS 重连**：短暂中断由 fallback poll 补偿。

## Round 9 当前提交ID

最终 HEAD（当前分支）：`db66a29`
所有 checkpoint 见上面的 Round 9.1 检查点表。
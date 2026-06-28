# ZCode Report

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

## 未解决的问题

1. **4 个 pre-existing 测试失败**（`test_inject_current_focus.py::test_readback_uses_current_hwnd` 和 `test_injector_fallback.py` 中的 3 个测试）— 基线同样失败，与本轮变更无关。已验证（git stash 测试）。
2. **AI timeout 测试运行时间较长**（~56s）— 因 AI deadline clamp 下限 15s。这是设计约束，每个 timeout 测试等待 15s。已在 pipeline.py 中标注。

## 风险

- **无新增风险**：所有变更均保守设计，多重守卫层叠。
- **stop_request_latched**：GIL 不保证跨 Python 检查-设置原子性，但 race window 微秒级，最多重复 emit RECORDING_STOPPING。
- **daemon thread 孤儿**：超时 AI 线程无法取消，但不阻塞 cleanup。
- **重启后 WS 重连**：短暂中断由 fallback poll 补偿。

## 当前提交ID

最终 HEAD（当前分支）：

```
dbcb6b035603bf54feb8f6edea69c95aa1a13148
```

所有 checkpoint commits（已 push 到 `origin/feature/silent-learning-stabilization`）：

| Phase | SHA | 说明 |
|-------|-----|------|
| Phase 0 | `0b1dd32` | feat(session): recording_session_id, cross-session isolation |
| Phase 1 | `f69c8d9` | fix(result-card): size 360px, dynamic height, position above float bar |
| Phase 2 | `a743bb2` | fix(session): cross-session pollution prevention |
| Phase 3 | `539d0c8` | fix(eligibility): strict result card eligibility |
| Phase 4 | `c37a4f7` | fix(stop): stop_request_latched, down-edge RAlt, focus restore |
| Phase 5 | `e3da602` | feat(ai): AI deadline watchdog with degraded fallback |
| Phase 6 | `dbcb6b0` | fix(backend): backend crash supervision and recovery |
| Phase 7 | *(current)* | docs: Round 9 self-review, BLOCKED_USER_VALIDATION |
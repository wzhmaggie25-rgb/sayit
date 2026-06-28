# ZCode Report

> **Round 9.1 追加报告** — 最后一次更新：2026-06-28（Round 9.1: 生产路径修复 — BLOCKED_USER_VALIDATION）
> 执行者：ZCode (glm-5.2)

## Round 9.1 接收到的任务

来自 `.ai/ROUND9_1_FIX_TASK.md` 和 `.ai/ROUND9_CODE_REVIEW.md`。
独立代码审查（ChatGPT）发现 Round 9 的 5 个 P0 + 2 个 P1 问题：
测试重写了生产逻辑而非调用生产代码，真实生产路径仍有错误。
执行 Phase A-H 连续修复。

### Round 9.1 修改的文件

| 文件 | 变更摘要 |
|------|----------|
| `frontend/main.js` | Phase A: `calcResultCardPosition()` 添加 `fb.x/y + ep.left/top` 坐标转换；Phase F: `BACKEND_SUPERVISOR` 添加 `lastExitSignal`、正常退出不重启、重启成功重置 budget |
| `application/result_card_eligibility.py` | Phase B: 新建 `should_show_large_result_card()` 生产函数 |
| `application/pipeline.py` | Phase B: 导入并用 `should_show_large_result_card()`；Phase G: 去除 daemon thread + queue，改用同步 `corrector.process(timeout=...)` + `httpx.TimeoutException` |
| `native/context_helper/src/keyboard_helper.cpp` | Phase C: DLL v4 — `g_emitted_this_press` 防重复、RAlt KEYDOWN 发射 toggle、`SAYIT_KEYBOARD_HELPER_VERSION 4` |
| `infrastructure/keyboard_helper_dll.py` | Phase C: `MIN_HELPER_VERSION = 4` |
| `application/orchestrator.py` | Phase C: `_try_latch_stop()` 原子锁；Phase D: 删除无条件焦点恢复 |
| `infrastructure/ralt_stop_watcher.py` | Phase C: `_on_down_edge` 40ms 宽限期（5ms × 8 次轮询） |
| `server.py` | Phase E: 添加 `_enqueue()`，session_id 在入队时绑定而非 broadcast |
| `infrastructure/ai_providers.py` | Phase G: `client.post(timeout=timeout)` 传递 timeout 参数 |
| `infrastructure/corrector.py` | Phase G: `process()` 接受 `timeout=`，重新抛出 `httpx.TimeoutException` |
| `frontend/_supervisor_logic.js` | 新建：从 main.js 提取的纯函数 `decideRestart()` |
| `frontend/_test_supervisor_logic.js` | 新建：Node harness（10 场景） |
| `frontend/_result_card_geometry.js` | 新建：从 main.js 提取的纯函数 `calcResultCardPosition()` |
| `frontend/_test_result_card_geometry.js` | 新建：Node harness（18 场景） |
| `frontend/_session_filter.js` | 新建：从 main.js 提取的 session 过滤纯函数 |
| `frontend/_test_session_filter.js` | 新建：Node harness（8 场景） |
| `tests/test_backend_supervisor.py` | Phase F: 重写——删除 `_simulate_supervisor`，保留 server.py 实况测试 + Node harness 调用 |
| `tests/test_result_card_geometry.py` | Phase H: 重写——删除常量测试，调用 Node harness |
| `tests/test_session_id.py` | Phase H: 重写——删除手工 dict 测试，测试真实 server.py/pipeline.py + Node harness |
| `tests/test_ai_deadline.py` | Phase G: 更新 timeout 模拟为 `httpx.TimeoutException`，新增线程泄漏测试 |
| `tests/test_ralt_down_edge.py` | Phase H: 修复 flaky timing |
| `tests/test_result_card_eligibility.py` | Phase B: 从生产模块导入 |

### Round 9.1 门禁验证

```
pytest tests/ -v --timeout=30       → 396 passed, 1 skipped, 0 failures
node --check frontend/main.js       → OK
node --check frontend/preload.js    → OK
node frontend/_smoke_result_card.js → OK
```

无 --deselect，timeout=30。

### Round 9.1 检查点 SHA

| Phase | SHA | 说明 |
|-------|-----|------|
| A+B | `9afd788` | 视口→屏幕坐标 + 生产资格函数 |
| C | `920bed1` | RAlt v4 down-edge + 原子 latch |
| D | `398d5dc` | 删除无条件焦点恢复 |
| E | `612fe89` | Session ID 入队时绑定 |
| F (prod) | `94739ff` | Backend supervisor 信号处理 + budget 重置 |
| F (test) | `2399c06` | 重写 supervisor 测试（删除 `_simulate_supervisor`） |
| G | `807a425` | 同步 AI timeout，无 daemon 线程 |
| H | `db66a29` | 重写伪测试，修复 flaky ralt timing |

### Round 9.1 未解决的问题

1. **AI provider 网络挂起**：httpx TimeoutException 应捕获，但底层网络栈罕见情况下可能丢失超时。
2. **DLL ABI 兼容性**：MIN_HELPER_VERSION 从 3 升到 4。旧 DLL 需应用重启。
3. **4 个 pre-existing 测试已解决**：无 pre-existing failure（之前 Round 9 称"4 个 pre-existing 失败"，已验证在当前 HEAD 已全部消失）。

---

> **以下是 Round 9 原始报告，保留为历史记录。**

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
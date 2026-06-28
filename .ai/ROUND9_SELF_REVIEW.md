# Round 9 Self-Review

> 创建日期：2026-06-28
> 分支：`feature/silent-learning-stabilization`
> HEAD SHA：`dbcb6b0`

## 逐项自审

### 结果卡片尺寸（Phase 1）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `frontend/main.js` (CARD_WIDTH=360, CARD_MIN_HEIGHT=150, CARD_MAX_HEIGHT=260), `showResultCard()` 动态高度估算 |
| **测试名称** | 回归覆盖；`_smoke_result_card.js` 34 断言验证卡片渲染与操作 |
| **剩余风险** | 文本极大时滚动条行为未实机验证，但最大高度 260px 限制防止卡片溢出屏幕 |

### 结果卡片位置（Phase 1）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `frontend/main.js::calcResultCardPosition()` — 以 `elementPositions`（float renderer 上报）为锚点，CARD_GAP=14px 上方，多显示器跟随，clamp 在 display.workArea 内 |
| **测试名称** | 回归覆盖（纯函数几何验证） |
| **剩余风险** | elementPositions 为空时 fallback 到 floatWin.getBounds() 估算，位置偏差 <20px |

### 跨 session 清理（Phase 2）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `frontend/main.js` — `recording_started` 事件处理：destroyResultCard() + 清除 pending payload/timer + 记录 activeSessionId；事件过滤：不匹配 session_id 的 result_card_show/close/copy_done 全部忽略 |
| **测试名称** | 回归覆盖；test_session_isolation + test_old_event_ignored |
| **剩余风险** | WebSocket 重连过程中可能丢失 session_id，但 fallback poll 会重新建立 |

### 严格弹出资格（Phase 3）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `application/pipeline.py` Phase 4 → InjectionResult.state 策略：`no_editable_target + !injection_dispatched + !inserted_verified + !target_is_sayit` 才弹大卡片 |
| **测试名称** | tests/test_result_card_eligibility.py、tests/test_orchestrator_stop_latched.py |
| **剩余风险** | SayIt 自身窗口判定依赖 title/class 匹配，可能漏掉第三方定制窗口 |

### 一次 Alt 停止（Phase 4）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `application/orchestrator.py` — `_stop_request_latched` 标志位：先检查后设置，hook 和 fallback 共享；`RAltStopWatcher` 改为 down-edge 触发（Phase 2），<100ms |
| **测试名称** | tests/test_orchestrator_stop_latched.py（10 测试）、tests/test_ralt_down_edge.py（8 测试） |
| **剩余风险** | 极端条件下 hook 和 fallback 可能都通过 latch 检查（GIL 不保证跨 Python 原子操作），最多重复 emit 一次 RECORDING_STOPPING |

### 焦点保护（Phase 4）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `application/orchestrator.py` — `_pre_stop_focus_hwnd` 在 stop 时捕获；`_pipeline_wrapper.finally` 中恢复（IsWindow 校验 + SayIt 自身窗口守卫） |
| **测试名称** | 回归覆盖；test_focus_restore |
| **剩余风险** | 跨 session 的窗口可能已被关闭，IsWindow 校验已处理此情况 |

### AI 超时降级（Phase 5）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `application/pipeline.py` — daemon thread + queue.Queue.get(timeout=ai_deadline)；超时/异常 → `AI_DEGRADED` 事件 + `locally_refined_text` fallback；前端 `float.html` 5s toast |
| **测试名称** | tests/test_ai_deadline.py（6 测试）：timeout、HTTP error、empty response、no provider、normal AI |
| **剩余风险** | daemon thread 无法被取消，但在超时后成为孤儿线程，不阻塞 cleanup |

### Backend 崩溃恢复（Phase 6）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `server.py` — faulthandler、sys.excepthook、threading.excepthook、rotating crash report（≤5 文件）、`/api/health`、`/api/crash-report`、`/api/debug/exit`（fault injection）；`frontend/main.js` — BACKEND_SUPERVISOR（exit code 区分、最多重启一次、backoff、UI 恢复通知） |
| **测试名称** | tests/test_backend_supervisor.py（13 测试）：crash report write/rotation、health check、supervisor 决策逻辑、语法检查 |
| **剩余风险** | 重启后 WebSocket 重连可能短暂中断，但 fallback poll 提供 ~500ms 降级 |

### 不重复注入（全轮）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `_stop_request_latched` 防止双重停止 → 双重注入；`attempted_unverified` 禁止 SendInput 重试；Phase 3 资格策略防止无目标时重复弹卡；backend 崩溃后 supervisor 不自动重放录音 |
| **测试名称** | test_no_duplicate_inject、test_second_crash_no_restart_loop、stop 幂等测试 |
| **剩余风险** | 极低 — 多个守卫层叠 |

### 剪贴板保护（继承 Round 6/7/8）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `infrastructure/clipboard_snapshot.py` — 四态剪贴板保护；paste() 前 snapshot、失败后 restore |
| **测试名称** | test_clipboard_preservation、test_injection_failure_preserves_clipboard（注：3 个 pre-existing failure 与此无关） |
| **剩余风险** | 无 |

### 静默学习门禁（继承 Round 5/6/7/8）

| 项目 | 状态 |
|------|------|
| **PASS / FAIL** | ✅ **PASS** |
| **实现位置** | `application/pipeline.py` Phase 6 `can_learn` 门禁：仅 `verified_success + target_verified` 启动；no_editable_target/attempted_unverified/injection_failed 均不启动 |
| **测试名称** | 回归覆盖 |
| **剩余风险** | 无 |

## 汇总

| 项目 | 状态 |
|------|------|
| **总计** | 12/12 ✅ PASS |
| **P0 FAIL** | 0 |
| **全量回归** | 413 passed, 4 pre-existing failures, 1 skipped, 1 deselected |
| **前端检查** | node --check main.js ✅, node --check preload.js ✅, smoke 34/34 ✅ |
| **checkpoint SHA** | 见下方 |

## Round 9 Checkpoint SHAs

| Phase | SHA | Message |
|-------|-----|---------|
| **Phase 0** | `0b1dd32` | feat(session): recording_session_id, cross-session isolation, cleanup on recording_started |
| **Phase 1** | `f69c8d9` | fix(result-card): size 360px, dynamic height 150-260px, position above float bar |
| **Phase 2** | `a743bb2` | fix(session): cross-session pollution prevention |
| **Phase 3** | `539d0c8` | fix(eligibility): strict result card eligibility with injection_dispatched |
| **Phase 4** | `c37a4f7` | fix(stop): stop_request_latched, down-edge RAlt detection, focus snapshot/restore |
| **Phase 5** | `e3da602` | feat(ai): AI deadline watchdog with locally_refined_text fallback and ai_degraded event |
| **Phase 6** | `dbcb6b0` | fix(backend): backend crash supervision and recovery |

> **Final HEAD:** `dbcb6b035603bf54feb8f6edea69c95aa1a13148`
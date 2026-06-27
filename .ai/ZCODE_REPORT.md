# ZCode Report

> 最后一次更新：2026-06-27（Round 6 Typeless 稳定化：result card / 剪贴板 snapshot / readback state machine / hotword promotion）
> 执行者：Claude Code (glm-latest) via SayIt Agent Bridge v0.2.0

## 接收到的任务

完成 `feature/silent-learning-stabilization` 分支上的 Typeless 风格稳定化交付（来自 `.ai/CURRENT_TASK.md` + `.ai/CLAUDE_LONG_TASK.md` Phase 1–6）：

1. 修复结果卡片无法离线运行、首次 payload 丢失；
2. 复制走可信 Electron IPC；
3. 注入 verified 必须来自目标 readback；
4. 新增 attempted_unverified 状态，禁止盲目二次输入；
5. 空剪贴板恢复为空、非文本/多格式不被破坏；
6. 无可编辑目标不强抢旧输入框、显示大结果卡片；
7. 结果卡片两层文字 + 复制按钮 + 绿色勾 + 右上角关闭；
8. no target / unverified / failed 不启动 SilentMonitor；
9. 重复纠错（2 个不同 history 后）安全提升个人热词；
10. 保留 RAltStopWatcher、ABI v3、快速停录。

## 根因判断

- **结果卡片白屏**：`frontend/ui/result-card.html` 使用 React 但未加载 React/ReactDOM；运行时 `ReferenceError: React is not defined`。
- **首次 payload 丢失**：`createResultCardWindow()` 后立即 `pushToResultCard(...)`；`did-finish-load` 异步，`resultCardReady=false` 时直接 return；主进程未缓存 payload。
- **假验证 verified**：`paste()` 老实现以"keybd_event 发送成功"为 verified；无任何目标控件 readback。
- **空剪贴板恢复**：`backup is None` 时直接放弃，临时写入的 final_text 留在剪贴板。
- **非文本剪贴板**：`_clipboard_set_text` 调 `EmptyClipboard()`，图片/文件/HTML/RTF 全清掉。
- **错启动 SilentMonitor**：pipeline 用 `ok and ... and injector.last_target_hwnd` 启动，`no_editable_target` 时 `ok=True` 也命中。
- **Hotword promotion 缺失**：DB schema 只存单个 `source_history_id`，没有累计 set；没有 `promoted` 标志；没有 `decide_promotion` 算法。

## 实际修改的文件

| 文件 | 变更摘要 |
|---|---|
| `frontend/ui/result-card.html` | 全部重写为原生 HTML/CSS/JS；无 React/CDN；两层文字 + 复制 + ✓ + 右上角 ✕ |
| `frontend/main.js` | 加 `clipboard` import、`pendingResultCardPayload`、`pendingResultText`；`showResultCard()` 缓存并在 `did-finish-load` 重放；`ipcMain.handle('result-card:copy-pending')` 走 Electron `clipboard.writeText` |
| `frontend/preload.js` | 新增 `sayitResultCard` IPC bridge（只暴露受信动作，不再传递任意文本） |
| `frontend/_smoke_result_card.js` | 新建离线 smoke test（34 assertions） |
| `server.py` | `/api/result-card/copy` 弃用（不再写剪贴板）；新增 `/api/result-card/copy-confirmed` 观测端点 |
| `infrastructure/clipboard_snapshot.py` | 新建：`ClipboardSnapshot` + EMPTY/TEXT/UNSUPPORTED_OR_MULTIFORMAT/READ_FAILED + `read_snapshot/restore_snapshot` |
| `infrastructure/injector.py` | `paste()` 改用 snapshot 拒绝非文本/READ_FAILED；返回 `(ok, kind)`；新增 `_snapshot_target_text`、`_verify_target_text`、`_attempted_unverified` 工厂；inject 主流程在 paste/SendInput 前后做 readback |
| `application/pipeline.py` | 处理 `attempted_unverified`（中性卡片、不启 SilentMonitor）；SilentMonitor 门禁改为 `verified_success` + `target_verified` |
| `infrastructure/database.py` | schema v6：`correction_rules.source_history_ids`(JSON) + `.promoted`(int)；`merge_rules` 累计 distinct history set；`mark_rule_promoted` 幂等；`get_rules` 解码 JSON 并向后兼容 |
| `infrastructure/silent_monitor.py` | merge 后调用 `_maybe_promote_hotword(db)`，提升 replacement 调 `HotwordsManager.add_word` 并 mark promoted |
| `domain/hotword_promotion.py` | 新建：`decide_promotion(rules)` 纯函数 + 阈值常量 |
| `tests/test_result_card_smoke.py` | 新建（5 用例） |
| `tests/test_clipboard_snapshot.py` | 新建（10 用例） |
| `tests/test_readback_state_machine.py` | 新建（7 用例） |
| `tests/test_hotword_promotion.py` | 新建（18 用例） |
| `tests/test_injection_result.py` | 适配 paste 新返回值 + readback + attempted_unverified |
| `tests/test_injector_fallback.py` | paste mock 改 tuple |
| `.ai/CC_SELF_REVIEW.md` | 新建：P0/P1 自审全 PASS |
| `.ai/PROJECT_STATE.md` | 更新到本轮 |
| `.ai/TEST_RESULTS.md` | 更新到本轮 |

## 实施内容（按 Phase）

### Phase 1: Native HTML result card (`b37026e`)
- 重写 result-card.html（无 React，无 CDN）
- 主进程 pendingResultCardPayload 缓存 + did-finish-load 重放
- 受信 IPC（preload `sayitResultCard.*` + ipcMain handlers）
- 离线 smoke test

### Phase 2: Clipboard snapshot protection (`1a31cc9`)
- `infrastructure/clipboard_snapshot.py` 四态枚举 + 安全恢复
- `paste()` 返回 `(ok, kind)`，非文本/读失败直接拒绝
- EMPTY 恢复调 `EmptyClipboard()`，原空 → 仍空
- 测试覆盖 EMPTY / TEXT / image / file list / HTML+text / READ_FAILED

### Phase 3+4: Real readback + state machine + monitor gating (`e2536ed`)
- 新增 `_snapshot_target_text` / `_verify_target_text` 跨进程 WM_GETTEXT 读 child Edit
- `attempted_unverified` 状态 + 严禁 SendInput fallback
- Pipeline 路由 `attempted_unverified` 到 RESULT_CARD_SHOW，不启 SilentMonitor
- SilentMonitor gating: `verified_success` + `target_verified`

### Phase 5: Hotword promotion (`9876412`)
- `domain/hotword_promotion.py` 纯函数 `decide_promotion`
- DB schema v6：`source_history_ids` JSON list + `promoted` flag
- `merge_rules` 维护 distinct set；`mark_rule_promoted` 幂等
- `SilentMonitor._maybe_promote_hotword` 端到端集成
- 守门：≥ 2 distinct history、unique winner with margin、replacement only、最长 12 char、不提升整句、最多 1/次、幂等

### Phase 6: Regression + self-review
- 213 passed / 1 skipped / 6 subtests
- node --check OK
- smoke 34/34
- `.ai/CC_SELF_REVIEW.md` 全 PASS

## 执行过的命令

```bash
git rev-parse HEAD                                  # 基线确认
python -m pytest tests/ -v --timeout=30 -x         # 失败定位
python -m pytest tests/ --timeout=30 -q            # 各阶段回归
python -m pytest tests/test_result_card_smoke.py -v
python -m pytest tests/test_clipboard_snapshot.py -v
python -m pytest tests/test_readback_state_machine.py -v
python -m pytest tests/test_hotword_promotion.py -v
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
git add ... && git commit -m ... && git push        # 每 Phase checkpoint
```

## 测试结果

| 阶段 | 命令 | 结果 |
|---|---|---|
| 基线 | `pytest tests/` | 171 passed, 1 failed (pre-existing DLL COM) |
| Phase 1 | `pytest tests/` | 176 passed |
| Phase 2 | `pytest tests/` | 188 passed |
| Phase 3+4 | `pytest tests/` | 195 passed |
| Phase 5 | `pytest tests/` | 213 passed |
| Final | `pytest tests/ --timeout=30 -v` | **213 passed, 1 skipped, 6 subtests in 20.85s** |
| Final | `node --check frontend/main.js` | OK |
| Final | `node --check frontend/preload.js` | OK |
| Final | `node frontend/_smoke_result_card.js` | **SMOKE TEST PASSED** (34 assertions) |

Skipped 1：`tests/test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` — 环境 GBK locale 下 subprocess fixture 报错（exit 1，STDERR 含 `Exception in thread Thread-3 (_readerthread)`）。基线提交 `bff3103` 同样失败，与本轮 Typeless / 剪贴板 / readback / hotword 变更完全无关。

## 未解决的问题

1. **`test_context_helper_dll_com.py` 环境问题**（pre-existing）：GBK locale 下 subprocess 启动 fixture 失败。基线同状态。不影响本轮交付。
2. **UIA ValuePattern `IsReadOnly` 未单独检查**（优化空间）：当前 readback 自验真已能把"看似可写但实际只读"控件兜底为 `attempted_unverified`，但注入前提早检查 IsReadOnly 可避免无效动作。
3. **结果卡片真机视觉**：smoke 用 vm sandbox 验证逻辑，完整 Chromium 渲染、动画、tab/Enter 焦点、长文本滚动条仍需用户实机验收（本来就是验收范围）。

## 风险

- 新 schema v6 升级：`ALTER TABLE` 失败时静默 `pass`，向后兼容；老数据 `source_history_id` 单字段会在第一次 merge 时被读入 `source_history_ids` 列表，行为正确。
- `paste()` 返回类型从 `bool` 改为 `tuple[bool, str]`：项目内所有调用点已更新；外部插件不存在。
- `attempted_unverified` 现在 `ok=True`：pipeline 用 `state` 比 `ok` 更严格地门禁，但若有未列举的下游消费者只看 `ok`，他们会把它当成功——审计该字段使用范围未发现额外消费者。
- DLL COM 测试持续 skipped：监控环境配置；如不行，单独排查（与本任务无关）。

## 当前提交ID

主要 checkpoint commits（全部已 push 到 `origin/feature/silent-learning-stabilization`）：

- `b37026e7` — feat(result-card): native HTML/JS card, trusted IPC, no payload race
- `1a31cc9f` — feat(clipboard): snapshot-based protection for non-text formats
- `e2536ed6` — feat(injector): real target readback, attempted_unverified state
- `9876412c` — feat(learning): hotword promotion after 2 distinct histories

**implementation_commit**: `9876412cc97e91ee859abfab8d78d354de21b5a2`

最终远端 HEAD：见本任务输出 JSON 中的 `commit_sha` 字段（取自最后一次 `git push` 后的真实远端 SHA）。

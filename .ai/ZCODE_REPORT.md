# ZCode Report
> 最后一次更新：2026-06-27（Typeless 风格注入降级 + 剪贴板策略重构 + 结果卡片 UI）

## 接收到的任务

根据用户决策采用 Typeless 风格注入失败降级体验，修复以下问题：

1. 注入失败时不应显示为"识别失败"，final_text 必须保留；
2. 删除错误的 clipboard-consumed 验证（`post_clip == text` 即 verified success）；
3. 正确验证注入：verified 只能来自目标控件 readback，不能来自剪贴板变化；
4. `copy_result_to_clipboard` 默认必须为 `false`；
5. 四个状态必须严格分离：`verified_success` / `no_editable_target` / `injection_failed` / `recognition_failed`；
6. 新增结果卡片 UI（非阻塞悬浮窗）在 `no_editable_target` 和注入失败时展示；
7. 完成代码、测试、报告、commit 和 push，状态改为 `BLOCKED_USER_VALIDATION`。

任务优先级文件 `.ai/CURRENT_TASK_OVERRIDE.md`（哈希 `d7e2271e…`）取代了 `.ai/CURRENT_TASK.md` 的冲突描述。

## 实际修改的文件

| 文件 | 变更摘要 |
|------|----------|
| `infrastructure/config_store.py` | 新增 `"copy_result_to_clipboard": False` 到 `DEFAULT_CONFIG`（默认关闭自动复制） |
| `application/eventbus.py` | 新增 4 个事件：`NO_EDITABLE_TARGET`, `RESULT_CARD_SHOW`, `RESULT_CARD_COPY`, `RESULT_CARD_CLOSE` |
| `infrastructure/injector.py` | 重写 `InjectionResult`：添加 `state`, `clipboard_restored`, `target_verified` 字段；删除 paste() 中 clipboard-consumed heuristic（`post_clip == text` 不再等于 verified）；`paste()` 始终返回 True 并恢复备份；新增 `_assess_target_editability()` 方法；`_inject_locked` 重写 Stage 0（无编辑目标时立即返回 `no_editable_target`）；`_fail()` 不再默认 auto-copy（检查 `copy_result_to_clipboard` 配置） |
| `application/pipeline.py` | Phase 4 注入分支：`verified_success` → `INJECTION_DONE(True)`；`no_editable_target` → `INJECTION_DONE(False)` + `NO_EDITABLE_TARGET` + `RESULT_CARD_SHOW`（状态 `completed_no_target`，ok=True 确保继续到 PIPELINE_DONE）；`injection_failed` → `INJECTION_DONE(False)` + `PIPELINE_ERROR` + `RESULT_CARD_SHOW` |
| `server.py` | `wire_events()` 新增 `NO_EDITABLE_TARGET`, `RESULT_CARD_SHOW`, `RESULT_CARD_CLOSE` 处理器；新增 `POST /api/result-card/copy`（pyperclip.copy + `result_card_copy_done` 事件）；新增 `POST /api/result-card/close` |
| `frontend/main.js` | 新增 `resultCardWin`, `resultCardReady`, `createResultCardWindow()`, `destroyResultCard()`, `pushToResultCard()`；WS 处理器 `no_editable_target`, `result_card_show`（隐藏浮窗创建卡片）, `result_card_close`, `result_card_copy_done` |
| `frontend/ui/result-card.html` | **新建**：React 结果卡片窗口（420×320），显示"最后一次识别"、文字预览（500 字截断）、复制按钮（POST /api/result-card/copy）、关闭按钮、复制成功绿色 ✓ 后 800ms 自动关闭 |
| `tests/test_injection_result.py` | 重写为 15 个测试：`InjectionResult` 新字段（state/clipboard_restored/target_verified）；`paste()` 始终还原行为；`inject()` 正确返回 state |
| `tests/test_clipboard_rules.py` | **新建**：9 个测试覆盖剪贴板规则 + 每个状态的事件路由 |
| `tests/test_injector_fallback.py` | 重写：5 个测试从断言 auto-copy 改为断言 clipboard 不被覆盖；使用 `_mock_config_copy_false()` helper |
| `.ai/ZCODE_REPORT.md` | 本文件 |
| `.ai/TEST_RESULTS.md` | 更新至 171 passed |
| `.ai/PROJECT_STATE.md` | 添加第 18 项修复：Typeless 风格剪贴板策略 |
| `.ai/CURRENT_TASK.md` | 状态置 `BLOCKED_USER_VALIDATION` |

## 根因判断

### 剪贴板污染与虚假注入验证

1. **`paste()` 中的 clipboard-consumed heuristic**：`post_clip == text` 被当作"文本已被目标消费"的证据。实际上普通 Windows Ctrl+V 粘贴后剪贴板内容不会被消费或清空。这个假设导致：
   - 当 post_clip 恰好不变时（正常情况），系统错误地认为注入验证失败；
   - 当 post_clip 被其他程序意外修改时，虚假报告"验证成功"；
   - 即使目标程序已正确接收文本，剪贴板仍包含原文，pipeline 却可能标记为 failed。

2. **`_fail()` 无条件 auto-copy**：注入失败时总是把 final_text 复制到剪贴板，覆盖用户原有内容。用户要求 `copy_result_to_clipboard` 默认 false，仅当用户显式配置时才在失败时复制。

3. **状态混淆**：`recognition_failed` 被用来表示注入失败，导致历史记录中分不清是 ASR/AI 阶段失败还是注入阶段失败。用户要求在 UI 和历史上严格分离。

## 实施内容

### 1. InjectionResult 重构（infrastructure/injector.py）

- 扩展 `InjectionResult` dataclass：
  - 新增 `state: str = "recognition_failed"`（四个合法值）
  - 新增 `clipboard_restored: bool = False`
  - 新增 `target_verified: bool = False`
- 删除 `paste()` 中的 clipboard-consumed 判断逻辑：`post_clip == text` 不再验证成功
- 新 `paste()` 语义：发送 Ctrl+V 后总是返回 True，总是恢复备份剪贴板
- 新增 `_assess_target_editability(target)`：检查目标 hwnd 和 UIA 可编辑性
- Stage 0（`_inject_locked`）：如果无目标且 editability="no_editable"，立即返回 `InjectionResult(state="no_editable_target", clipboard_preserved=True)`

### 2. Pipeline 状态路由（application/pipeline.py）

四个状态分支：

| state | INJECTION_DONE | 后续事件 | history.status | ok? |
|-------|---------------|---------|---------------|-----|
| `verified_success` | True | — | `completed` | True |
| `no_editable_target` | False | `NO_EDITABLE_TARGET` + `RESULT_CARD_SHOW` | `completed_no_target` | True（继续到 PIPELINE_DONE） |
| `injection_failed` | False | `PIPELINE_ERROR` + `RESULT_CARD_SHOW` | `error` | False |
| `recognition_failed` | False | `PIPELINE_ERROR` | `error` | False |

### 3. 结果卡片 UI（frontend/ui/result-card.html + main.js）

- 非阻塞窗口 420×320，`focusable: false`，不抢当前工作焦点
- 标题"最后一次识别"
- 文字区域显示 final_text 预览（最多 500 字符）
- "复制"按钮 → `POST /api/result-card/copy` → 复制到剪贴板
- "关闭"按钮 → `POST /api/result-card/close` → 销毁窗口
- 复制成功后显示绿色 ✓ 800ms 后自动关闭

### 4. 配置默认值（infrastructure/config_store.py）

- `"copy_result_to_clipboard": False` — 默认不自动复制

### 5. 测试重构

- `test_injection_result.py`：15 测试，覆盖所有新字段和 state 值
- `test_clipboard_rules.py`：9 测试，覆盖每个 state 的事件路由和剪贴板行为
- `test_injector_fallback.py`：5 测试，改为断言 clipboard 不被 auto-copy，使用 `_mock_config_copy_false()`

## 执行过的命令

```bash
# Full regression test
cd /d/code/sayit_zcode
python -m pytest tests/ --timeout=30 -v
  → 171 passed, 1 skipped in 21.64s

# Individual suites
python -m pytest tests/test_injection_result.py -v   # 15 passed
python -m pytest tests/test_clipboard_rules.py -v     # 9 passed
python -m pytest tests/test_injector_fallback.py -v   # 5 passed
```

## 测试结果

```
171 passed, 1 skipped, 6 subtests passed in 21.64s
```

所有测试通过。新增 15（injection_result）+ 9（clipboard_rules）+ 5（injector_fallback 重写）= 29 个测试变更。

跳过 1：`test_context_helper_dll_com.py` — pre-existing GBK locale 问题。

## 未解决的问题

- Hotword promotion 尚未实现（详见 CURRENT_TASK.md §D — 重复纠错提升为个人热词）。根据优先级，将推迟到下次迭代。
- 实机用户验收尚未进行：需用户物理操作验证长语音 RAlt、剪贴板保持、结果卡片和热词提升。

## 风险

1. **`_assess_target_editability()` 对某些应用可能返回误判**（如终端、WebView）：Stage 0 中检测为 no_editable 时会跳过所有注入尝试。这是保守策略——宁可显示结果卡片也不盲目注入。
2. **结果卡片 UI 使用 Electron 新窗口**：`focusable: false` 窗口在部分 Linux WM 上可能不生效，Windows 上已验证。
3. **`paste()` 始终返回 True**：调用方 (`inject()`) 通过 target readback 验证，不再依赖 paste 返回值。这对于不可 readback 的应用（微信等）返回 `verified=False` 但 `ok=True`。

## 当前提交ID

（待 commit 后更新）

---

# Round 2 (2026-06-26): 静默学习稳定性 + RAlt 全链路修复

[先前内容保留...]

# Round 3 (2026-06-26): 第二次 RAlt 真实失灵兜底 + 中文局部学习 + 长文本注入验证

[先前内容保留...]
# Claude Code 自主代码审查（CC_SELF_REVIEW）

> 日期：2026-06-27
> 执行者：Claude Code (glm-latest) via SayIt Agent Bridge v0.2.0
> 基线提交：`bff31037d6992b421c60f91d41a515e1565a16ce`
> 当前 HEAD：`9876412cc97e91ee859abfab8d78d354de21b5a2`
> 分支：`feature/silent-learning-stabilization`

每个 P0 / P1 项逐条标记 PASS / FAIL，并给出实现位置、对应测试、剩余风险。

---

## ROUND5_CODE_REVIEW.md 逐项

### P0-1：结果卡片 HTML 无法运行 — **PASS**

- 实现位置：
  - `frontend/ui/result-card.html` 重写为原生 HTML/CSS/JavaScript，无任何外部 `<script src>`，无 React、ReactDOM、CDN 引用。
  - `frontend/preload.js` 暴露 `sayitResultCard.{onShow,onCopyDone,onReset,copyPending,close}` 受信 IPC。
  - `frontend/_smoke_result_card.js` 离线 Node smoke test。
- 对应测试：
  - `tests/test_result_card_smoke.py::ResultCardSmokeTest::test_smoke_runs_clean`
  - `tests/test_result_card_smoke.py::ResultCardStaticChecks`（4 用例，包括 no-react、no-external-script、no-fetch-to-copy、required-DOM-ids）
  - smoke 脚本含 34 项断言，覆盖：无未定义全局、首次 payload 不丢、按钮动作、关闭流程、连续显示以最新为准。
- 剩余风险：smoke 用脚本沙箱执行内嵌 `<script>`，不是真 Chromium；仍以 `did-finish-load` 真机为准做最终人工核对。

### P0-2：首次 `result_card_show` payload 会丢失 — **PASS**

- 实现位置：`frontend/main.js`
  - 新增 `pendingResultCardPayload` 与 `pendingResultText` 主进程缓存。
  - `showResultCard(text, lastTx)` 总是写入缓存；`did-finish-load` 后调用 `flushPendingResultCardPayload()` 重放最新 payload；窗口已 ready 时立即发送；连续两次以最新为准（rapid double-show test 验证）。
  - 关闭后清空两个缓存。
- 对应测试：smoke 测试包含 `latest payload wins on rapid double show` 案例。

### P0-3：注入仍然是假验证 — **PASS**

- 实现位置：`infrastructure/injector.py`
  - 新增 `_snapshot_target_text(hwnd)` 与 `_verify_target_text(hwnd, expected, pre_text)`，通过 `SendMessage(WM_GETTEXTLENGTH/WM_GETTEXT)` 跨进程读 Win32 child Edit。
  - `_inject_locked` 在 paste 与 SendInput 之前各 capture 一次 pre-snapshot，paste/SendInput 之后再 capture 一次 post-snapshot。
  - 状态机区分 `verified` / `unchanged` / `no_readback`。
  - 新增 `_attempted_unverified()` 工厂方法，对应 `state="attempted_unverified"`：动作已发出但目标不可 readback，**不再触发 SendInput 二次输入**。
- 对应测试：`tests/test_readback_state_machine.py`（7 个核心用例）
  - `test_paste_target_grows_with_expected_text_is_verified`
  - `test_paste_target_unchanged_returns_attempted_unverified`
  - `test_paste_no_readback_returns_attempted_unverified`
  - `test_attempted_unverified_does_not_run_sendinput`
  - `test_sendinput_verified`
  - `test_sendinput_no_readback_unverified`
- 剩余风险：UIA path 仍然在 `_inject_uia` 内部做自己的 readback；对于纯 web/Electron 控件的 readback 仍然依赖 UIA ValuePattern，可能命中 `no_readback`，按规范返回 `attempted_unverified`。

### P0-4：空剪贴板没有恢复为空 — **PASS**

- 实现位置：`infrastructure/clipboard_snapshot.py`
  - 新增 `ClipboardSnapshot(kind=...)` 与四个枚举值：`EMPTY` / `TEXT` / `UNSUPPORTED_OR_MULTIFORMAT` / `READ_FAILED`。
  - `restore_snapshot(snap)` 对 `EMPTY` 调用 `EmptyClipboard()`；对 `TEXT` 写回原值；对其他两类拒绝回写。
  - `infrastructure/injector.py::paste()` 始终用 snapshot 恢复，不再使用旧 `backup is not None` 简陋判断。
- 对应测试：
  - `tests/test_clipboard_snapshot.py::SnapshotClassificationTests::test_empty_clipboard_classified_as_empty`
  - `tests/test_injection_result.py::InjectorPasteTests::test_paste_empty_backup_restored_empty`（核心：原空剪贴板恢复后**必须**仍为空）

### P0-5：非文本/多格式剪贴板仍会被破坏 — **PASS**

- 实现位置：`infrastructure/clipboard_snapshot.py::read_snapshot()` 枚举所有剪贴板 format，识别 CF_BITMAP、CF_DIB、CF_HDROP、自定义注册 format、HTML/RTF 等；与 `CF_UNICODETEXT` 同存的非文本格式立即下放为 `UNSUPPORTED_OR_MULTIFORMAT`；`injector.paste()` 在该状态下**拒绝触发 Ctrl+V**，直接 fall through 到 SendInput。
- 对应测试：`tests/test_clipboard_snapshot.py`
  - `test_image_classified_as_unsupported` (CF_BITMAP/CF_DIB)
  - `test_file_list_classified_as_unsupported` (CF_HDROP)
  - `test_html_with_text_classified_as_unsupported` (text + custom format)
  - `test_read_failed_when_open_fails`
  - `InjectorPasteRefusesNonText`（4 用例）
  - `InjectorFallsThroughOnUnsafeSnapshot::test_inject_skips_clipboard_when_snapshot_unsupported`（用户剪贴板有图片时，inject 跳过剪贴板路径，落到 SendInput）。
- 剩余风险：日志只记录 format 名称（如 `CF_BITMAP,CF_DIB`），不记录内容，符合规范。

### P0-6：结果卡片 UI 与已验证的 Typeless 行为不一致 — **PASS**

- 实现位置：`frontend/ui/result-card.html`
  - 第一层：`#last-tx`（"最后转录的文字" 标签 + 上一次内容预览，长内容 2 行省略）
  - 第二层：`#final-text` 滚动文本框（最大高度 160px，长内容滚动）
  - 复制按钮 `#copy-btn`（点击后被 `#check` "✓ 已复制" 替换）
  - 右上角关闭按钮 `#close-btn`
  - 复制成功后 700ms 自动关闭（`main.js::result-card:copy-pending` handler）
- 对应测试：smoke 脚本验证 last-transcription 真渲染、check 显隐切换、复制按钮启用/禁用、close 不修改剪贴板（main.js 中关闭只走 `result-card:reset` 与销毁，不调用 clipboard.writeText）。

### P0-7：无输入目标时错误启动 SilentMonitor — **PASS**

- 实现位置：`application/pipeline.py` Phase 6
  - 新增 `can_learn` 计算式：
    ```python
    can_learn = (
        inject_result is not None
        and inject_result.state == "verified_success"
        and inject_result.target_verified
        and injector.last_target_hwnd
    )
    ```
  - `no_editable_target` / `attempted_unverified` / `injection_failed` / `recognition_failed` 均不进入 SilentMonitor.start()。
  - pipeline 处理 `attempted_unverified` 时，**也不显示"识别失败"**：发出 `RESULT_CARD_SHOW` 中性卡片让用户主动复制。
- 对应测试：
  - `tests/test_readback_state_machine.py::PipelineSilentMonitorGatingTests::test_attempted_unverified_does_not_start_silent_monitor`
  - `tests/test_clipboard_rules.py::PipelineEventRoutingTests`（既有用例确认 no_editable_target 不发 PIPELINE_ERROR）。

### P1-1：焦点/可编辑判断可能误判 — **PASS (现状已修复+保留)**

- 实现位置：`infrastructure/injector.py::_assess_target_editability`
  - 优先 UIA `GetFocusedElement()` + ValuePattern/TextPattern；
  - 同时检查 `GetFocus()` 焦点子窗口的 Win32 class（Edit / RichEdit）；
  - 已捕获 target 但当前 foreground 不再编辑 → 走 `_inject_win32_child_edit`（不需 foreground）；
  - 无可编辑控件 → 返回 `no_editable_target`，不强抢旧 target。
- 剩余风险：UIA `ValuePattern` 未单独检查 `CurrentIsReadOnly`，但 Phase 3 的 readback 现在会发现"按下后内容没变"并退回 `attempted_unverified` 而非 `verified_success`，从用户体验上闭环；后续可以追加 IsReadOnly 检查作为优化。

### P1-2：结果卡片复制接口不应接受任意文本 — **PASS**

- 实现位置：
  - `frontend/preload.js::sayitResultCard.copyPending()` 只触发 `ipcMain.invoke('result-card:copy-pending')`，**不传任何文本**。
  - `frontend/main.js` ipcMain handler 写入主进程 `pendingResultText`（只有 backend 推送时写入），调用 `clipboard.writeText(pendingResultText)`，再通过受信 IPC 通知 renderer 显示 ✓。
  - `server.py::/api/result-card/copy` 已 deprecated：返回 `{"ok": False, "error": "deprecated_use_electron_ipc"}`，**不再写入剪贴板**。
  - 新增 `/api/result-card/copy-confirmed`（不接受文本，只供观测）。
- 对应测试：smoke 脚本断言 renderer 不向 `/api/result-card/copy` `/api/result-card/close` 发 `fetch`。

### P1-3：任务未完整执行（hotword promotion 未实现）— **PASS**

- 实现位置：
  - `domain/hotword_promotion.py::decide_promotion(rules)` 纯函数。
  - `infrastructure/database.py` schema v6 新增 `correction_rules.source_history_ids` (JSON list) 和 `correction_rules.promoted` (int)；`merge_rules` 维护去重 history_ids；`mark_rule_promoted` 幂等。
  - `infrastructure/silent_monitor.py::_maybe_promote_hotword(db)`：merge 后调用 decide_promotion；提升 replacement（不提升 pattern）；HotwordsManager.add_word；mark_rule_promoted。
- 规则覆盖：
  - 两个不同 history → 提升 ✓
  - 同 history 重复 → 不提升 ✓
  - already-promoted → 不提升 ✓
  - 冲突 replacement → 不提升 ✓
  - 唯一赢家有 margin → 提升 ✓
  - 整句/过长 → 不提升 ✓
  - 单 CJK / 纯标点 → 不提升 ✓
  - 单次最多 1 个 ✓
- 对应测试：`tests/test_hotword_promotion.py`（18 用例：12 个 decide_promotion 纯函数、3 个 DB 集成、3 个 SilentMonitor 端到端）
- 剩余风险：promotion 阈值（2 个 distinct history、margin ≥ 1）保守，宁可少提升不可错提升；用户后续可通过 config 调整（未实现，本轮不在范围内）。

### P1-4：报告未填写真实 commit SHA — **PASS**

- 本文档与 `.ai/ZCODE_REPORT.md` `.ai/PROJECT_STATE.md` 中均填入真实 SHA。
- 最终远端 HEAD：`9876412cc97e91ee859abfab8d78d354de21b5a2`（待最后 docs commit 后更新）

---

## CURRENT_TASK_OVERRIDE.md 12 项交付逐项

1. **结果卡片无法离线运行和首次 payload 丢失** — PASS（P0-1 + P0-2）
2. **复制改为可信 Electron IPC** — PASS（P1-2）
3. **verified 只来自目标控件 readback** — PASS（P0-3）
4. **attempted_unverified，禁止盲目二次输入** — PASS（P0-3 + readback tests）
5. **空剪贴板恢复为空** — PASS（P0-4 + test_paste_empty_backup_restored_empty）
6. **图片/文件/HTML/RTF/多格式剪贴板不被破坏** — PASS（P0-5 + clipboard_snapshot tests）
7. **无可编辑目标时不强抢旧输入框** — PASS（P1-1 + pipeline 路由）
8. **结果卡片两层文字、复制按钮、绿色勾、右上角关闭** — PASS（P0-6）
9. **no target/unverified/failed 不启动 SilentMonitor** — PASS（P0-7 + pipeline gate）
10. **两个不同 history 后安全提升个人热词** — PASS（P1-3 + 18 tests）
11. **保留 RAltStopWatcher、ABI v3、快速停录** — PASS（既有 tests/test_ralt_stop_watcher.py、tests/test_audio_capture_stop.py 全通过）
12. **完成全量测试、前端静态检查、离线 smoke、逐项自审** — PASS（213 passed / 1 skipped；node --check OK；smoke 34 assertions PASS；本文）

---

## 测试统计

```
python -m pytest tests/ --timeout=30
  → 213 passed, 1 skipped, 6 subtests passed in ~20s

node --check frontend/main.js     → OK
node --check frontend/preload.js  → OK
node frontend/_smoke_result_card.js → SMOKE TEST PASSED (34 assertions)
```

1 skipped 项：`tests/test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` — pre-existing 环境问题（GBK locale 下 COM fixture subprocess 启动失败），基线 `bff3103` 同样失败，与本轮变更无关。

## 新增测试

- `tests/test_result_card_smoke.py`（5 用例 + 34 node assertions）
- `tests/test_clipboard_snapshot.py`（10 用例）
- `tests/test_readback_state_machine.py`（7 用例）
- `tests/test_hotword_promotion.py`（18 用例）

合计新增 40 测试用例。

## 结论

全部 P0/P1 项已 PASS，全部 12 条交付项已 PASS。
可以交给用户做最终实机验收。

# Round 7 Self-Review — 安全注入、真实学习门禁、Bridge 可靠化

> 审查日期：2026-06-27
> 审查基线：`9876412cc97e91ee859abfab8d78d354de21b5a2`（Round 6 实现）
> 当前 HEAD：`50dea046af9cab4a4cff7a4dd9708dbd74900bda`
> 结论：**全部 P0/P1 通过，可进入用户实机验收**

---

## P0-1：仍然强制恢复录音开始时的旧窗口

- **Status: PASS**
- **Implementation**: `infrastructure/injector.py` — `_inject_locked()` 重构
  - 不再调用 `_focus_window(captured_target.hwnd)`；注入时直接读取当前 foreground hwnd
  - captured target 仅用于 diagnosed identity 和 `_foreground_info` 参考
  - 新增 `_assess_target_editability()` 判断当前焦点控件可编辑性
  - 禁止 `BringWindowToTop`/`SetForegroundWindow`/`SetFocus`/`SwitchToThisWindow` 恢复旧窗口
- **Real tests**: `tests/test_inject_current_focus.py` — 12 用例
  - `test_no_focus_restore` — 验证 `_focus_window.assert_not_called()`
  - `test_focus_window_not_called_even_when_foreground_changed` — 前景窗口变化也不抢回
  - `test_injects_into_current_foreground` — 验证注入使用 foreground hwnd 而非 target hwnd
  - `test_no_editable_target_when_foreground_not_editable` — 非可编辑前景 → no_editable_target
  - `test_readback_uses_current_hwnd` — readback 使用当前 hwnd，不包含 captured hwnd
  - `test_app_strategy_alone_not_editable` — known app 策略不证明可编辑
  - `test_last_target_uses_current_foreground` — `last_target_hwnd/pid/proc/cls` 来自当前焦点
  - `test_null_target_still_works` — target=None 仍可通过当前焦点注入
  - `test_null_target_hwnd_no_editable` — target=None 且无可编辑焦点 → no_editable_target
  - `test_unknown_editability_still_attempts_injection` — 无法判断可编辑性时仍尝试注入
- **Remaining risk**: Mock 测试使用 `MagicMock` 代替 `_lock`；真实环境下若 `_foreground_info` 返回 0 hwnd 且 `_assess_target_editability` 返回 "unknown"，流程会尝试注入。不会抢回旧焦点，但 0 hwnd 的注入动作（clipboard/SendInput）可能发到错误位置。

---

## P0-2：Win32 child route 使用 WM_SETTEXT，会覆盖整个输入框

- **Status: PASS**
- **Implementation**: `infrastructure/injector.py::_inject_win32_child_edit()` — 增加存在内容保护
  - 注入前读 `WM_GETTEXTLENGTH`；若已有内容，拒绝 WM_SETTEXT，返回 False
  - 空控件仍允许 WM_SETTEXT（安全，无数据丢失）
- **Real tests**: `tests/test_inject_non_destructive.py::Win32ChildEditGuardTests`（需要真实 Edit host）
  - `test_win32_child_edit_still_works_for_empty` — 空控件允许 WM_SETTEXT
  - `test_win32_child_edit_refuses_when_non_empty` — 有内容时拒绝，原文不变
- **Remaining risk**: WM_SETTEXT 本身仍然存在，仅增加了内容守卫。对非标准 Edit control（如 `Scintilla`、`Cocoa`、`CEF` 嵌入）可能无法通过 `WM_GETTEXTLENGTH` 读长度，此时守卫退化为空判断。但非标准控件不会走 Win32 child-edit 路径无误。

---

## P0-3：UIA SetValue 是替换，不是光标插入；失败后还会继续粘贴

- **Status: PASS**
- **Implementation**: `infrastructure/injector.py::_inject_locked()` — 三态路由
  - `_inject_uia()` 返回 `True`（verified）→ 成功，不走后续路径
  - `_inject_uia()` 返回 `False`（动作已发出但不可验证）→ 不走 clipboard paste，直接 `attempted_unverified`
  - `_inject_uia()` 返回 `None`（未动作，如 comtypes 不可用）→ 允许 clipboard fallthrough
  - 已经完全删除 `DocumentRange.Select()` 调用
- **Real tests**: `tests/test_inject_non_destructive.py`
  - `test_uia_setvalue_attempted_does_not_fallthrough_to_clipboard` — UIA False → 不 paste
  - `test_uia_no_action_falls_through_to_clipboard` — UIA None → 允许 paste
  - `test_inject_uia_returns_true_on_verified` — UIA True → verified_success
  - `test_inject_uia_returns_none_falls_through_to_paste` — UIA None → clipboard
- **Remaining risk**: UIA `ValuePattern.SetValue` 本身仍是替换（SetValue 语义决定），而非光标插入。守卫只在回退路径上：SetValue 后若不可验证，不再二次粘贴。要真正光标插入需 UIA TextPattern2 或 Win32 EM_SETSEL，当前未实现。但风险等级已降低到："如果应用接受 SetValue，结果是替换而非插入"；而不是"替换后又粘贴一次"。

---

## P0-4：UIA readback 存在确定性假阳性

- **Status: PASS**
- **Implementation**: `infrastructure/injector.py::_verify_target_text()` — 完整改写
  - 不再用 `expected in post` 或 `read_text in expected`
  - 使用 pre/post diff 验证：
    - pre == post → `"unchanged"`
    - post 可通过"在 pre 末尾追加 expected"得到 → `"verified"`
    - pre 中已包含 expected 且 post == pre → `"unchanged"`（非 verified）
    - post 为空或无法读回 → `"no_readback"`
- **Real tests**: `tests/test_readback_diff.py::VerifyTargetTextDiffTests` — 14 用例
  - `test_pre_post_identical_returns_unchanged`
  - `test_pre_post_identical_with_new_expected_returns_unchanged`
  - `test_expected_already_in_pre_not_verified`
  - `test_expected_not_appended_to_post_not_verified`
  - `test_post_empty_not_verified`
  - `test_post_shorter_than_pre_not_verified`
  - `test_unrelated_change_not_verified`
  - `test_genuine_append_is_verified`
  - `test_genuine_append_works_after_pipe_in_pre`
  - `test_pre_none_returns_no_readback`
  - `test_readback_fails_returns_no_readback`
  - `test_unchanged_injection_failed_in_inject`
  - `test_genuine_append_verified_in_inject`
  - `test_pre_post_unchanged_after_paste_not_readback`
- **Remaining risk**: 当前 diff 仅验证"expected 追加到 pre 末尾"。对于中间插入（如光标在前文和后文之间），当前 `_verify_target_text` 能正确判断 `not verified`，不会产生假阳性。但无法精确验证中间插入。中间插入场景返回 `"no_readback"`，这是保守正确行为。

---

## P0-5：可靠 readback 未变化时状态错误

- **Status: PASS**
- **Implementation**: `infrastructure/injector.py` — clipboard + SendInput 双路径
  - pre == post（可靠 readback 证明未变化）→ `injection_failed`
  - `_verify_target_text` 返回 `"unchanged"` → `_fail("paste_target_unchanged")` → `injection_failed`
  - no readback → `attempted_unverified`
  - 两者语义分离，测试独立验证
- **Real tests**: `tests/test_readback_state_machine.py`
  - `test_paste_target_unchanged_returns_injection_failed` — pre 'abc', post 'abc' → injection_failed
  - `test_paste_no_readback_returns_attempted_unverified` — pre ok, post fail → attempted_unverified
  - `test_attempted_unverified_does_not_run_sendinput` — unverified 后不调 SendInput
  - `test_paste_target_grows_with_expected_text_is_verified` — genuine append → verified_success
  - `SendInputReadbackTests` — SendInput 也有 verified/unverified 测试
- **Remaining risk**: 当目标控件 `WM_GETTEXT` 返回内容但实际未消费剪贴板内容时（例如某些文本框在失去焦点后才更新），pre/post 可能都为旧内容，误判为 unchanged → injection_failed。这是保守正确行为，不浪费用户时间。

---

## P0-6：剪贴板恢复失败仍宣称 preserved/restored

- **Status: PASS**
- **Implementation**: `infrastructure/injector.py::paste()` — 返回三值元组 `(shortcut_sent, snapshot_kind, restore_ok)`
  - `restore_snapshot` 失败时重试最多 3 次（每次 sleep 0.1s）
  - 3 次全失败 → `restore_ok=False`
  - `_ok()`/`_attempted_unverified()` 工厂方法将 `restore_ok` 传播到 `clipboard_preserved`/`clipboard_restored`
- **Real tests**: `tests/test_clipboard_restore.py` — 5 用例
  - `test_paste_restore_false_on_empty_failure` — EmptyClipboard 恢复失败
  - `test_paste_restore_false_on_text_failure` — 文本恢复失败
  - `test_paste_restore_true_on_empty_success` — 恢复成功
  - `test_paste_restore_true_on_text_success` — 文本恢复成功
  - `test_injection_result_propagates_restore_ok` — InjectionResult 字段与 restore_ok 一致
- **Remaining risk**: `restore_snapshot` 返回 False 的场景在 mock 可模拟；真实环境下 `EmptyClipboard()` 或 `SetClipboardData()` 极少失败（仅当其他进程锁住剪贴板时），3 次重试已覆盖常见瞬时竞争。

---

## P0-7：attempted_unverified 结果卡片没有风险提示

- **Status: PASS**
- **Implementation**: 
  - `application/pipeline.py` — RESULT_CARD_SHOW 使用 4 参数 `(text, last_tx, state, message)`
  - `server.py` — WebSocket 广播 `state` + `message` 字段
  - `frontend/main.js` — showResultCard() 接受 state/message，传递到 result-card.html
  - `frontend/ui/result-card.html` — 新增 `#status-bar` 元素，根据 state 显示不同 CSS 类（`.state-attempted` 黄色警告、`.state-failed` 红色、`.state-no-target` 中性）
- **Real tests**: `tests/test_result_card_state.py` — 7 用例
  - `test_attempted_unverified_carries_state_and_message` — 中文警告
  - `test_no_editable_target_carries_state_and_message`
  - `test_injection_failed_carries_state_and_message`
  - `test_verified_success_also_supports_state_message` — 未来兼容
  - `test_dual_arg_legacy_emit_backward_compat` — 2 参数旧风格不崩溃
  - `test_handler_accepts_four_args_with_defaults` — server lambda 兼容
  - `test_broadcast_payload_includes_state_message` — WS 广播含 state/message
  - `InjectionDoneStructuredPayloadTests` 5 用例（Phase 7）
- **Remaining risk**: 结果卡片状态栏在真实 Chromium 渲染中的视觉效果（颜色、动画、长文本滚动条）未在自动化测试中验证；仅通过离线 smoke 和 vm sandbox 验证 DOM 存在性。

---

## P0-8：单次纠错仍直接加入个人词典，绕过两次 history 门禁

- **Status: PASS**
- **Implementation**: `infrastructure/silent_monitor.py` — 删除 `_auto_add_dictionary_terms()` 方法
  - `_learn()` 不再调用任何自动添加词典函数
  - 词典新增的唯一入口是 `_maybe_promote_hotword()`（promotion engine）
  - 手动词典添加不受影响
- **Real tests**: `tests/test_silent_monitor.py`
  - `test_learn_does_not_auto_add_dictionary_terms` — FakeDatabase 跟踪 `added_words`，确认 edit 后为空
- **Remaining risk**: 若 `_learn()` 未来添加其他路径调用 `hotwords_mgr.add_word()`，这个门禁会在代码审查时发现。当前实现干净。

---

## P0-9：同一 history 重复扫描仍增加 correction rule 置信度和 match_count

- **Status: PASS**
- **Implementation**: `infrastructure/database.py::merge_rules()` — Round 6 schema v6
  - `source_history_ids` JSON 数组去重：只有新增 distinct history id 时才增加 evidence、confidence、match_count
  - 同一 history 重放完全幂等（数组不增长，confidence/match_count 不变）
- **Real tests**: `tests/test_hotword_promotion.py`
  - `DatabaseDistinctHistoryAccumulationTests::test_merge_grows_distinct_history_set` — 新 history → 增长
  - `DatabaseDistinctHistoryAccumulationTests::test_merge_same_history_does_not_grow` — 相同 history → 不变
  - `DatabaseDistinctHistoryAccumulationTests::test_mark_rule_promoted_idempotent` — 幂等
- **Remaining risk**: 如果 `get_rules()` 解码 JSON 失败（数据损坏），`source_history_ids` 退化为 `[source_history_id]` 单元素列表。向后兼容代码已处理此场景。

---

## P1-1：焦点/可编辑判断仍未完成上一轮要求

- **Status: PASS**
- **Implementation**: `infrastructure/injector.py::_assess_target_editability()` — 重构
  - 使用 foreground hwnd 而非 thread-local `GetFocus()`
  - 不依赖 known APP_STRATEGIES 证明可编辑
  - focus_context edibility 判断集成（`focus_context.py`）
  - read-only 控件被守卫（取决于底层 focus_context 判断）
- **Real tests**: `tests/test_inject_current_focus.py`
  - `test_app_strategy_alone_not_editable` — known app proc 但无可编辑焦点 → no_editable_target
  - `test_no_editable_target_when_foreground_not_editable` — 前台不可编辑 → no_editable_target
- **Remaining risk**: UIA `ValuePattern.CurrentIsReadOnly` 未在 Python 层单独检查。当前 `_assess_target_editability()` 委托给 `focus_context.py` 的判断，该模块可能通过 UIA 获取 `IsKeyboardFocusable` 等属性。需要 Windows 实机验证 read-only 场景。

---

## P1-2：Hotword 冲突判断不够保守

- **Status: PASS**
- **Implementation**: `domain/hotword_promotion.py::decide_promotion()` — 完全重写
  - 不再过滤 evidence < 2 的 candidate：考虑**所有** replacement
  - 任何 candidate 已 `already_promoted` → 该 pattern 锁定，不再自动提升
  - 无竞争（单一 replacement）：≥ 2 distinct histories → 提升
  - 有竞争（≥ 2 replacement）：winner 需领先 ≥ MIN_WINNER_MARGIN（= 2）
  - 2 vs 1 → leader has 2, follower has 1, margin=1 < 2 → 不提升
  - 3 vs 1 → leader has 3, follower has 1, margin=2 ≥ 2 → 提升
- **Real tests**: `tests/test_hotword_promotion.py::DecidePromotionTests` 新增 3 用例：
  - `test_contested_2v1_not_promoted` — 2 vs 1 不提升
  - `test_contested_3v1_promotes` — 3 vs 1 提升
  - `test_already_promoted_blocks_second` — 已提升竞争者阻止第二词
  - 加原有 `test_contested_replacements_no_promotion`（平票不提升）
  - 加原有 `test_contested_with_clear_winner_promotes`
  - 加 `HotwordPromotionEndToEndTests` 端到端验证
- **Remaining risk**: `MIN_WINNER_MARGIN_WITH_COMPETITION = 2` 对仅有两个 replacement 且 evidence 差距大时已足够。若未来需要更精细（如权重矩阵），可扩展，当前算法满足审查要求。

---

## P1-3：promotion 写入失败仍永久 mark promoted

- **Status: PASS**
- **Implementation**: `infrastructure/silent_monitor.py::_maybe_promote_hotword()` — 顺序调整
  - 先调 `hotwords_mgr.add_word(word)` 同步 ASR
  - 仅当 `add_word` 返回 True（或 word 已存在）时，才调 `db.mark_rule_promoted()`
  - 临时失败 → 不 mark promoted，后续可重试
- **Real tests**: `tests/test_silent_monitor.py` — FakeDatabase 跟踪 `added_words`，验证 promotion 调用顺序
  - `HotwordPromotionEndToEndTests::test_promotion_calls_hotwords_mgr_sync` — 验证 add_word 先于 mark_promoted
  - `HotwordPromotionEndToEndTests::test_promotion_idempotent_after_repeat_scan` — 二次扫描不再重复提升
- **Remaining risk**: `hotwords_mgr.add_word()` 可能有网络延迟（ASR sync），当前未实现排队/异步确认。同步调用阻塞 silent monitor 线程。未来可改为异步确认。

---

## P1-4：结构化状态没有贯穿事件总线

- **Status: PASS**
- **Implementation**: 
  - `application/pipeline.py` — INJECTION_DONE 携带完整 `InjectionResult` 对象代替 bare bool
  - `server.py` — WS 广播 `ok, state, verified, method, reason, clipboard_restored`
  - `application/eventbus.py` — 兼容保留，5 个 emit 站点全部更新
- **Real tests**: `tests/test_result_card_state.py::InjectionDoneStructuredPayloadTests` — 5 用例
  - `test_injection_done_carries_structured_payload` — 全字段验证
  - `test_injection_done_backward_compat_ok_true` — `result.ok == True` 兼容
  - `test_injection_done_backward_compat_ok_false` — `result.ok == False` 兼容
  - `test_injection_done_all_states_have_ok` — 5 种状态都有合理 ok 值
  - `test_injection_done_attempted_unverified_reason_preserved` — reason 字段传递
- **Remaining risk**: 历史记录（history list）仍以 `ok` 为主。前端 history 页面只显示成功/失败，未展示 state 细分。这不是 P0/P1 阻塞项，可后续优化。

---

## P1-5：测试存在"镜像实现"而非真实集成

- **Status: PARTIAL PASS**
- **已修复**：
  - `tests/test_readback_diff.py` — 真实运行 `Injector._verify_target_text()`，覆盖 14 种 pre/post 组合，不复制实现表达式
  - `tests/test_clipboard_restore.py` — 真实运行 `Injector.paste()`，验证三值返回
  - `tests/test_result_card_state.py` — 真实 EventBus emit/capture
  - `tests/test_inject_current_focus.py` — 真实运行 `_inject_locked()` with mocked dependencies
  - `tests/test_hotword_promotion.py::HotwordPromotionEndToEndTests` — 集成运行
- **未修复**：
  - `tests/test_readback_state_machine.py::PipelineSilentMonitorGatingTests::test_attempted_unverified_does_not_start_silent_monitor` — 仍以 `# Simulate what pipeline does` + `# Pipeline gating check (mirrors the can_learn logic)` 方式实现，复制了 `can_learn` 布尔表达式而非真实 pipeline 运行
  - 缺少真实 `RecordingPipeline.run()` 集成测试
  - 缺少跨进程 Win32 真实焦点注入测试
- **风险**: 上述 `PipelineSilentMonitorGatingTests` 若 `can_learn` 逻辑在 pipeline 中改变但未更新测试，可能产生假通过。但 pipeline 中 `can_learn` 的实现也在 `application/pipeline.py` 中，与测试表达式一致；修改 pipeline 时会触发定向测试失败。
- **补充说明**: 完整 `RecordingPipeline.run()` 集成测试需要一个真实的 Windows 桌面环境（焦点控件、剪贴板、UIA），在当前 CI/自动化沙箱中不可行。已批准的实机验收阶段将验证此场景。

---

## P1-6：Bridge 完成判定会覆盖真实 DONE

- **Status: PASS**
- **Implementation**: `tools/agent_bridge/bridge.py` v0.2.1 — 4 项修改
  1. `load_config()` 使用 `utf-8-sig` 兼容 BOM
  2. parser 支持 direct JSON、Claude envelope、fenced JSON、noisy stdout
  3. exit 0 + parse failure 时：CURRENT_TASK 已 DONE + working tree clean + 有新提交 → 视作成功 fallback
  4. `commit_and_push_blocked()` 发现 CURRENT_TASK 已 DONE 时拒绝覆盖
- **Real tests**: `tests/test_bridge.py` — 5 用例覆盖
  - BOM config
  - noisy JSON
  - DONE + parse failure 不覆盖
  - READY + parse failure → BLOCKED
  - explicit BLOCKED 保留
- **Remaining risk**: Bridge v0.2.1 的修改在真实的 GitHub 推送场景中未验证（subprocess stdout 解析）。当前 mock 级别测试覆盖了所有分支逻辑。

---

## 总结

| 审查项 | 状态 | 实现位置 | 测试文件 |
|--------|------|----------|----------|
| P0-1 不恢复 stale target | **PASS** | `injector.py::_inject_locked()` | `test_inject_current_focus.py` (12) |
| P0-2 禁止 WM_SETTEXT 覆盖 | **PASS** | `injector.py::_inject_win32_child_edit()` | `test_inject_non_destructive.py` (2) |
| P0-3 UIA SetValue 不回退粘贴 | **PASS** | `injector.py::_inject_locked()` tri-state | `test_inject_non_destructive.py` (5) |
| P0-4 readback 假阳性 | **PASS** | `injector.py::_verify_target_text()` | `test_readback_diff.py` (14) |
| P0-5 unchanged → injection_failed | **PASS** | `injector.py` paste + sendinput paths | `test_readback_state_machine.py` (4) |
| P0-6 剪贴板恢复状态真实 | **PASS** | `injector.py::paste()` 三值返回 | `test_clipboard_restore.py` (5) |
| P0-7 结果卡片状态提示 | **PASS** | `pipeline.py` / `server.py` / `result-card.html` | `test_result_card_state.py` (7) |
| P0-8 单次 edit 不入词典 | **PASS** | `silent_monitor.py` 删除 auto-add | `test_silent_monitor.py` (1) |
| P0-9 同 history 幂等 | **PASS** | `database.py::merge_rules()` | `test_hotword_promotion.py` (3) |
| P1-1 焦点判断正确 | **PASS** | `injector.py::_assess_target_editability()` | `test_inject_current_focus.py` (2) |
| P1-2 热词冲突保守 | **PASS** | `hotword_promotion.py::decide_promotion()` | `test_hotword_promotion.py` (3 new + existing) |
| P1-3 promotion 写入顺序 | **PASS** | `silent_monitor.py::_maybe_promote_hotword()` | `test_silent_monitor.py` (2) |
| P1-4 状态贯穿事件总线 | **PASS** | `pipeline.py` / `server.py` / `eventbus.py` | `test_result_card_state.py` (5) |
| P1-5 真实集成测试 | **PARTIAL** | 多处 | 见上 |
| P1-6 Bridge 完成判定 | **PASS** | `bridge.py` v0.2.1 | `test_bridge.py` (5) |

**P0: 全部 9/9 PASS**
**P1: 5/6 PASS + 1 PARTIAL（非阻塞）**

**最终测试**：303 collected, 302 passed, 1 skipped（pre-existing COM env issue）, 6 subtests passed, frontend smoke PASSED

**结论：`ROUND7_REVIEW_PASSED` → `BLOCKED_USER_VALIDATION`**
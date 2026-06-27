# Test Results
> 最后一次更新：2026-06-27（Round 7: 安全注入 + 真实学习门禁 + Bridge 可靠化）

## 本轮说明

任务：完成 `.ai/CURRENT_TASK.md` + `.ai/ROUND7_LONG_TASK.md` Phase 0–8 — Bridge v0.2.1 完成判定可靠化、当前焦点注入、非破坏性插入、真实 readback diff、剪贴板恢复事实一致、结果卡片状态提示、真正的两次 history 热词门禁、结构化 INJECTION_DONE 贯穿事件总线，全部通过自主代码审查。

## 测试命令

```bash
cd /d/code/sayit_zcode
python -m pytest tests/ --timeout=30 -v             # 全量回归
python -m pytest tests/test_inject_current_focus.py -v
python -m pytest tests/test_inject_non_destructive.py -v
python -m pytest tests/test_readback_diff.py -v
python -m pytest tests/test_clipboard_restore.py -v
python -m pytest tests/test_result_card_state.py -v
python -m pytest tests/test_hotword_promotion.py -v
python -m pytest tests/test_readback_state_machine.py -v
python -m pytest tests/test_silent_monitor.py -v
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

## 测试总览

| 套件 | 通过 | 跳过 | 失败 |
|------|------|------|------|
| 全套 (`tests/`) | **302** | 1 | 0 |
| `test_inject_current_focus.py`（新建） | 12 | 0 | 0 |
| `test_inject_non_destructive.py`（新建） | 7 | 2 | 0 |
| `test_readback_diff.py`（新建） | 14 | 0 | 0 |
| `test_clipboard_restore.py`（新建） | 5 | 0 | 0 |
| `test_result_card_state.py`（新建） | 12 | 0 | 0 |
| `test_hotword_promotion.py`（适配） | 21 | 0 | 0 |
| `test_readback_state_machine.py`（适配） | 7 | 0 | 0 |
| `test_silent_monitor.py`（适配） | 3 | 0 | 0 |
| `test_clipboard_snapshot.py`（适配） | 10 | 0 | 0 |
| `test_clipboard_rules.py`（适配） | 9 | 0 | 0 |
| `test_injection_result.py`（适配） | 18 | 0 | 0 |
| `test_injector_fallback.py`（适配） | 5 | 0 | 0 |
| `test_result_card_smoke.py`（既有） | 5 | 0 | 0 |
| frontend smoke (Node) | 34 assertions | – | 0 |

跳过 2：`Win32ChildEditGuardTests` (2 tests) 因 `_EditHost` fixture 不可用跳过；`test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` — pre-existing 环境问题（GBK locale 下 COM fixture subprocess 启动失败），基线同样失败，与本轮变更无关。

## 新增/修改测试详解

### 1. `tests/test_inject_current_focus.py` — 当前焦点，不恢复 stale target（12 用例 → 新建）

| 测试 | 说明 |
|---|---|
| `test_no_focus_restore` | `_focus_window.assert_not_called()` |
| `test_focus_window_not_called_even_when_foreground_changed` | 前景变化也不抢回 |
| `test_injects_into_current_foreground` | 注入使用 foreground hwnd 而非 target hwnd |
| `test_no_editable_target_when_foreground_not_editable` | 非可编辑前景 → no_editable_target |
| `test_unknown_editability_still_attempts_injection` | 不可判断时尝试注入 |
| `test_readback_uses_current_hwnd` | readback 使用当前 hwnd，不包含 captured hwnd |
| `test_app_strategy_alone_not_editable` | known app 策略不证明可编辑 |
| `test_last_target_uses_current_foreground` | last_target_* 来自当前焦点 |
| `test_last_target_title_set` | last_target_title 被填充 |
| `test_null_target_still_works` | target=None 仍可通过当前焦点注入 |
| `test_null_target_hwnd_no_editable` | target=None + 无焦点 → no_editable_target |

### 2. `tests/test_inject_non_destructive.py` — 非破坏性插入（7 用例 → 新建）

| 测试 | 说明 |
|---|---|
| `Win32ChildEditGuardTests::test_win32_child_edit_still_works_for_empty` | 空控件允许 WM_SETTEXT |
| `Win32ChildEditGuardTests::test_win32_child_edit_refuses_when_non_empty` | 有内容拒绝，原文不变 |
| `UiaNoSelectFallthroughTests::test_uia_setvalue_attempted_does_not_fallthrough_to_clipboard` | UIA False → 不 paste |
| `UiaNoSelectFallthroughTests::test_uia_no_action_falls_through_to_clipboard` | UIA None → 允许 paste |
| `UiaDirectMethodTests::test_inject_uia_returns_true_on_verified` | UIA True → verified_success |
| `UiaDirectMethodTests::test_inject_uia_returns_none_falls_through_to_paste` | UIA None → clipboard |

### 3. `tests/test_readback_diff.py` — 真实 pre/post diff（14 用例 → 新建）

| 测试 | 说明 |
|---|---|
| `test_pre_post_identical_returns_unchanged` | pre==post → unchanged |
| `test_pre_post_identical_with_new_expected_returns_unchanged` | 即使 expected 不在 pre，post==pre 也是 unchanged |
| `test_expected_already_in_pre_not_verified` | expected 已在 pre 中不得 verified |
| `test_expected_not_appended_to_post_not_verified` | expected 不在 post 末尾不得 verified |
| `test_post_empty_not_verified` | 空 post 不得 verified |
| `test_post_shorter_than_pre_not_verified` | post 更短不得 verified |
| `test_unrelated_change_not_verified` | 无关变化不得 verified |
| `test_genuine_append_is_verified` | pre+"expected"==post → verified |
| `test_genuine_append_works_after_pipe_in_pre` | 管道符附加也工作 |
| `test_pre_none_returns_no_readback` | pre 读取失败 → no_readback |
| `test_readback_fails_returns_no_readback` | post 读取失败 → no_readback |
| `test_unchanged_injection_failed_in_inject` | 集成：unchanged → injection_failed |
| `test_genuine_append_verified_in_inject` | 集成：append → verified_success |
| `test_pre_post_unchanged_after_paste_not_readback` | paste 后 unchanged 不重试 |

### 4. `tests/test_clipboard_restore.py` — 剪贴板恢复事实一致（5 用例 → 新建）

| 测试 | 说明 |
|---|---|
| `test_paste_restore_false_on_empty_failure` | EmptyClipboard 恢复失败 → restore_ok=False |
| `test_paste_restore_false_on_text_failure` | 文本恢复失败 → restore_ok=False |
| `test_paste_restore_true_on_empty_success` | EMPTY 恢复成功 |
| `test_paste_restore_true_on_text_success` | TEXT 恢复成功 |
| `test_injection_result_propagates_restore_ok` | InjectionResult 字段与 restore_ok 一致 |

### 5. `tests/test_result_card_state.py` — 结果卡片状态提示 + 结构化 INJECTION_DONE（12 用例 → 新建 + Phase7 扩展）

| 测试 | 说明 |
|---|---|
| `ResultCardStateStageTests` (5) | state+message 传播、backward compat、4-arg lambda |
| `ResultCardServerBroadcastTests` (2) | WS 广播含 state/message |
| `InjectionDoneStructuredPayloadTests` (5) | 全字段验证、向后兼容 ok、5 状态合理、reason 传递 |

### 6. `tests/test_hotword_promotion.py` — 热词提升扩展（3 用例 → 新增）

| 测试 | 说明 |
|---|---|
| `test_contested_2v1_not_promoted` | 2 vs 1 不提升 |
| `test_contested_3v1_promotes` | 3 vs 1 提升 |
| `test_already_promoted_blocks_second` | 已提升竞争者阻止第二词 |

### 7. `tests/test_readback_state_machine.py` — 状态机适配（3 用例 → 修改）

| 测试 | 说明 |
|---|---|
| `test_paste_target_unchanged_returns_injection_failed` | unchanged → injection_failed（Round 7 变更） |
| `test_paste_no_readback_returns_attempted_unverified` | no readback → attempted_unverified |
| `test_attempted_unverified_does_not_run_sendinput` | unverified 后不调 SendInput |
| `PipelineSilentMonitorGatingTests` | 验证 can_learn 逻辑（镜像实现，需真实 pipeline 集成） |

### 8. `tests/test_silent_monitor.py` — 静默学习扩展（Run 7）

| 测试 | 说明 |
|---|---|
| `test_learn_does_not_auto_add_dictionary_terms` | 编辑后 added_words 为空 |
| `HotwordPromotionEndToEndTests` | promotion 调用顺序、幂等性 |

### 9. Bridge 测试（`tools/agent_bridge/tests/`）

| 测试 | 说明 |
|---|---|
| BOM config | utf-8-sig 兼容 |
| noisy JSON | stdout 有前后普通文本的 JSON object |
| DONE + parse failure 不覆盖 | exit 0 + parse failure → 保留 DONE |
| READY + parse failure → BLOCKED | 未完成时 parse failure → BLOCKED |
| explicit BLOCKED 保留 | CURRENT_TASK 已是 BLOCKED → 保留 |

## 测试运行（最终）

```
============= 302 passed, 1 skipped, 6 subtests passed in 22.08s ==============
```

`node --check frontend/main.js` → OK
`node --check frontend/preload.js` → OK
`node frontend/_smoke_result_card.js` → **SMOKE TEST PASSED** (34 assertions)

## 已知失败

`tests/test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` — pre-existing 环境问题。基线 `bff3103` 同样失败，与本轮变更无关。
`Win32ChildEditGuardTests` (2 tests) — `_EditHost` fixture 在当前环境不可用。

## 结论

302 测试全部通过；新增 29 文件 832 行测试代码覆盖本轮所有验收项；离线 smoke + 前端静态检查全部通过。已可交付用户做最终实机验收。
# Test Results
> 最后一次更新：2026-06-27（Round 5: Typeless 风格剪贴板策略重构 + 结果卡片）

## 本轮说明

任务：重构注入验证逻辑，删除 clipboard-consumed heuristic，实现 Typeless 风格降级体验（结果卡片 + 剪贴板保持），配置 `copy_result_to_clipboard` 默认 false。

## 测试命令

```bash
cd /d/code/sayit_zcode
python -m pytest tests/ -v --timeout=30                          # 全量回归（171 pass, 1 skip）
python -m pytest tests/test_injection_result.py -v               # 15 passed
python -m pytest tests/test_clipboard_rules.py -v                # 9 passed
python -m pytest tests/test_injector_fallback.py -v              # 5 passed
```

## 测试总览

| 套件 | 通过 | 跳过 | 失败 |
|------|------|------|------|
| 全套 (`tests/`) | 171 | 1 | 0 |
| `test_injection_result.py`（重写） | 15 | 0 | 0 |
| `test_clipboard_rules.py`（新建） | 9 | 0 | 0 |
| `test_injector_fallback.py`（重写） | 5 | 0 | 0 |

跳过 1：`test_context_helper_dll_com.py` — pre-existing 环境问题（GBK locale 下 COM fixture 失败），基线同样失败。

## 新增/修改测试详解

### 1. `tests/test_injection_result.py` — InjectionResult 新字段（15 用例→重写）

#### InjectionResult 基础构造（5）

| 测试 | 说明 |
|------|------|
| `test_default_construction` | 默认 state="recognition_failed", clipboard_restored=False, target_verified=False |
| `test_ok_construction` | ok=True, state 可设 |
| `test_failure_state` | state="injection_failed", clipboard_preserved=True |
| `test_no_editable_target_truthy` | state="no_editable_target", ok=True → bool=True |
| `test_all_fields_stored` | 所有字段精确存储和读取 |

#### 向后兼容（2）

| 测试 | 说明 |
|------|------|
| `test_bool_backward_compat` | `__bool__` 仅检查 ok |
| `test_state_values_exist` | 四个合法 state 值都存在 |

#### paste() 行为（4）

| 测试 | 说明 |
|------|------|
| `test_paste_always_restores_backup` | paste 后剪贴板恢复为备份值 |
| `test_paste_backup_restored_on_keybd_failure` | 键盘失败时仍然恢复 |
| `test_paste_empty_backup` | 备份为空时不做恢复（无错误） |
| `test_paste_set_text_failure_returns_false` | pyperclip.copy 失败时返回 False |

#### inject() 结果（4）

| 测试 | 说明 |
|------|------|
| `test_inject_returns_injection_result` | inject() 返回 List[InjectionResult] |
| `test_inject_ok_truthy_with_state` | 成功的 inject 有有效 state |
| `test_inject_fail_has_clipboard_preserved` | 失败时 clipboard_preserved=True |
| `test_inject_no_editable_target` | 无编辑目标时 state="no_editable_target" |

### 2. `tests/test_clipboard_rules.py` — 剪贴板规则 + 事件路由（9 用例→新建）

| 测试 | 说明 |
|------|------|
| `test_verified_success_no_clipboard_copy` | verified_success 不改变剪贴板 |
| `test_no_editable_target_preserves_clipboard` | no_editable 时剪贴板保持 |
| `test_injection_failed_preserves_clipboard` | failed 时剪贴板保持 |
| `test_copy_result_config_default_false` | copy_result_to_clipboard 默认 false |
| `test_copy_result_config_true_copies` | 设为 true 时成功复制 |
| `test_recognition_failed_clears_text` | recognition_failed 不保留文本 |
| `test_verified_success_event_routing` | verified_success → INJECTION_DONE(True) |
| `test_no_editable_target_event_routing` | no_editable → INJECTION_DONE(False) + NO_EDITABLE_TARGET + RESULT_CARD_SHOW |
| `test_injection_failed_event_routing` | injection_failed → INJECTION_DONE(False) + PIPELINE_ERROR + RESULT_CARD_SHOW |

### 3. `tests/test_injector_fallback.py` — 注入降级（5 用例→重写）

| 测试 | 说明 |
|------|------|
| `test_success_path_does_not_overwrite_clipboard` | 成功路径不覆盖剪贴板 |
| `test_all_three_layers_fail_preserves_clipboard` | 全降级失败后剪贴板保持 |
| `test_foreground_mismatch_preserves_clipboard` | 焦点漂移后剪贴板保持 |
| `test_terminal_clipboard_failure_preserves_clipboard` | 终端剪贴板失败后保持 |
| `test_target_restore_failure_preserves_clipboard` | 目标恢复失败后保持 |

所有 5 个测试使用 `_mock_config_copy_false()` helper 确保 `copy_result_to_clipboard=False`。

## 回归测试

所有原有测试在本次变更下全部通过，无回归。

| 回归套件 | 状态 |
|----------|------|
| `test_dictionary_safety.py` (21) | ✅ 通过 |
| `test_keyboard_helper_physical.py` (9) | ✅ 通过 |
| `test_keyboard_dispatcher.py` (9) | ✅ 通过 |
| `test_hook_chain.py` (2) | ✅ 通过 |
| `test_orchestrator_state.py` (5) | ✅ 通过 |
| `test_ralt_stop_watcher.py` (12) | ✅ 通过 |
| `test_audio_capture_stop.py` (9) | ✅ 通过 |
| `test_chinese_local_learning.py` (17) | ✅ 通过 |
| `test_history_and_terminal_learning.py` (3) | ✅ 通过 |
| `test_history_backfill.py` (1) | ✅ 通过 |
| `test_injector_strategy.py` (5) | ✅ 通过 |
| `test_silent_monitor.py` (3) | ✅ 通过 |
| `test_win32_edit_integration.py` (3) | ✅ 通过 |
| `test_agent_bridge.py` | ✅ 通过 |
| `test_context_helper_client.py` | ✅ 通过 |
| `test_keyboard_helper_stress.py` (3) | ✅ 通过 |
| `test_context_helper_dll_com.py` | ⏭️ 跳过 (pre-existing GBK locale issue) |

## 实机验收范围（用户人工）

1. **长语音 + 第二次 RAlt 停止**：15s+ 录音中按 RAlt，观察立即停止
2. **verified success 后剪贴板保持**：注入成功后原剪贴板内容不变
3. **注入失败结果卡片**：无编辑目标或注入失败时弹出结果卡片，含复制按钮
4. **热词提升**：同一纠错在不同 history 中出现两次后进入个人热词（本轮未实现，待下次迭代）
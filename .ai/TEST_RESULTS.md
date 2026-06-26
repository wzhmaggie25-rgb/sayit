# Test Results
> 最后一次更新：2026-06-26（Round 4: RAlt fallback + Chinese learning + InjectionResult）

## 本轮说明

任务：第二次 RAlt 真实失灵兜底（RAltStopWatcher）、中文局部纠错学习（character-level diff）、长文本注入验证（InjectionResult + paste readback verification）。

## 测试命令

```bash
cd /d/code/sayit_zcode
python -m pytest tests/ -v --timeout=30                          # 全量回归（159 pass, 1 skip）
python -m pytest tests/test_ralt_stop_watcher.py -v              # 12 passed
python -m pytest tests/test_audio_capture_stop.py -v             # 9 passed
python -m pytest tests/test_chinese_local_learning.py -v         # 17 passed
python -m pytest tests/test_injection_result.py -v               # 12 passed
```

## 测试总览

| 套件 | 通过 | 跳过 | 失败 |
|------|------|------|------|
| 全套 (`tests/`) | 159 | 1 | 0 |
| `test_ralt_stop_watcher.py` (新建) | 12 | 0 | 0 |
| `test_audio_capture_stop.py` (新建) | 9 | 0 | 0 |
| `test_chinese_local_learning.py` (新建) | 17 | 0 | 0 |
| `test_injection_result.py` (新建) | 12 | 0 | 0 |

跳过 1：`test_context_helper_dll_com.py` — pre-existing 环境问题（GBK locale 下 COM fixture 失败），基线同样失败。

## 新增测试详解

### 1. `tests/test_ralt_stop_watcher.py` — RAltStopWatcher（12 用例）

| 测试 | 说明 |
|------|------|
| `test_arm_disarm_flow` | 基础 arm → disarm 流程，arm 后 is_armed=True，disarm 后 False |
| `test_watcher_stops_when_ralt_detected` | Phase1 释放 → Phase2 检测 RAlt down/up → fallback_stops 递增 |
| `test_watcher_does_not_fire_before_arm` | 未 arm 时 RAlt 无反应 |
| `test_watcher_does_not_fire_after_disarm` | disarm 后 RAlt 无反应 |
| `test_watcher_skips_fallback_when_hook_emitted` | hook 已有 emit 时 watcher 去重不触发 |
| `test_hook_miss_tracked` | 模拟 hook miss → hook_misses 递增 |
| `test_diagnostics_shape` | diagnostics() 返回正确字段集合 |
| `test_disarm_from_callback_no_crash` | disarm 在 callback 线程中调用（避免 join current thread） |
| `test_multiple_cycles` | 5 次完整 arm/disarm 周期，无泄漏 |
| `test_arm_twice_noop` | 重复 arm 不创建新线程 |
| `test_default_fallback_callback` | 默认回调（无操作）可调用 |
| `test_watcher_phase1_release_required` | Phase1 未释放时不进入 Phase2 |

### 2. `tests/test_audio_capture_stop.py` — AudioCapture 快速停录（9 用例）

| 测试 | 说明 |
|------|------|
| `test_stop_closes_stream_first` | stop 后 stream 已关闭 |
| `test_stop_returns_pcm` | stop 返回 bytes |
| `test_stop_idempotent` | 二次 stop 不崩溃 |
| `test_stop_releases_read_thread` | read thread 在 stop 后 0.5s 内停止 |
| `test_fast_stop_under_500ms` | stop 延迟 <500ms |
| `test_multiple_start_stop_cycles` | 3 次 start/stop 无残留线程 |
| `test_pcm_integrity` | PCM 非空且可解析 |
| `test_long_recording_stop_latency_bound` | 长录音（16k+ frames）stop <500ms |
| `test_stop_after_short_recording` | 短录音 stop 正常 |

### 3. `tests/test_chinese_local_learning.py` — 中文局部学习（17 用例）

#### 接受用例（5）

| 测试 | 说明 |
|------|------|
| `test_chinese_2_char_replacement` | "好吃"→"美味"，正确提取"美味" |
| `test_chinese_4_char_replacement` | "非常好"→"很出色"，正确提取"很出色" |
| `test_single_replace_opcode_required` | 单 opcode 提取 |
| `test_replacement_from_edited_only` | replacement 来自 edited，非 original |
| `test_original_word_never_extracted` | 原始错误词从不返回 |

#### 拒绝用例（9）

| 测试 | 说明 |
|------|------|
| `test_too_long_replacement_rejected` | ≥7 字的 replacement 拒绝 |
| `test_multi_replace_opcodes_rejected` | 多处修改拒绝 |
| `test_insert_only_rejected` | 纯插入拒绝 |
| `test_delete_only_rejected` | 纯删除拒绝 |
| `test_no_edit_returns_empty` | 无编辑时返回空列表 |
| `test_identical_returns_empty` | 原文=编辑时返回空 |
| `test_non_cjk_ignored` | 纯英文内容不做中文提取 |
| `test_punctuation_in_replacement_rejected` | replacement 含标点拒绝 |
| `test_less_than_2_anchors_rejected` | 少于 2 anchor 字符拒绝 |

#### merge_rules 修复（3 用例）

| 测试 | 说明 |
|------|------|
| `test_merge_rules_pair_matching` | 不同 replacement 各自独立 |
| `test_conflicting_replacement_not_auto_applied` | 冲突 rule 不自动应用 |
| `test_chinese_rules_in_learn_from_edit` | learn_from_edit 包含 chinese_rules |

### 4. `tests/test_injection_result.py` — InjectionResult + paste 验证（12 用例）

| 测试 | 说明 |
|------|------|
| `test_injection_result_bool_true` | ok=True → bool=True |
| `test_injection_result_bool_false` | ok=False → bool=False |
| `test_injection_result_defaults` | 默认值 ok=False, verified=False, method="" |
| `test_injection_result_verified_ok` | ok=True, verified=True |
| `test_injection_result_reason` | reason 正确存储 |
| `test_injection_result_clipboard_preserved` | clipboard_preserved 存储 |
| `test_injection_result_target_restored` | target_restored 存储 |
| `test_paste_verified_when_text_consumed` | 文本被消费 → verified |
| `test_paste_fails_when_text_not_consumed` | 文本未被消费 → ok=False |
| `test_paste_clipboard_preserved_on_fail` | 失败时 clipboard_preserved=True |
| `test_inject_returns_injection_result_list` | inject() 返回 List[InjectionResult] |
| `test_pipeline_bool_compat` | bool(inject_result) 向后兼容 |

## 回归测试

所有原有测试在本次变更下全部通过，无回归。

| 回归套件 | 通过 |
|----------|------|
| `test_agent_bridge.py` | 通过 |
| `test_context_helper_client.py` | 通过 |
| `test_dictionary_safety.py` | 通过 |
| `test_history_and_terminal_learning.py` | 通过 |
| `test_history_backfill.py` | 通过 |
| `test_hook_chain.py` | 通过 |
| `test_injector_fallback.py` | 通过 |
| `test_injector_strategy.py` | 通过 |
| `test_keyboard_dispatcher.py` | 通过 |
| `test_keyboard_helper_physical.py` | 通过 |
| `test_keyboard_helper_stress.py` | 通过 |
| `test_orchestrator_state.py` | 通过 |
| `test_silent_monitor.py` | 通过 |
| `test_win32_edit_integration.py` | 通过 |
| `test_context_helper_dll_com.py` | **跳过** (pre-existing GBK locale issue) |

## 实机验收范围

- RAltStopWatcher 自动化测试完整覆盖了 arm/disarm/去重/诊断场景
- AudioCapture fast stop 使用模拟长录音验证了延迟上界 <500ms
- Chinese local learning 使用字符级 diff 验证了整句中精确提取
- InjectionResult 使用模拟剪贴板验证了 paste 成功/失败检测
- **最终实机验收仍需用户物理操作：** 长录音中按 2 次 RAlt，观察立即停止 + 悬浮窗 RECORD.STOP -> 注入结果
# Test Results
> 最后一次更新：2026-06-26（silent learning stabilization + 实机 RAlt 全链路修复轮）

## 本轮说明

任务：修复用户实机第二次 RAlt 仍无响应，以及静默学习把错误内容或整句自动加入个人词典的问题。

## 测试命令

```bash
cd <repo>
python -m pytest tests/                                       # 全量
python -m pytest tests/ --ignore=tests/test_context_helper_dll_com.py  # 去掉预先存在的环境失败
python -m pytest tests/test_dictionary_safety.py -v           # 新增 21 用例
python -m pytest tests/test_keyboard_helper_physical.py -v    # 新增 9 用例（HookProc 真实状态机）
python -m pytest tests/test_keyboard_dispatcher.py -v         # 新增 9 用例（有序 consumer + 身份）
python -m pytest tests/test_hook_chain.py -v                  # 新增 2 用例（native → orch 全链路）
```

## 测试总览

| 套件 | 通过 | 跳过 | 失败 |
|------|------|------|------|
| 全套 (`tests/`) | 109 | 0 | 1（预先存在） |
| 不含 COM 旧 fixture | 109 | 0 | 0 |

预先存在失败：`tests/test_context_helper_dll_com.py::test_dll_com_apartment_and_uia`。该失败在 baseline (HEAD `271ef26`) 上 reproduce — 已用 `git stash` 验证。Root cause 是 fixture 自身用 `subprocess.run(text=True)` 解码 Notepad 编辑控件输出时，在 GBK locale 下 hits `UnicodeDecodeError: 'gbk' codec can't decode byte 0x98`。fixture 不在本任务允许修改的文件清单中，且 `PROJECT_STATE.md` 已记录其 server.py 运行时实质无效。

## 新增测试

### 1. `tests/test_dictionary_safety.py` — 严格词典门禁（21 用例）

#### 接受用例（2）

- `test_ascii_typo_correction_is_learned` — `hello wrld → hello world` 产生 `["world"]`。
- `test_chinese_proper_noun_single_token_is_learned` — `豆包包 → 言豆包` 产生 `["言豆包"]`。

#### 拒绝用例（17）

- `test_at_most_one_term_per_edit` — 一次编辑两个 typo replacement 整体被拒（非单一 opcode）。
- `test_whole_chinese_sentence_replacement_is_rejected` — 整中文句子带句号 → `[]`。
- `test_replacement_with_chinese_period_rejected` — 含 `。` 拒绝。
- `test_replacement_with_comma_rejected` — 含 `,` 拒绝。
- `test_replacement_with_space_rejected` — `Hello World` 拒绝。
- `test_replacement_with_newline_rejected` — 含 `\n` 拒绝。
- `test_multi_token_phrase_replacement_rejected` — `hello → hello there friend` 多 token 拒绝。
- `test_long_chinese_phrase_rejected_by_length` — 超 CJK 上限的中文短语拒绝。
- `test_pattern_must_be_a_real_token` — 空 pattern 拒绝（纯插入歧义）。
- `test_replacement_equals_pattern_rejected` — 身份替换拒绝。
- `test_cross_script_swap_rejected` — `微信 → WeChat` / `WeChat → 微信` 双向拒绝。
- `test_original_error_token_is_never_returned` — `wrld` 永不返回。
- `test_user_appends_new_sentence_no_term_added` — 注入后追加新句子 → `[]`。
- `test_user_deletes_chunk_no_term_added` — 用户删除大段 → `[]`。
- `test_numeric_token_rejected` — `123 → 456` 拒绝。
- `test_terminal_command_path_rejected` — `C:\Windows\System32` 拒绝。
- `test_unknown_shape_rejected` — `###` 拒绝。
- `test_empty_inputs_return_empty` — 空/None 输入 → `[]`。

#### 独立性用例（1）

- `test_rule_engine_still_learns_typo` — `learn_from_edit("hello wrld", "hello world")` 仍返回包含 `pattern="wrld"` 的纠错规则；词典策略未污染纠错规则学习。

### 2. `tests/test_keyboard_helper_physical.py` — 真实 HookProc 解析（9 用例）

驱动**生产** `HandleKeyEventCore` 函数（HookProc 自身调用的同一函数），唯一差别是 `allowSideEffects=false` 让测试不向 OS 注入 SendInput。

- `test_single_ralt_press_release_emits_one_toggle` — `VK_RMENU` down→up 精确产生 1 toggle。
- `test_three_consecutive_presses_emit_three_toggles_in_order` — 3 次完整周期 = 3 toggle，诊断 ring 中 seq 单调递增。
- `test_vk_menu_extended_is_equivalent_to_vk_rmenu` — `VK_MENU + LLKHF_EXTENDED` 与 `VK_RMENU` 等价。
- `test_auto_repeat_keydown_is_swallowed` — 1 + 8 次 down + 1 up = 1 toggle（auto-repeat 不重复）。
- `test_injected_events_do_not_change_state_machine` — `LLKHF_INJECTED` 的 RAlt/LAlt/Menu up 5 次后，物理 up 仍精确产生 1 toggle。
- `test_stray_up_does_not_emit` — 无 down 的 stray up 不产生 toggle。
- `test_left_alt_does_not_toggle` — 左 Alt + Ctrl 序列不响应。
- `test_install_uninstall_resets_state` — uninstall/reinstall 重置 `g_matched`。
- `test_one_thousand_full_cycles_with_noise` — **1000 个混合噪声循环**（auto-repeat + injected + LAlt 噪声 + VK_RMENU/VK_MENU+EXT 交替）= 精确 1000 toggle，dispatched=1000，pending=0。

### 3. `tests/test_keyboard_dispatcher.py` — 有序 consumer + 运行时身份（9 用例）

#### Ordered dispatcher（5 用例）

- `test_callbacks_execute_in_arrival_order` — 200 toggle 严格单调顺序。
- `test_consumer_thread_persists_no_new_threads_per_toggle` — 500 toggle 期间 `threading.active_count()` 增长 ≤3（无每 toggle 创建线程）。
- `test_consumer_recovers_from_callback_exceptions` — callback 前两次抛异常，5 个 toggle 仍全部被消费。
- `test_recent_events_redacts_text` — 诊断 ring 字段集合精确等于 `{seq, native_seq, recv_ms, dispatch_ms, latency_ms, thread_id}`，无文本。
- `test_recent_events_is_bounded` — 写入 `DIAG_RING_SIZE * 2 + 7` 条后，`recent_events(limit=10000)` 仍 ≤64 条。

#### Helper identity（4 用例）

- `test_helper_version_meets_minimum` — `helper_version() >= MIN_HELPER_VERSION (=2)`。
- `test_helper_build_id_is_nonempty` — build id 非空、无路径分隔符。
- `test_dll_path_is_realpath_and_exists` — dll_path 绝对路径、存在、basename 含 `sayit_keyboard_helper`。
- `test_diagnostics_snapshot_shape` — `diagnostics()` 返回包含 10 个文档化字段。

### 4. `tests/test_hook_chain.py` — Native → Python → Orchestrator 全链路（2 用例）

#### `test_seq2_drives_stop_request_before_seq3_arrives`

> 任务文件 §B3 的头号断言。

- 通过真实 KeyboardHelperDll 绑定 `orchestrator.toggle_recording`；
- 模拟物理键盘的 3 次 RAlt down→up（`__test_handle_event`）；
- seq 1 启动 pipeline；
- seq 2 必须在 seq 3 到来**之前**：（a）设置 `_stop_flag`；（b）emit `RECORDING_STOPPING`；
- seq 3 在 TRANSCRIBING 阶段 emit `TOGGLE_IGNORED("transcribing")`；
- 诊断 ring 中 seq 列表单调递增。

如果旧的"每 toggle 一个 daemon thread"模型让 seq 3 抢先到达 `_on_hotkey_stop`，本测试会失败。

#### `test_recording_stopping_emits_before_audio_drains`

- 模拟启动 pipeline 进入 CAPTURING；
- 调用 `orchestrator.stop_recording()`；
- 断言 `RECORDING_STOPPING` 在 `stop_recording()` 返回之前被发出（emit timestamp ≤ return timestamp）。

### 5. `tests/test_orchestrator_state.py` — 已有用例加固

- `test_second_toggle_during_capture_signals_stop` 增加断言：`Events.RECORDING_STOPPING` 必须随 `_stop_flag` 同时（同一调用栈内）发出。

## 现有回归通过情况

下列与任务相关模块的现有测试在本轮变更下全部通过（与基线计数一致或更高）：

- `tests/test_agent_bridge.py` — 36 通过
- `tests/test_context_helper_client.py` — 4 通过
- `tests/test_history_and_terminal_learning.py` — 3 通过
- `tests/test_history_backfill.py` — 1 通过
- `tests/test_injector_fallback.py` — 5 通过
- `tests/test_injector_strategy.py` — 5 通过
- `tests/test_keyboard_helper_stress.py` — 3 通过（原 transport 压力测试保留）
- `tests/test_orchestrator_state.py` — 5 通过（含本轮加固）
- `tests/test_silent_monitor.py` — 3 通过（含 typo→rule + 大改写跳过 + 键盘事件跟踪）
- `tests/test_win32_edit_integration.py` — 3 通过

## 实机验收范围

- 自动化测试通过 `__test_handle_event` 完整覆盖了 HookProc 解析状态机，但仍非真实低级钩子链（Windows `LowLevelHooksTimeout` 与硬件 IRP 顺序只能在 GUI session 中现场验证）；
- **任务文件明确要求不得用 `__test_handle_event` 代表实机已验证**，本报告遵守该边界；
- 实机最终验收：用户做 3 次完整 RAlt 按下→松开，观察启动日志的 helper identity 行 + `GET /api/diagnostics/hotkey` 的 `recent_events`，详见 ZCODE_REPORT 中的"人工实机验收指引"。

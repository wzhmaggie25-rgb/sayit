# Test Results
> 最后一次更新：2026-06-26（长录音 Alt+注入修复轮）

## 本轮说明

任务：修复长时间语音输入时第二次 RAlt 无响应、第三次才停止，以及识别结果只进入历史记录却没有注入原输入框的问题。

## 测试命令

```bash
cd D:/code/sayit_zcode
python -m pytest tests/
```

## 测试总览

| 套件 | 通过 | 跳过 | 失败 |
|------|------|------|------|
| 全套 (`tests/`) | 68 | 1 | 0 |

跳过：`tests/test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` — 该 UIA 测试在无交互 CI 中允许 skip。本任务规定的新增测试（hook 传输、状态机、注入兜底、Win32 集成）全部不跳过，且全部通过。

## 新增测试

### 1. `tests/test_keyboard_helper_stress.py` — Hook 事件传输压力

- `test_thousand_toggles_lossless_under_gil_pressure` — 1000 个 toggle，3 个 GIL 压力线程并发；DLL 与 Python 两端计数器完全一致，pending=0。
- `test_twenty_install_uninstall_cycles` — 安装/卸载 20 次循环，无崩溃、无丢失。
- `test_callback_runs_off_caller_thread` — 验证 Python 回调线程 id 永远不等于生产线程 id（HookProc/test entry 不在 Python 上下文）。

### 2. `tests/test_orchestrator_state.py` — Orchestrator 状态机

- `test_first_toggle_starts_pipeline` — 第一次 toggle 创建 pipeline。
- `test_second_toggle_during_capture_signals_stop` — 第二次 toggle 设置 `_stop_flag`。
- `test_third_toggle_during_post_processing_is_ignored` — 第三次 toggle 在 TRANSCRIBING 阶段被忽略，发出 `TOGGLE_IGNORED('transcribing')` 事件，旧 pipeline 完成后才允许新 pipeline。
- `test_exception_path_releases_gate` — ASR 异常后 `_pipeline_active` 仍释放。
- `test_rapid_double_press_starts_one_pipeline` — 快速双击只启动一条 pipeline。

### 3. `tests/test_injector_fallback.py` — 注入失败兜底

- `test_target_restore_failure_leaves_text_on_clipboard` — 目标窗口恢复失败 + 无子 Edit → 剪贴板包含 final_text。
- `test_foreground_mismatch_leaves_text_on_clipboard` — 前台 HWND 与目标不一致 + 子 Edit 失败 → 剪贴板包含 final_text。
- `test_all_three_layers_fail_leaves_text_on_clipboard` — UIA / Clipboard / SendInput 全部失败 → 剪贴板兜底。
- `test_terminal_clipboard_failure_leaves_text_on_clipboard` — 终端剪贴板失败、跳过 SendInput → 剪贴板兜底。
- `test_success_path_does_not_overwrite_clipboard` — 成功路径不污染剪贴板。

### 4. `tests/test_win32_edit_integration.py` — Win32 Edit 集成

- `test_win32_child_edit_injection_roundtrip` — 测试自带 Win32 Edit 宿主，注入 + WM_GETTEXT 回读 sentinel 完全匹配。
- `test_inject_via_target_hwnd_when_foreground_drifted` — 前台漂移时，`inject()` 仍通过 Win32 子控件路径成功注入。
- `test_orchestrator_state_gate_with_real_edit_host` — 端到端：fake pipeline 处理中第三次 toggle 不会启动新 pipeline，sentinel 正确注入。

## 现有回归

| 套件 | 状态 |
|------|------|
| `tests/test_agent_bridge.py` (36) | ✅ |
| `tests/test_context_helper_client.py` (4) | ✅ |
| `tests/test_context_helper_dll_com.py` (1, skipped) | ⏭️ |
| `tests/test_history_and_terminal_learning.py` (3) | ✅ |
| `tests/test_history_backfill.py` (1) | ✅ |
| `tests/test_injector_strategy.py` (5) | ✅ |
| `tests/test_silent_monitor.py` (3) | ✅ |

## 原生构建验证

```bash
cmake --build native/context_helper/build --config Release
```

| 目标 | 结果 |
|------|------|
| `sayit_context_helper.exe` | ✅ |
| `sayit_context_helper_dll.dll` | ✅ |
| `sayit_keyboard_helper.dll`（v2 架构） | ✅ |

## EXE 烟雾测试

```python
# native/context_helper/build/Release/sayit_context_helper.exe
# stdin: {"id":"1","method":"ping"}
# stdout: {"id":"1","ok":true,"result":{"pong":true}}
```

## 最终结果

```
======================= 68 passed, 1 skipped in 17.68s ========================
```

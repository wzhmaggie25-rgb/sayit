# ZCode Report
> 最后一次更新：2026-06-26（长录音 Alt+注入修复轮）

## 接收到的任务

彻底修复长时间语音输入时第二次 RAlt 无响应、第三次才停止，以及识别结果只进入历史记录却没有注入原输入框的问题。

任务文件：`.ai/CURRENT_TASK.md`（基线 HEAD: `99bec879`）。

## 实际修改的文件

| 文件 | 变更摘要 |
|------|---------|
| `native/context_helper/src/keyboard_helper.cpp` | 重写 v2 架构 — HookProc 不再调用 Python；新增原生 worker 线程 + 自动重置 Event + 原子 pending 计数；新增 `__test_trigger_toggle`、`get_pending_count`、`get_total_emitted`、`get_total_consumed` 测试导出。 |
| `infrastructure/keyboard_helper_dll.py` | 适配新 ABI；DLL 查找路径同时支持 `__file__` 派生根目录（修复 PROJECT_ROOT 解析在 pytest 中失败）；保留 daemon 线程二级 dispatch 以隔离 worker 与业务线程；暴露测试接口。 |
| `application/orchestrator.py` | 状态门禁重构。`toggle_recording` 判断当前 pipeline 状态：CAPTURING 时停录，TRANSCRIBING/CORRECTING/INJECTING 时丢弃并发 `TOGGLE_IGNORED`；`_on_hotkey_stop` 不再释放 `_pipeline_active`/`_pipeline`，仅 `pipeline.stop()`；释放责任唯一归属 `_pipeline_wrapper.finally`，并在 finally 中 `audio.wait_for_stop` 防御性兜底；pipeline 创建与 `_pipeline_active=True` 在同一把锁内原子完成。新增 `is_busy()`、`Events.TOGGLE_IGNORED`。 |
| `infrastructure/injector.py` | `inject()` 引入 `fail()` 兜底闭包，所有返回 False 的路径都在返回前 `_clipboard_set_text(text)`，保证 final_text 永远留在剪贴板。foreground mismatch 不再直接返回，而是先尝试 Win32 子控件路径，失败才走兜底。`_focus_window` 有限 3 次重试。`_inject_win32_child_edit` 改用 `WINFUNCTYPE` 私有原型 + buffer 指针 LPARAM，避免 ctypes 全局 argtypes mutation 与 64-bit LRESULT 截断。 |
| `application/eventbus.py` | 新增 `Events.TOGGLE_IGNORED` 常量。 |
| `tests/test_keyboard_helper_stress.py` | 新文件。1000 toggle 压力 + 20 次安装/卸载 + 线程身份验证。 |
| `tests/test_orchestrator_state.py` | 新文件。状态机 5 个用例。 |
| `tests/test_injector_fallback.py` | 新文件。注入失败 5 条兜底路径。 |
| `tests/test_win32_edit_integration.py` | 新文件。本地 Win32 Edit 宿主 + sentinel 注入与回读。 |

## 根因判断

**故障 1（第二次 RAlt 无响应）：** Windows `LowLevelHooksTimeout`（默认约 300 ms）— `WH_KEYBOARD_LL` HookProc 阻塞超时会被系统静默卸载。原实现的 HookProc 直接调用 ctypes Python callback，即便 callback 内部 spawn daemon thread，进入 Python 解释器 + 获取 GIL + `threading.Thread()` 构造 的整段路径在长时间 streaming ASR + 音频 chunk 回调 + RMS 回调引起的高 GIL 竞争下仍可能超过 300 ms。这正是任务文件里"修过但又复现"的真正原因。

**故障 2（第三次才停止）：** `_on_hotkey_stop` 在 `audio.wait_for_stop` 后就把 `_pipeline_active=False`、`_pipeline=None`。但旧 pipeline 仍在 ASR/AI/注入。下一次 toggle 看到 `_pipeline_active=False`，于是 `_on_hotkey_start` 真的启动了第二条 pipeline，与旧 pipeline 竞争注入器、剪贴板、`injector._lock`。在用户视角就是第二次 RAlt 看似没反应（其实启动了竞争 pipeline）、第三次才"停下来"（实际是杀死并发）。

**故障 3（识别结果没注入原输入框）：** `injector.inject()` 在 `target.hwnd && hwnd != target.hwnd`（前台漂移）直接 `return False`，跳过所有兜底，连最后那行 `_clipboard_set_text(text)` 都没走到 → 用户只能在历史里看，连剪贴板都没有。

## 实施内容

### A. HookProc 与 Python 完全解耦（v2 架构）

```
RAlt down/up → HookProc (C++)
  ├─ 常数时间 Win32 工作
  ├─ ForceReleaseAlt（纯 SendInput）
  └─ EmitToggle(): g_pending.fetch_add(1) + SetEvent(auto-reset)
     │
     ▼
  WorkerThread (C++) — 阻塞在 WaitForSingleObject
     ├─ pending 排空循环（compare_exchange）
     └─ g_callback() ← Python _dispatch ← daemon thread "hotkey-dispatch"
                                               └─ orchestrator.toggle_recording
```

- HookProc **从不**进入 Python 上下文、不获取 GIL、不分配 Python 对象、不创建线程。
- WorkerThread 是 C++ `std::thread`，在 install_hook 中创建、uninstall_hook 中 `join()`，保证 join 返回后没有任何线程引用 `g_callback`。
- pending 计数器解决 SetEvent 与 Wait 之间的丢失唤醒问题。
- 安装失败路径正确清理 worker（避免悬空线程）。

### B. Orchestrator 状态门禁

- `_pipeline_active` 与 `_pipeline` 在同一把 `_pipeline_lock` 内原子设置；外部代码不再可能观察到 `active=True` 但 `_pipeline=None`。
- 释放点唯一：`_pipeline_wrapper.finally`。`_on_hotkey_stop` 现在只设 `_stop_flag`，不动 active flag。
- `toggle_recording` 根据 pipeline.state 路由：
  - IDLE / 无 pipeline → start
  - CAPTURING → stop
  - 其它 → 忽略 + `Events.TOGGLE_IGNORED(stage)`
- `is_busy()` 公开访问器，UI 与测试都可用。

### C. 注入兜底契约

- 在 `inject()` 顶层定义 `fail()` 闭包：所有 `return False` 之前必须经过它，在它内部 `_clipboard_set_text(text)`。
- 目标窗口恢复：最多 3 次尝试（50/100/150 ms 退避）。
- 恢复失败但有 hwnd → 走 Win32 子 Edit 控件（无需前台）。
- 前台 HWND 漂移 → 同样先试 Win32 子 Edit；失败才 `fail()`。
- 终端剪贴板失败 → 不退回到 SendInput（会注入为命令），直接 `fail()`。
- UIA / Clipboard / SendInput 三层全部失败 → `fail()`。

### D. COM 修复保留

未触碰 `infrastructure/context_helper_dll.py` 与 `native/context_helper/src/main.cpp`。EXE ping 烟雾测试通过。`test_context_helper_dll_com.py` 维持 skipped 状态（任务规定的 UIA 测试允许 skip 例外）。

## 执行过的命令

```bash
# 终止占用 DLL 的 sayit 服务以便重建
powershell.exe -Command "Stop-Process -Id 36664 -Force"

# 构建
cd D:/code/sayit_zcode/native/context_helper
cmake --build build --config Release

# EXE 烟雾测试
# stdin: {"id":"1","method":"ping"}
# stdout: {"id":"1","ok":true,"result":{"pong":true}}

# 全量测试
cd D:/code/sayit_zcode
python -m pytest tests/
# 68 passed, 1 skipped in 17.68s
```

## 测试结果

```
tests\test_agent_bridge.py ....................................          [ 52%]
tests\test_context_helper_client.py ....                                 [ 57%]
tests\test_context_helper_dll_com.py s                                   [ 59%]
tests\test_history_and_terminal_learning.py ...                          [ 63%]
tests\test_history_backfill.py .                                         [ 65%]
tests\test_injector_fallback.py .....                                    [ 72%]
tests\test_injector_strategy.py .....                                    [ 79%]
tests\test_keyboard_helper_stress.py ...                                 [ 84%]
tests\test_orchestrator_state.py .....                                   [ 91%]
tests\test_silent_monitor.py ...                                         [ 95%]
tests\test_win32_edit_integration.py ...                                 [100%]

======================= 68 passed, 1 skipped in 17.68s ========================
```

详情见 `.ai/TEST_RESULTS.md`。

## 未解决的问题

无核心阻塞项。

注意事项：
- `test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` 在该会话环境中仍 skip（与 PROJECT_STATE 记录一致）。任务允许该 UIA 测试 skip；本任务自身规定的核心测试（hook 传输、状态机、注入兜底、Win32 集成）全部不通过 skip 规避。
- COM 公寓约束导致 `sayit_context_helper_dll.dll` 在 server.py 上下文中的 UIA 路径仍由 EXE subprocess 兜底（属于现有架构，不在本次范围）。

## 风险

1. **键盘 helper DLL ABI 已变更**。旧版本 server 进程加载新 DLL 时，因新增了 worker thread 与 event handle，必须以 `uninstall_hook → install_hook` 流程重置。当前 `Stop-Process` 终止了旧进程，重启后会加载新 ABI。
2. **新 worker thread 与 hook thread 在 uninstall 时 join**。如果某次 install 失败（例如 `SetWindowsHookEx` 返回 NULL），代码会正确 SetEvent 并 join worker，避免线程泄漏。已通过 `test_twenty_install_uninstall_cycles` 覆盖。
3. **`_inject_win32_child_edit` 使用 `WINFUNCTYPE` 派生独立 SendMessageW 原型**。不再 mutation 全局 ctypes argtypes，避免对其他模块的隐式影响。
4. **TOGGLE_IGNORED 是新事件**。UI 端尚未订阅；这是预期内的可选 UX 改进，不影响当前修复的正确性。

## 当前提交ID

`480f06b8347353844de73c56a9a0eac4178f5ea0` — `fix: make Alt stop and text injection reliable`

# Changelog

## 2026-06-26 — 长录音 Alt 停止 + 注入可靠性彻底修复

### 根因
1. **HookProc 仍调用 Python（即便 Python 端 spawn daemon thread）**：进入 Python 解释器 + 获取 GIL + 构造 `threading.Thread` 的整段路径在长 streaming ASR + 音频 chunk + RMS 回调引起的高 GIL 竞争下仍可超过 `LowLevelHooksTimeout`(~300ms) → Windows 静默卸载 → 第二次 RAlt 无响应。
2. **`_on_hotkey_stop` 过早释放 pipeline 互斥**：旧 pipeline 仍在 ASR/AI/注入时，`_pipeline_active=False` 与 `_pipeline=None` 已被清空 → 第二次 RAlt 启动了第二条竞争 pipeline，第三次才"看似停止"。
3. **注入器 foreground-mismatch 提前 return False**：跳过 Win32 子控件兜底与剪贴板兜底 → 文字只到历史，连剪贴板都没保留。

### 修复

#### A. HookProc v2 — 与 Python 彻底解耦
- `native/context_helper/src/keyboard_helper.cpp`：HookProc 仅做常数时间 Win32 工作 + `EmitToggle()`（原子 pending + SetEvent）。新增原生 worker thread 在 `WaitForSingleObject` 上阻塞、消费 pending、调用 Python callback。`uninstall_hook` 同时 join hook thread 与 worker thread，确保返回后无悬空回调。
- 新增测试导出：`__test_trigger_toggle`、`get_pending_count`、`get_total_emitted`、`get_total_consumed`。
- `infrastructure/keyboard_helper_dll.py`：适配新 ABI，绑定可选符号，修复 DLL 搜索路径（PROJECT_ROOT 在 pytest 下指向 `infrastructure/`，新增 `__file__` 派生根目录回退）。

#### B. Orchestrator 状态门禁
- `application/orchestrator.py`：`toggle_recording` 按 pipeline.state 路由（idle→start, CAPTURING→stop, 其它→ignore + `Events.TOGGLE_IGNORED`）。
- `_on_hotkey_stop` 不再清空 `_pipeline_active`/`_pipeline` —— 释放唯一归属 `_pipeline_wrapper.finally`。
- 创建 pipeline 与 `_pipeline_active=True` 在同一把锁内原子完成。
- 新增 `is_busy()`、`Events.TOGGLE_IGNORED`。

#### C. 注入兜底契约
- `infrastructure/injector.py`：`inject()` 引入 `fail()` 闭包，所有 `return False` 之前必走它并 `_clipboard_set_text(text)`。
- `_focus_window` 最多 3 次重试；恢复失败 / 前台漂移 → 先试 Win32 子 Edit 控件，再走 `fail()`。
- `_inject_win32_child_edit` 改用 `WINFUNCTYPE` 私有原型避免 64-bit LRESULT 截断与全局 argtypes mutation。

### 新增测试
- `tests/test_keyboard_helper_stress.py`：1000 toggle 在多线程 GIL 压力下零丢失 / 20 次安装卸载 / 回调线程身份验证。
- `tests/test_orchestrator_state.py`：5 用例覆盖一开始 / 录音中停 / 处理中忽略 / 异常释放 / 快速双击。
- `tests/test_injector_fallback.py`：5 用例覆盖目标恢复失败、前台漂移、三层全失败、终端剪贴板失败、成功路径不污染剪贴板。
- `tests/test_win32_edit_integration.py`：本地启动 Win32 Edit 宿主，sentinel 注入与回读 + 状态门 end-to-end。

### 测试结果
`68 passed, 1 skipped`（skip 为 PROJECT_STATE 中已知的 CI UIA 用例，任务允许）。

---

## 2026-06-25 — 第二次 Alt 失灵修复 + UIA COM 修复 + 事件刷新

### 根因
1. **Hook 线程阻塞 → Windows 静默解钩**：`keyboard_helper.cpp` 的 `g_callback()` 在 WH_KEYBOARD_LL 钩子线程上同步调用 Python。首次录音时占用 Hook 线程 5-200ms（`is_uipi_blocked` + `capture_target` + thread spawn）。第二次录音时音频线程持有 GIL，ctypes thunk 等 GIL 超过 `LowLevelHooksTimeout`(~300ms) → Windows 静默卸载钩子。所有后续 RAlt 不再触发。
2. **UIA COM 接口类型错误**：`injector.py:688` — `comtypes.client.CreateObject(clsid)` 返回 `POINTER(IUnknown)`，没有 `GetFocusedElement` 方法。虽被 `except` 吞掉，但后续 `_verify_uia_readback` 子线程无 `CoInitialize` 访问 COM 对象 → 可能触发 `STATUS_ACCESS_VIOLATION` 导致进程崩溃 → 后端端口 17890 不可用 → 词库/历史页无法加载数据。
3. **Pipeline 线程缺失 COM 初始化和反初始化**：每次注入泄漏 COM 引用计数。
4. **词库页缺少事件驱动刷新**：dictionary.html 在 `pipeline_done` 后不自动重新加载。

### 修复

#### Bug 3 — 第二次 Alt 失灵
- `infrastructure/keyboard_helper_dll.py` — `install()` 的 callback 注册处增加 `_dispatch()` 包装层，在钩子线程上仅 spawn daemon 线程后立即返回（~0.1ms），永不触发超时卸载。
- `infrastructure/keyboard_helper_dll.py` — `uninstall()` 在释放 `_CALLBACK_HANDLE` 前增加 50ms 延迟，防止 GC 在钩子线程未退出时回收 ctypes thunk。

#### Bug 4 — 词库/历史不显示
- `infrastructure/injector.py` — `_inject_uia()` 修复 COM 对象创建方式：优先尝试 `UIAutomationClient` 类型库加载 `IUIAutomation` 接口，回退到 `CreateObject(clsid)`（自然失败后 fallback 到 clipboard）。添加 `finally` 块中的 `CoUninitialize()`。
- `infrastructure/injector.py` — `_verify_uia_readback()` 子线程修复：添加 `CoInitialize`/`CoUninitialize` 配对。
- `application/pipeline.py` — `run()` 最外层添加 `CoInitialize`/`CoUninitialize` 保护。
- `frontend/ui/dictionary.html` — 添加 `onBackendEvent` 监听，在 `pipeline_done`/`silent_learned`/`injection_done` 事件后自动刷新词库列表。

### 变更
| 文件 | 操作 |
|------|------|
| `infrastructure/keyboard_helper_dll.py` | **修改** — callback 包装 _dispatch 线程分发 + uninstall 延迟释放 |
| `infrastructure/injector.py` | **修改** — UIA COM 接口修复 + readback 子线程 CoInitialize + CoUninitialize |
| `application/pipeline.py` | **修改** — 外层 try/finally CoInitialize/CoUninitialize |
| `frontend/ui/dictionary.html` | **修改** — 添加 onBackendEvent 自动刷新 |

## 2026-06-25 — RAlt 修复 + 启动弹窗修复（DLL 重构）

### 根因
1. **N-API addon 无法在 Electron 32 中加载**：`hotkey_addon.node` 的系统 Node 24 与 Electron 32（内置 Node 20）ABI 不兼容，Electron 的 `require()` 拒绝加载 `.node` 文件。`loadHotkeyAddon()` 的 try/catch 无声捕获该异常 → `hotkeyAddon = null` → 全局钩子从未安装 → RAlt 无效。
2. **启动错误弹窗**：`frontend/main.js` 中 `backendProcess.spawn()` 缺少 `error` 事件处理器。当 Python 进程启动失败（如 PATH 不一致、依赖缺失）时，`error` 事件成为未捕获错误，Electron 弹崩溃对话框退出。

### 修复方案
将 WH_KEYBOARD_LL 钩子从 N-API addon 迁移到独立 DLL（Typeless 架构：DLL + ctypes），与 `sayit_context_helper_dll.dll` 在同一 CMake 项目中编译。

### 变更
| 文件 | 操作 |
|------|------|
| `native/context_helper/src/keyboard_helper.cpp` | **新建** — WH_KEYBOARD_LL 钩子 DLL，导出 install_hook / uninstall_hook / is_hook_installed，无 N-API 依赖，仅 `windows.h` + `ctypes` |
| `native/context_helper/CMakeLists.txt` | 新增 `sayit_keyboard_helper` SHARED 目标 |
| `infrastructure/keyboard_helper_dll.py` | **新建** — ctypes 加载器，与 `context_helper_dll.py` 同模式 |
| `application/orchestrator.py` | 集成 `KeyboardHelperDll`; `start()` 时自动安装钩子, `stop()` 时卸载; 新增 `_install_keyboard_hook` / `_uninstall_keyboard_hook` |
| `server.py` | orchestrator 初始化加 try/except 保护; 热键 API 端点保持 no-op（钩子在 Python 端） |
| `frontend/main.js` | 删除 `loadHotkeyAddon()` / `startHotkeyAddon()` / `hotkeyAddon` 全局变量; 新增 `backendProcess.on('error')` 处理器; WS open 不再 install addon |

### 数据流
```
RAlt ↓ → keyboard_helper.dll HookProc → Python callback → orchestrator.toggle_recording()
```

### DLL 编译
- 零警告，148KB，导出 3 个函数
- 测试验证：install → 确认 installed; 二次 install 被拒绝; uninstall → 确认 removed

## 2026-06-24 — Typeless 架构重构（RAlt 无限触发修复）

### 根因
Python `server.py` 中的 `WH_KEYBOARD_LL` 钩子（`hotkey.py`）与 Electron 主进程的 `spawn` 之间存在双重 Hook 竞争：
Electron 启动 Python → 安装钩子 → 当第二个 Python 实例因 port-busy 退出前，钩链已被污染 → RAlt 只触发一次就死。

### 修复方案
将唯一的 `WH_KEYBOARD_LL` 钩子从 Python 迁移到 Electron 的 C++ N-API addon，
Python 后端不再参与键盘事件处理。

### 变更
| 文件 | 操作 |
|------|------|
| `native/hotkey-addon/` | **新建** — C++ addon: binding.gyp + main.cpp (N-API ThreadSafeFunction) |
| `native/hotkey-addon/build/Release/hotkey_addon.node` | 148KB, 0 错误 |
| `frontend/main.js` | 加载 addon, WS 双向化, RAlt → ws.send(toggle_recording) |
| `application/orchestrator.py` | 移除 HotkeyManager, 保留 start/stop_recording, 新增 toggle_recording |
| `server.py` | WS 从 asyncio.sleep(30) → receive_text() 分派命令 |
| `infrastructure/hotkey.py` | **删除** |
| `start.bat` / `launch_sayit.bat` / `_clean_restart.ps1` | 改为只启动 Electron（后端由 Electron 管理） |
| `frontend/package.json` | build 脚本 + extraResources 加入 hotkey_addon.node |
| `README.md` | 启动说明简化 |

### 数据流
```
RAlt ↓ → C++ HookProc → ThreadSafeFunction → Node.js → ws.send(toggle_recording) → Python WS → orchestrator.toggle_recording()
```

## 2026-06-13 — 注入乱码修复 + 火山 AI Key + 诊断基础设施

### 注入乱码 fevhlbigktcps（根因 + 修复）
**现象**：记事本中注入的文本顶部每次出现固定 13 个随机字母 `fevhlbigktcps`，无论注入什么内容。
**根因**：`_release_modifiers()` 无条件发送 11 个 modifier keyup（Alt/Win/Ctrl/Shift），即使这些键从未按下。
在部分 Windows 版本/IME 配置下，对未按下的键发 `KEYEVENTF_KEYUP` 会被系统误处理为按键，产生固定字母序列。
**修法**：`injector.py` `_release_modifiers()` 加 `GetAsyncKeyState(vk) & 0x8000` 守卫 — 只释放真正被按下的修饰键。
**验证**：`paste_only`(跳过 preamble)→干净；完整 `inject` 3 次→全部干净。

### 火山 AI Key Fallback Bug（Patch 2-3）
- `ai_providers.py:92`：Volcengine 无显式 key 时，fallback 误读 `asr.access_token`→ 改为 `ai.api_key`
- `server.py:292`：`_sync_provider_keys` 同步 key 时同 bug → 改为读取 `volcengine.ai.api_key`

### 诊断基础设施
- `[PORT-BUSY]` 启动守卫：17890 被占时打印占用者 PID 并退出，不再静默 bind 失败
- 日志落地：`%APPDATA%/Sayit/sayit.log`（FileHandler），所有 `[WAV-CHECK]/[AI-KEY]/[AUDIO-DEVICE]/[INJECT-PATH]/[VOLC-ASR-EP]` tag 可 grep
- 4 个调试端点：
  - `POST /api/debug/inject` — 注入隔离测试（可选 `paste_only` 跳过 preamble）
  - `POST /api/debug/pipeline-text` — 文本→corrector→injector 全链
  - `POST /api/debug/release-only` — `_release_modifiers` 单独测试
  - `GET /api/debug/wav-check` — 最近 WAV 文件信息

### 采样率链路排查
- 全链 16000 一致（音频捕获→WAV 头→ASR 引擎），设备 48000→16000 重采样无质量问题
- 删除 `config_store.py` 死配置 `sample_rate: 16000`（无任何组件读取）
- WAV 桌面副本 `sayit_last.wav` 供听感验证

### 诊断日志 tag 一览
| Tag | 文件 | 触发时机 |
|-----|------|---------|
| `[WAV-CHECK]` | asr.py | WAV 文件写入时 |
| `[AI-KEY]` | ai_providers.py | AI provider 构建时 |
| `[AUDIO-DEVICE]` | audio_capture.py | 录音启动时 |
| `[INJECT-PATH]` | injector.py | 注入路径选择/按键合成 |
| `[VOLC-ASR-EP]` | asr.py, asr_v3.py | 火山 ASR 发起请求前 |

### 改动文件
| 文件 | 变更 |
|------|------|
| `infrastructure/injector.py` | fix: `_release_modifiers` GetAsyncKeyState 守卫; diag: [INJECT-PATH] 入口/路由/按键合成; UIA TextPattern fallback pyperclip.copy |
| `infrastructure/ai_providers.py` | fix: Volcengine AI key fallback; diag: [AI-KEY] + [AI-KEY-legacy] |
| `server.py` | fix: `_sync_provider_keys`; feat: [PORT-BUSY] 守卫; feat: FileHandler 日志落地; feat: 4 个 /api/debug 端点 |
| `infrastructure/asr.py` | diag: [WAV-CHECK] + 桌面 WAV copy; diag: [VOLC-ASR-EP] v1; import urlparse |
| `infrastructure/asr_v3.py` | diag: [VOLC-ASR-EP] v3; import urlparse |
| `infrastructure/audio_capture.py` | diag: [AUDIO-DEVICE] 设备原生采样率 |
| `infrastructure/config_store.py` | chore: 删除死配置 sample_rate |

## 2026-06-10 — Hotkey RAlt Toggle Fix

### 问题
右 Alt 按下后菜单栏激活（Notion）、记事本冒字符。预期：右 Alt 作为全局 toggle 键，不应透传到 OS。

### 根因链 (5 层)
1. **pynput 不 suppress**：`win32_event_filter` 返回 `False` 只跳过 `on_press`/`on_release`，不抛 `SuppressException` → Windows 钩子回调不 `return 1` → 事件透传 OS
2. **换原生 ctypes**：用 `SetWindowsHookEx(WH_KEYBOARD_LL)` 替代 pynput，`_hook_proc` 返回 `1` 真正拦截
3. **钩子线程错位**（最隐蔽）：`SetWindowsHookEx` 在主线程调，`GetMessage` 泵在后台线程跑 → 回调派发到主线程但主线程无消息泵 → 钩子永不触发。修复：安装 + 泵合并到同一条 `_hook_thread`
4. **状态机 s 变量不同步**：`IDLE_DEBOUNCE` 中改了 `self._state` 但局部变量 `s` 未更新 → 后续 `if s == 'IDLE'` 永远 False。修复：去掉 `IDLE_DEBOUNCE`，用 `_last_toggle_ts` 时间戳防抖
5. **vkE8 mask key**（保底）：Mode B 首次检测到右 Alt 按下时注入 `vkE8` 虚拟键，抢在 Windows 发 `SC_KEYMENU` 之前

### 改动文件
| 文件 | 变更 |
|------|------|
| `infrastructure/hotkey.py` | 完全重写：原生 ctypes `WH_KEYBOARD_LL`、`_active` 标志、三形态状态机、L/R 分辨、AltGr 过滤、`pause()`/`resume()`、vkE8 mask key |
| `infrastructure/config_store.py` | 默认 `hotkey`: `"Ctrl+Shift+Space"` → `"RAlt"` |
| `server.py` | 新增 4 个 REST 端点：`/api/hotkey/pause`, `/api/hotkey/resume`, `/api/hotkey/set`, `/api/config-value` |
| `frontend/preload.js` | 新增 `pauseHotkey`, `resumeHotkey`, `setHotkey`, `getConfigValue` |
| `frontend/ui/recorder.html` | v3 快捷键录制 popup：location-aware 键名、纯修饰单键支持、keyup 确认 |
| `main.py` | 标注 DEPRECATED |

### 架构决策
- **退役 pywebview**：`main.py` + 根 `ui/` 标记废弃，统一 Electron 入口 (`server.py` + `frontend/`)
- **原生 ctypes 替代 pynput**：pynput 的 `win32_event_filter` 不等价于 OS 级 suppress

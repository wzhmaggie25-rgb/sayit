# Project State
> 最后一次更新：2026-06-26 14:00

## Overview

- **Project:** SayIt — 桌面语音输入工具（静默语音识别 + AI 转录 + 自学习纠错）
- **Stack:**
  - **UI:** Electron (Chromium) — vanilla HTML/CSS/JS（除 float.html 加载 React 18 UMD 用于悬浮波形动画）
  - **Backend:** Python FastAPI + uvicorn
  - **Audio capture:** PyAudio (blocking mode), 16kHz 16-bit mono
  - **Hotkey:** WH_KEYBOARD_LL 全局钩子 → C++ DLL (`sayit_keyboard_helper.dll`) → Python ctypes
  - **ASR:** DashScope (Aliyun) streaming → 火山引擎 → ONNX SenseVoice（三级级联）
  - **AI Correction:** OpenAI 兼容协议（通义千问 / 豆包 / DeepSeek / OpenAI 多 Provider）
  - **Injection:** UIA ValuePattern → Clipboard → SendInput（四级瀑布）
  - **Context helper:** C++ DLL (`sayit_context_helper_dll.dll`, in-process UIA) + legacy EXE (JSON-RPC over stdio)
  - **Storage:** SQLite

- **Current branch:** feature/silent-learning-stabilization
- **Base branch (stable):** backup/local-working-2026-06-25

## Architecture

### 各层的职责

| Layer | Component | 职责 |
|-------|-----------|------|
| **Electron** | `frontend/main.js` | 窗口管理、IPC bridge、WebSocket 客户端、spawn Python 后端进程 |
| **Electron** | `frontend/preload.js` | contextBridge 暴露 `window.sayit` API（getConfig / startRecording / onBackendEvent 等） |
| **Electron** | `frontend/ui/` | 纯 HTML + 内联 JS（recorder / dictionary / history / settings / float） |
| **Python** | `server.py` (FastAPI) | REST + WebSocket 入口，事件广播，config hot-reload |
| **Python** | `application/orchestrator.py` | 中心编排器：热键生命周期、pipeline 创建、pipeline 互斥锁 |
| **Python** | `application/pipeline.py` | 状态机（IDLE→CAPTURING→TRANSCRIBING→CORRECTING→INJECTING→DONE） |
| **Python** | `infrastructure/audio_capture.py` | PyAudio 阻塞模式录音 |
| **Python** | `infrastructure/asr.py`, `asr_v3.py`, `asr_streaming.py` | ASR 引擎级联 |
| **Python** | `infrastructure/corrector.py`, `ai_providers.py` | AI 纠错 |
| **Python** | `infrastructure/injector.py`, `injector_uia.py` | 文本注入（4 级瀑布） |
| **Python** | `infrastructure/silent_monitor.py` | 静默学习——注入后跟踪用户编辑，提取纠错规则 |
| **Python** | `infrastructure/keyboard_helper_dll.py` | ctypes 加载 `sayit_keyboard_helper.dll` |
| **Python** | `infrastructure/context_helper_dll.py` | ctypes 加载 `sayit_context_helper_dll.dll` |
| **Python** | `infrastructure/context_helper_client.py` | legacy EXE subprocess (JSON-RPC over stdio) |
| **Python** | `infrastructure/focus_context.py` | 焦点输入框上下文结构 + UIA 快照 |
| **C++ DLL** | `sayit_keyboard_helper.dll` | WH_KEYBOARD_LL 全局钩子，检测 RAlt |
| **C++ DLL** | `sayit_context_helper_dll.dll` | 进程内 UIAutomation 访问（get_full_context_json 等） |
| **C++ EXE** | `sayit_context_helper.exe` | 遗留子进程式 UIA 访问（JSON-RPC over stdin/stdout） |

### 右 Alt 调用链

```
RAlt 按下
  → WH_KEYBOARD_LL HookProc (keyboard_helper.cpp)
  → C++ 回调 → Python ctypes CFUNCTYPE
  → KeyboardHelperDll._dispatch()
  → spawn daemon thread "hotkey-dispatch" (< 0.1ms 返回钩子线程)
  → orchestrator.toggle_recording()
  → orchestrator._on_hotkey_start()
    → UIPI 检查（admin 窗口警告）
    → pipeline_lock 互斥（P0：拒绝并发 pipeline）
    → injector.capture_target() 捕获目标窗口
    → RecordingPipeline.run() 在新 pipeline 线程启动
```

### 录音 → 识别 → 文本处理 → 注入 → 静默学习 调用链

```
RAlt press → pipeline.run()
  ├── Phase 1: CAPTURING
  │     → AudioCapture.start() (PyAudio blocking read 线程)
  │     → Streaming ASR session (aliyun_streaming) 启动
  │     → audio_capture.set_chunk_callback(session.enqueue_audio)
  │     → RMS 回调 → EventBus → WebSocket → 悬浮窗波形
  │
  RAlt release → pipeline.stop() → _stop_flag = true
  │     → audio_capture.stop() → 返回 PCM bytes
  │
  ├── Phase 2: TRANSCRIBING
  │     → streaming_session.finish() (streaming 结果)
  │     ├─ 质量门：如 streaming 输出太短则 fallback
  │     └─ asr_cascade.transcribe(pcm) (batch 级联: 阿里云 → 火山 → ONNX)
  │     → hotwords_mgr.apply_layer2_correction()
  │     → domain.correction.apply_rules_with_stats() (静默学习历史规则)
  │
  ├── Phase 3: CORRECTING
  │     → corrector.process() (AI LLM 纠错，多 Provider 轮询)
  │     → 去除结尾句号（config remove_trailing_period）
  │
  ├── Phase 4: INJECTING
  │     → injector.inject() — 4 级瀑布：
  │        UIA ValuePattern → UIA TextPattern → Clipboard → SendInput
  │     → EventBus INJECTION_DONE
  │
  ├── Phase 5: Save to history
  │     → db.add_history(raw, refined, final, app, duration, ...)
  │
  └── Phase 6: SILENT LEARNING (如 config.silent_learning == true)
        → silent_monitor.start(history_id, final_text, hwnd, pid, hotwords_mgr)
        → daemon thread "silent-monitor-{hash}" 启动
        → _start_track(): 1.2s 内轮询 UIA 确认注入文本存在
        → 循环 15s，每 0.3s poll 键盘事件 + 取焦点上下文
        → 检测到用户编辑（内容变化 + 非大修改 + 锚点可对齐）
        → learn_from_edit() → db.merge_rules()
        → _auto_add_dictionary_terms() → hotwords_mgr.add_word()
        → EventBus SILENT_LEARNED → WebSocket → UI
```

### 静默学习的完整调用链

```
RecordingPipeline.run() Phase 6
  → SilentMonitor.start(hid, text, hwnd, pid, hotwords_mgr)
    → 创建 daemon 线程 silent-monitor-{hid}
    → _monitor_loop():
      1. _start_track() — 1.2s 超时内确认注入文本存在于输入框
         → 取焦点上下文（ContextHelperDll / ContextHelperClient）
         → 验证 editable + contains text + hwnd 匹配
         → 记录 track_context（基准快照）
      2. 循环 15s，每 0.3s:
         → _poll_keyboard_events()
           → ContextHelperClient().poll_keyboard_events() (首选)
           → fallback: GetAsyncKeyState(Enter)
         → _get_current_context()
         → 检查 hwnd/input_box 未切换
         → 检查 full_field_content 是否还包含注入文本
         → 不再包含 → 用户已编辑 → 触发 _check_edited_text()
      3. _check_edited_text():
         → 比较当前文本 vs 基准文本
         → extract_inserted_region() 定位编辑范围
         → analyze_modification() 检查是否大修改 (>50%)
         → _learn() — 核心学习:
           → learn_from_edit(original, edited, existing_rules)
           → db.merge_rules(merged)
           → _auto_add_dictionary_terms()
           → _on_learned callback → EventBus SILENT_LEARNED
```

### Context Helper 实际加载方式

两种加载路径，按优先级：

1. **`ContextHelperDll`**（新，进程内 UIA）— `infrastructure/context_helper_dll.py`
   - `ctypes.CDLL` 加载 `sayit_context_helper_dll.dll`
   - 导出函数：`get_full_context_json`, `get_focused_context_json`, `poll_keyboard_events_json`, `free_string`
   - 搜索路径：`native/context_helper/build/Release/` → `Debug/` → `build/` → `bin/`
   - `get_focused_input_info()` 被 `focus_context.py` 中的 `get_focus_context()` 使用

2. **`ContextHelperClient`**（旧，subprocess）— `infrastructure/context_helper_client.py`
   - `subprocess.Popen` 启动 `sayit_context_helper.exe`
   - JSON-RPC over stdin/stdout（每请求一个 JSON line）
   - 搜索路径同上 + `SAYIT_CONTEXT_HELPER` 环境变量覆盖
   - `poll_keyboard_events()` 被 `SilentMonitor._poll_keyboard_events()` 使用
   - 被 `focus_context.py` 用做 `get_focus_context()` 的回退

**调用方使用链:**
- `focus_context.get_focus_context()` → 优先试 `ContextHelperDll.get_focused_input_info()` → 失败时回退 `ContextHelperClient.get_full_context()`
- `silent_monitor.SilentMonitor._poll_keyboard_events()` → 直接调用 `ContextHelperClient().poll_keyboard_events()`

## Branches

| Branch | Purpose | 保护规则 |
|--------|---------|----------|
| `main` | 发布分支 | 仅 PR 合并，禁止直接推送 |
| `backup/local-working-2026-06-25` | 稳定备份 | **禁止直接修改**，仅作为基线 |
| `feature/silent-learning-stabilization` | 当前开发分支 | 自由开发 |

## 已知问题

1. **PortAudio + UIA DLL 初始化冲突**：`STATUS_DLL_INIT_FAILED (0xC0000142)` — PortAudio 初始化后，在新线程加载 `UIAutomationCore.dll` 可能触发进程崩溃。`audio_capture.py` 中 `was_portaudio_used()` 守卫标记此风险，`focus_context.py` 对其有检查。
2. **Hook 线程阻塞 → Windows 静默解钩**：`keyboard_helper.cpp` 的 HookProc 如果同步调用 Python 超过 `LowLevelHooksTimeout`(~300ms)，Windows 静默卸载钩子（**已修复**：`keyboard_helper_dll.py` 增加 `_dispatch()` 包装层，hook 线程仅 0.1ms spawn 后返回）。
3. **UIA COM 接口类型错误**：`injector.py` `CreateObject(clsid)` 返回 `POINTER(IUnknown)` 无 `GetFocusedElement` 方法（**已修复**：优先类型库加载 `IUIAutomation` + `finally` CoUninitialize）。
4. **词库页缺少事件驱动刷新**：dictionary.html 在 `pipeline_done` 后不自动重新加载（**已修复**）。
5. **双重 Hook 竞争**：旧架构中 Electron + Python 各装一个 WH_KEYBOARD_LL（**已修复**：Typeless 架构将唯一钩子移到 Python 端 ctypes DLL）。
6. **N-API addon 不兼容 Electron 32**：`hotkey_addon.node` 的 Node ABI 与 Electron 内置 Node 不兼容（**已修复**：迁移到 Typeless DLL + ctypes）。
7. **注入乱码 `fevhlbigktcps`**：`_release_modifiers()` 对未按下的键发送 KEYUP（**已修复**：加 `GetAsyncKeyState` 守卫）。

## 不允许随意修改的模块

- **热键**：`infrastructure/keyboard_helper_dll.py`、`native/context_helper/src/keyboard_helper.cpp`
- **录音**：`infrastructure/audio_capture.py`
- **注入**：`infrastructure/injector.py`、`infrastructure/injector_uia.py`
- **进程管理**：`application/orchestrator.py`（`_pipeline_lock` 互斥逻辑）、`frontend/main.js`（Electron 生命周期）
- **静默学习**：`infrastructure/silent_monitor.py`

修改上述模块需额外审查跨线程/COM 副作用。

## 最近重要提交

- `0d69a98` — `backup: working local version after hotkey and lifecycle fixes`
  - 稳定备份点，包含：第二次 Alt 失灵修复、UIA COM 修复、词库事件刷新、CoInitialize/CoUninitialize 保护

- `d7ac403` — `chore: add AI handoff workflow`
  - 新建 AI 交接机制：AGENTS.md + .ai/ 目录（PROJECT_STATE / CURRENT_TASK / ZCODE_REPORT / TEST_RESULTS）

## Configuration & Secrets

- `.env` / `.env.*` — 不上传
- `config.json` — 不上传
- `*.db` / `*.sqlite` / `*.sqlite3` — 不上传
- `*.wav` / `*.mp3` / `*.pcm` / `*.flac` / `*.ogg` / `*.aac` / `*.m4a` / `*.webm` — 不上传
- `*.log` — 不上传
- API keys, tokens — 不上传
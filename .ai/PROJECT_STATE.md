# Project State
> 最后一次更新：2026-06-26 14:45

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
        → 检测到用户编辑 → learn_from_edit() → db.merge_rules()
```

### 静默学习的完整调用链

```
RecordingPipeline.run() Phase 6
  → SilentMonitor.start(hid, text, hwnd, pid, hotwords_mgr)
    → 创建 daemon 线程 silent-monitor-{hid}
    → _monitor_loop():
      1. _start_track() — 1.2s 超时内确认注入文本存在于输入框
         → _get_current_context() 实际调用链：
           [有 hwnd] → get_focus_context_for_window(hwnd, text)
             Path 1: Win32 child-edit (SendMessage WM_GETTEXT) — 最快
             Path 2: ContextHelperClient EXE subprocess (get_full_context_for_window)
             Path 3: ContextHelperDll DLL (如果 PortAudio 未使用)
             Path 4: Win32 上下文（最后手段）
           [无 hwnd] → get_focus_context(text)
             Path 1: ContextHelperClient EXE subprocess (get_full_context)
             Path 2: ContextHelperDll DLL (如果 PortAudio 未使用)
             Path 3: Python UIA + Win32 纯 Python 降级
         → 验证 editable + contains text + hwnd 匹配
         → 记录 track_context（基准快照）
      2. 循环 15s，每 0.3s:
         → _poll_keyboard_events()
           Path 1: ContextHelperClient().poll_keyboard_events() (EXE subprocess)
           Path 2: ctypes.windll.user32.GetAsyncKeyState(Enter) 降级
           → 注意：**永远不走 ContextHelperDll.poll_keyboard_events()**
         → _get_current_context()
         → 内容变化 → _check_edited_text()
      3. _check_edited_text() → _learn() → db.merge_rules()
```

## Context Helper 实际加载方式（审计确认）

### 两种路径的文件存在性（2026-06-26 确认）

| 组件 | 路径 | 存在 |
|------|------|------|
| `sayit_context_helper_dll.dll` | `native/context_helper/build/Release/sayit_context_helper_dll.dll` | ✅ 70,656 bytes |
| `sayit_context_helper.exe` | `native/context_helper/build/Release/sayit_context_helper.exe` | ✅ 存在 |
| `sayit_keyboard_helper.dll` | `native/context_helper/build/Release/sayit_keyboard_helper.dll` | ✅ 148KB, ABI v3, build `2026-06-26-v3` |

### 运行时加载优先级（focus_context.py）

**`get_focus_context()`（无指定 hwnd）：**
1. **ContextHelperClient EXE subprocess**（首选）— 通过 JSON-RPC over stdin/stdout
2. **ContextHelperDll 进程内 DLL**（降级）— 仅当 `was_portaudio_used() == False` 时尝试
3. **Python UIA + Win32**（最后手段）— 使用 comtypes + ctypes

**`get_focus_context_for_window(hwnd)`：**
1. **Win32 child-edit**（最快）— `SendMessage(WM_GETTEXT)` 直接读取子窗口
2. **ContextHelperClient EXE subprocess** — 调用 `get_full_context_for_window`
3. **ContextHelperDll 进程内 DLL** — 仅当 `was_portaudio_used() == False` 时尝试
4. **Win32 上下文**（最后手段）

### DLL 实际运行状态（审计发现）

- **DLL 加载成功**（`ctypes.CDLL` 返回有效句柄）
- **DLL 函数调用崩溃**（exit 127 / STATUS_DLL_INIT_FAILED）
  - 根因：Python comtypes 先将 COM 公寓模型设为 MTA（`CoInitializeEx(None, 2)`）
  - DLL 内部的 `ComInit` 尝试 `CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED)`（STA）
  - STA 初始化失败 → `CoCreateInstance(CLSID_CUIAutomation)` 崩溃
  - **结论：在 server.py 运行时 DLL 永远不可用**
- **EXE subprocess 稳定工作**（独立进程，有自己的 COM 公寓，不受主进程影响）
- **KeyboardHelperDll 正常工作**（仅使用 `WH_KEYBOARD_LL`，不涉及 UIA）

### SilentMonitor 键盘轮询路径

- **`_poll_keyboard_events()` 只用 `ContextHelperClient`（EXE subprocess）**
- 无需回退到 `ContextHelperDll`
- 降级路径：`GetAsyncKeyState(Enter)` — 仅检测 Enter 键
- **这个路径设计是合理的**：EXE 独立进程，不受 COM 公寓约束

## Branches

| Branch | Purpose | 保护规则 |
|--------|---------|----------|
| `main` | 发布分支 | 仅 PR 合并，禁止直接推送 |
| `backup/local-working-2026-06-25` | 稳定备份 | **禁止直接修改**，仅作为基线 |
| `feature/silent-learning-stabilization` | 当前开发分支 | 自由开发 |

## 已知问题

### 已确认（审计验证）

1. **DLL 的 UIA 函数因 COM 公寓模型不一致而崩溃**（STATUS_DLL_INIT_FAILED）— server.py 中 comtypes 设置 MTA，DLL 尝试 STA。`focus_context.py` 的 `was_portaudio_used()` 守卫只能部分缓解（PortAudio 也会设 MTA），但即使无 PortAudio，comtypes 导入后 COM 已初始化。**DLL 路径在 server.py 上下文中实质无效。**

2. **Python UIA 降级路径（Path 3）在无焦点可编辑文本框时返回空** — `read_focus_text()` 调用 `CoCreateInstance` 创建 `CUIAutomation` 对象，但 `GetFocusedElement()` 在 VS Code / ZCode 等非标准编辑器中可能返回 None。`_get_focus_context_python()` 对 editable 的判断依赖 `focused_element_snapshot.editable` 的值，该值在无 UIA 焦点元素时为 None → `is_editable=False`。

### 已修复（CHANGELOG 记录）

3. **Hook 线程阻塞 → Windows 静默解钩** — 修复：`_dispatch()` 线程分发
4. **UIA COM 接口类型错误** — 修复：类型库加载 + CoUninitialize
5. **词库页缺少事件驱动刷新** — 修复：onBackendEvent 监听
6. **双重 Hook 竞争** — 修复：Typeless 架构迁移
7. **N-API addon 不兼容 Electron 32** — 修复：迁移到 Typeless DLL
8. **注入乱码 fevhlbigktcps** — 修复：GetAsyncKeyState 守卫
9. **Per-toggle daemon thread 乱序风险** — 修复（2026-06-26）：keyboard_helper_dll.py 改单一 `hotkey-consumer` 线程串行 drain queue，不再每个 toggle spawn 新线程；64 槽诊断 ring + `helper_version=2` / `helper_build_id="2026-06-26-v2"` 在启动日志和 `/api/diagnostics/hotkey` 暴露
10. **静默学习把整句/错误内容自动加入个人词典** — 修复（2026-06-26）：`extract_dictionary_terms` 严格门禁，仅允许单一 1↔1 token replacement、同字符族、形态/长度受控、最多 1 个候选；纠错规则学习独立未受影响
11. **第二次 RAlt stop ACK 不可见** — 修复（2026-06-26）：`Events.RECORDING_STOPPING` 在 `pipeline.stop()` 之前同步发出
12. **第二次 RAlt 真实物理失灵 fallback** — 修复（2026-06-26 Round 4）：新增 `RAltStopWatcher` 使用 `GetAsyncKeyState(VK_RMENU)` 10ms 轮询作为 WH_KEYBOARD_LL 钩子丢失的兜底；orchestrator arm-on-start/disarm-on-stop 集成；`_fallback_stop()` 幂等检查 `_stop_flag`；Phase 1 wait-release + Phase 2 detect-cycle + hook emit count 去重
13. **AudioCapture 停止延迟** — 修复（2026-06-26 Round 4）：`stop()` 先 close stream（`stream.stop_stream()+stream.close()`）解除 blocking read，再 join thread，避免 3s 阻塞等待
14. **前端 stop ACK 消费** — 修复（2026-06-26 Round 4）：`frontend/main.js` 转发 `recording_stopping` WS 事件 → `float.html` 立即显示 RECORD.STOP（无提示音）
15. **中文局部纠错无法学习** — 修复（2026-06-26 Round 4）：`_extract_chinese_local_replacement(original, edited)` 字符级 SequenceMatcher diff，single replace opcode，≤6 字 CJK，≥2 anchor；`merge_rules` 按 `(pattern, replacement)` 对匹配；ABI v3
16. **Clipboard 注入假成功** — 修复（2026-06-26 Round 4）：`paste()` 在 Ctrl+V 后读剪贴板验证文本是否被消费；未消费时返回 `InjectionResult(ok=False, reason='text_not_consumed', clipboard_preserved=True)`
17. **注入返回无结构** — 修复（2026-06-26 Round 4）：`InjectionResult` dataclass（ok/verified/method/reason/clipboard_preserved/target_restored + `__bool__` 向后兼容），`inject()` 返回 `List[InjectionResult]`

## 不允许随意修改的模块

- **热键**：`infrastructure/keyboard_helper_dll.py`、`native/context_helper/src/keyboard_helper.cpp`
- **录音**：`infrastructure/audio_capture.py`
- **注入**：`infrastructure/injector.py`、`infrastructure/injector_uia.py`
- **进程管理**：`application/orchestrator.py`（`_pipeline_lock` 互斥逻辑）、`frontend/main.js`（Electron 生命周期）
- **静默学习**：`infrastructure/silent_monitor.py`

修改上述模块需额外审查跨线程/COM 副作用。

## 最近重要提交

- `1077cb7` — `docs: populate SayIt project handoff context`
- `d7ac403` — `chore: add AI handoff workflow`
  - 新建 AI 交接机制：AGENTS.md + .ai/ 目录
- `0d69a98` — `backup: working local version after hotkey and lifecycle fixes`
  - 稳定备份点：第二次 Alt 失灵修复、UIA COM 修复、词库事件刷新、CoInitialize/CoUninitialize 保护

## Configuration & Secrets

- `.env` / `.env.*` — 不上传
- `config.json` — 不上传
- `*.db` / `*.sqlite` / `*.sqlite3` — 不上传
- `*.wav` / `*.mp3` / `*.pcm` — 不上传
- `*.log` — 不上传
- API keys, tokens — 不上传
# Changelog

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

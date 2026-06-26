# ZCode Report
> 最后一次更新：2026-06-26 14:54

## 接收到的任务（第三轮）

读取 `.ai/CURRENT_TASK.md` 中的 READY 任务——搭建 SayIt 本地 AI 任务桥梁第一版
（`tools/agent_bridge/`），每 30 秒轮询 GitHub，调用 Claude Code 非交互执行。

### 范围
- 新建桥梁代码、配置模板、启动脚本、设计文档
- 新建测试文件（单元测试 + 冒烟脚本）
- 更新 `.gitignore` 排除运行时文件
- **不修改任何 SayIt 业务代码**

### 创建的文件

| 文件 | 说明 |
|------|------|
| `tools/agent_bridge/bridge.py` | 核心桥梁（~500 行） |
| `tools/agent_bridge/bridge_config.example.json` | 配置模板 |
| `tools/agent_bridge/README.md` | 用户文档 |
| `start_bridge.bat` | 启动脚本 |
| `.ai/BRIDGE_DESIGN.md` | 设计文档 |
| `tests/test_agent_bridge.py` | 29 个单元测试 |
| `tests/smoke_agent_bridge.py` | Claude 冒烟测试 |

### 修改的文件

| 文件 | 变更 |
|------|------|
| `.gitignore` | 新增桥梁运行时文件排除规则 |
| `.ai/CURRENT_TASK.md` | 状态改为 DONE |
| `.ai/ZCODE_REPORT.md` | 新增本轮记录 |
| `.ai/TEST_RESULTS.md` | 新增桥梁测试结果 |

### 桥梁核心行为

1. 每 30 秒 `git fetch origin feature/silent-learning-stabilization`
2. 安全检查：分支正确、工作目录干净、无进行中操作、可 ff-only、CURRENT_TASK 为 READY、未重复执行、无并发锁
3. 通过后调用 `claude -p <prompt> --output-format json` (timeout=300s)
4. Claude 执行任务、更新 .ai 报告、提交推送
5. 更新状态文件、释放锁

### 执行过的命令

```bash
# 单元测试
python -m pytest tests/test_agent_bridge.py -v    # 29/29 通过

# 注意：冒烟测试（真实 Claude）尚未执行
```

执行 `.ai/CURRENT_TASK.md` 中的"只读审计静默学习"任务。

重点审计：
1. 静默学习的实际运行时路径（DLL vs EXE）
2. PortAudio 已使用后的降级行为
3. 运行全部已有测试 + 记事本受控测试
4. 确认最早失败断点
5. 不修改任何业务代码

## 实际修改的文件

- `.ai/PROJECT_STATE.md` — 更新：添加审计验证的真实调用链、DLL 运行时状态（崩溃确认）、ContextHelper 双路径存在性确认
- `.ai/CURRENT_TASK.md` — 标记完成状态、最早失败断点、最小修复建议
- `.ai/ZCODE_REPORT.md` — 本报告
- `.ai/TEST_RESULTS.md` — 详细记录所有测试结果

## 根因判断

### DLL 崩溃根因
`sayit_context_helper_dll.dll` 的 `inputJsonForWindow()` 函数中有 `ComInit` 类，其对 COM 调用 `CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED)`（STA）。

而 Python 端的 `comtypes` 库在首次导入时已调用 `CoInitializeEx(None, 2)`（COINIT_MULTITHREADED / MTA）。
Windows COM 不允许在同一线程上混合公寓模型，第二次 CoInitializeEx 返回 `RPC_E_CHANGED_MODE`。
后续 `CoCreateInstance(CLSID_CUIAutomation)` 因此失败，导致 `UIAutomationCore.dll` 加载时 `DllMain` 返回 FALSE
→ 进程退出（exit 127 / STATUS_DLL_INIT_FAILED）。

### SilentMonitor._poll_keyboard_events() 仅使用 EXE
设计决策：`silent_monitor.py:324` 只调用 `ContextHelperClient().poll_keyboard_events()`，不走 `ContextHelperDll`。这意味着键盘事件轮询完全依赖 EXE 子进程。

### Python UIA 降级路径脆弱
`_get_focus_context_python()` 依赖 `comtypes` 创建 `CUIAutomation` 对象。在 VS Code / ZCode 等非标准编辑器中，
`GetFocusedElement()` 可能返回 None，导致 `is_editable=False`，`_start_track()` 无法绑定。

## 实施内容（第二轮：ZCode 自动化能力评估）

### 探查范围
- `zcode` CLI 在 PATH 上：不存在
- `ZCode.exe --help / --version`：无 CLI 接口（Electron 应用），版本 3.1.7
- ZCode 作为 MCP 服务端：否（仅客户端）
- `zcode://` URI scheme：已注册，指向 `ZCode.exe "%1"`
- `codex://` URI scheme：已注册，无 open command
- 本机代码代理候选：`claude`（2.1.185，支持 `-p` 非交互模式）、`cursor`（3.8.11，仅 IDE 启动器）
- 不可用：`aider`、`gh`、`ollama`、`gemini`、`continue`、`codex`

### 创建的文件
- `.ai/ZCODE_AUTOMATION_CAPABILITY.md` — 完整评估报告

### 更新的文件
- `.ai/ZCODE_REPORT.md` — 新增本轮内容
- `.ai/TEST_RESULTS.md` — 新增环境能力扫描记录

## 实施内容（第一轮：静默学习审计）

### 代码阅读
- 读取 `silent_monitor.py`（379 行全读）
- 读取 `focus_context.py`（724 行全读）
- 读取 `context_helper_dll.py`（167 行全读）
- 读取 `context_helper_client.py`（177 行全读）
- 读取 `pipeline.py`（320 行全读）
- 读取 `orchestrator.py`（312 行全读）
- 读取 `injector_uia.py`（前 90 行）
- 读取 `domain/correction.py`（314 行全读）
- 读取 `audio_capture.py`（前 60 行）
- 读取 `paths.py`（全读 → 发现 PROJECT_ROOT bug）
- 读取 `keyboard_helper_dll.py`（关键部分）
- 读取 `native/context_helper/src/main.cpp`（DLL 的 ComInit 和 UIA 函数）
- 读取全部测试文件

### 测试执行
- 单元测试：5 个文件，13 个用例全部通过
- 记事本冒烟测试：通过（生成规则 wrld→world）
- DLL 加载/崩溃验证：3 次独立测试确认
- EXE 通信验证：成功返回实时焦点上下文
- EXE 自动重启验证：关闭后自动重建子进程
- PortAudio 守卫验证：`was_portaudio_used()` 为 True 时跳过 DLL

### 运行时验证
- 确认 DLL 在 server.py 上下文加载成功但函数调用崩溃（exit 127）
- 确认 EXE 子进程可稳定工作并返回 ZCode 的焦点上下文
- 确认 Python UIA 降级路径在当前环境返回 `editable=None`

## 执行过的命令

```bash
# 单元测试
python -m pytest tests/test_silent_monitor.py -v
python -m pytest tests/test_history_and_terminal_learning.py -v
python -m pytest tests/test_context_helper_client.py -v
python -m pytest tests/test_injector_strategy.py -v
python -m pytest tests/test_history_backfill.py -v

# 记事本冒烟测试
python tests/smoke_notepad_silent_monitor.py

# DLL/EXE 存在性检查
find native/context_helper/build -name "sayit_keyboard_helper.dll"
find native/context_helper/build -name "sayit_context_helper_dll.dll"
find native/context_helper/build -name "sayit_context_helper.exe"

# DLL 加载/运行时验证
python -c "..."  # 多次调用验证 DLL 和 EXE 行为

# 路径验证
python -c "..."  # PROJECT_ROOT 验证、server.py vs 独立脚本
```

## 测试结果

**单元测试：13/13 通过**
| Suite | Pass | Fail | Notes |
|-------|------|------|-------|
| test_silent_monitor | 3 | 0 | 规则提取、大修改过滤、键盘事件跟踪 |
| test_history_and_terminal_learning | 3 | 0 | 终端文本归一化、history_id 迁移、静默学习状态更新 |
| test_context_helper_client | 4 | 0 | JSON-RPC 往返、焦点上下文映射、缓存、缺失降级 |
| test_injector_strategy | 5 | 0 | Chrome UIA、Google Docs Clipboard、终端/WinTerm/Word 策略 |
| test_history_backfill | 1 | 0 | 手动编辑回填 |

**记事本冒烟测试：通过**
- 注入 "hello wrld" → 编辑为 "hello world" → 生成规则 `wrld→world`
- status: TRACKING → EXTRACTED
- 上下文读取路径：EXE subprocess（Path 2）

**DLL 运行时测试：关键发现**
- DLL 加载成功 ✓
- DLL `get_full_context_json(0)` 调用 → exit 127（STATUS_DLL_INIT_FAILED）✗

## 未解决的问题

1. DLL 的 ComInit 使用 STA，与 Python comtypes 的 MTA 冲突，需修复 `main.cpp` 的 `COINIT_APARTMENTTHREADED` → `COINIT_MULTITHREADED`
2. Python UIA 降级路径在无 UIA 焦点元素时脆弱
3. SilentMonitor._poll_keyboard_events() 未尝试 ContextHelperDll 作为备选

## 风险

- **当前静默学习的可靠路径仅为 EXE subprocess**。如果 EXE 文件缺失或崩溃后无法自动重启，_start_track 和 _poll_keyboard_events 都会降级到能力大幅减弱的路径
- DLL 崩溃（exit 127）会在 `_get_focus_context_via_dll()` 中导致整个 Python 进程退出，但因为 `get_focus_context()` 在调用 DLL 前有 `was_portaudio_used()` 检查 + try/except，在实际 server.py 运行时通常不会触发——PortAudio 先初始化 → `was_portaudio_used()=True` → DLL 路径跳过
- **主输入链路不受影响**，所有失败路径都有 try/except 保护
- EXE 自动重启机制已验证有效

## 当前提交ID

```
6173a8e
```
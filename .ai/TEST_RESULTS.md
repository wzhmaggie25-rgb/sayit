# Test Results
> 最后一次更新：2026-06-26 18:32

## 本轮说明（第六轮）

本轮不涉及代码修改，未运行项目测试。

### 验证内容

1. **配置加载验证**：`load_config()` 返回 `claude_timeout_seconds=7200` ✅
2. **桥日志验证**：`(timeout=7200s, ...)` ✅
3. **Claude 分派验证**：`=== CLAUDE EXECUTION START (SHA=1c390675bfe9) ===` ✅
4. **进程验证**：旧桥已全部终止，仅存 Claude PID 26244 执行中 ✅
5. **Git 分支配置**：单远程/merge 条目 ✅

修复 Agent Bridge 快捷启动：`start_bridge.bat` 闪退修复 + 桌面快捷方式安装脚本。
**不修改 SayIt 业务代码**。

## 启动器验证

| 验证项 | 结果 |
|--------|------|
| `start_bridge.bat --version` 输出横幅 + 版本号 | ✅ |
| `start_bridge.bat --once` 输出 `Agent Bridge v0.2.0 starting` | ✅ |
| 自动检测 `py -3` (Python 3.12) | ✅ |
| `.git` 不存在时错误停留 | ✅ |
| `bridge.py` 不存在时错误停留 | ✅ |
| 轮询模式输出 `Waiting 30s...` | ✅ |
| `install_bridge_shortcut.bat` 安装成功 | ✅ |
| 桌面快捷方式 `SayIt AI Bridge.lnk` 存在 | ✅ |
| 快捷方式目标 = `cmd.exe /k start_bridge.bat` | ✅ |
| 快捷方式起始目录 = 仓库根 | ✅ |
| `pause` 保持窗口不闪退 | ✅ |

## 本轮说明（第四轮）

修复 Agent Bridge v0.1.0 9 个问题（A–H），更新至 v0.2.0。**详细设计见 `.ai/BRIDGE_DESIGN.md`**。

## 桥梁单元测试（v0.2.0）

文件：`tests/test_agent_bridge.py`（36 个测试，全部通过）

| Suite | Tests | Pass | Fail | Notes |
|-------|-------|------|------|-------|
| PreconditionTests | 8 | 8 | 0 | C 设计：重启恢复、新任务识别、已处理跳过、脏目录/分支/进行中保护 |
| ParseResultTests | 8 | 8 | 0 | D 覆盖：直接JSON、envelope+json、envelope+codeblock、envelope+纯文本、非零退出、无效JSON、is_error |
| ClaudeInvocationTests | 2 | 2 | 0 | B 验证：`call_claude` 和 `claude_binary_path` 均使用 `cwd=PROJECT_ROOT` |
| LockTests | 3 | 3 | 0 | PID 锁获取释放/并发/残留覆盖 |
| StateTests | 3 | 3 | 0 | 状态持久化：空/匹配/不同 SHA |
| GitHelperTests | 7 | 7 | 0 | 辅助函数：repo/分支/脏/MERGE_HEAD/SHA/进行中操作 |
| IsTaskReadyTests | 4 | 4 | 0 | READY/BLOCKED/DONE/空 状态检测 |
| BuildPromptTests | 1 | 1 | 0 | Prompt 包含任务文本和约束 |

**合计：36/36 通过** ✅

### 新增/修改测试（v0.1.0 → v0.2.0）

新增 7 个测试：
- `test_local_ready_without_remote_changes_still_executes` — Issue C 核心
- `test_ready_after_new_commit_is_new_task` — Issue C
- `test_already_processed_skips` — Issue C 重复防护
- `test_blocked_without_remote_skips` — Issue C
- `test_done_without_remote_skips` — Issue C
- `test_envelope_is_error` — Issue D
- `test_envelope_plain_text_result` — Issue D

移除 2 个旧测试（EndToEndMockedTests 已拆解到各 suite；ClaudeInvocationTests 从 4 精简为 2 个更聚焦的测试）

## 桥梁冒烟测试（真实 Claude Code）

文件：`tests/smoke_agent_bridge.py`

**执行时间：2026-06-26 15:56**
**结果：通过** ✅

| 检查项 | 结果 |
|--------|------|
| 正确分支 (`feature/silent-learning-stabilization`) | ✅ |
| 干净工作目录 | ✅ |
| 无进行中 git 操作 | ✅ |
| Claude 退出码 0 | ✅ |
| `.ai/BRIDGE_SMOKE_TEST.md` 已创建 | ✅ (48 字节) |
| 内容正确 | ✅ |
| 存在新提交 | ✅ (`e6aa861`) |
| 提交消息 `test: bridge smoke test` | ✅ |
| 已推送至 `origin` | ✅ |
| 仅 `.ai/BRIDGE_SMOKE_TEST.md` 被修改 | ✅ |
| Claude 输出指示成功 | ✅ |

**Claude 版本：** 2.1.163
**模型：** `glm-latest`（继承 CC Switch，未强制 `--model`）
**耗时：** 38.4 秒
**权限提示：** 无（`--allowedTools Read Edit Write 'Bash(git*)' 'Bash(python*)' 'Bash(pytest*)'` 正常工作）

## 桥梁冒烟测试（第三轮记录）

文件：`tests/smoke_agent_bridge.py`

⚠️ **未执行**——上一轮冒烟测试需要真实调用 Claude Code（`claude -p`）。本轮已执行并成功通过。

## 本轮说明（第二轮）

本轮为 ZCode 自动化能力评估（只读探查），**未运行业务代码测试**。
所有调查结果见 `.ai/ZCODE_AUTOMATION_CAPABILITY.md`。

### 环境能力扫描

| 项目 | 结果 | 方法 |
|------|------|------|
| `zcode` CLI on PATH | ❌ 不存在 | `where zcode` |
| `ZCode.exe` CLI 子命令 | ❌ 无 | `--help` / `--version`（仅启动 Electron） |
| ZCode MCP 服务端 | ❌ 不暴露 | 配置检查（仅客户端） |
| `zcode://` URI scheme | ⚠️ 已注册 | `reg query HKCR\zcode` → `ZCode.exe "%1"` |
| `codex://` URI scheme | ⚠️ 已注册（无 command） | `reg query HKCR\codex` |
| Claude Code 可用 | ✅ 2.1.185，支持 `-p` 非交互 | `where claude` + `--version` |
| Cursor CLI 非交互 | ❌ 仅 IDE 启动器 | `where cursor` + `--help` |
| aider / gh / ollama / gemini / continue | ❌ 均不在 PATH | `where` 各工具 |

## 单元测试

### test_silent_monitor.py
| Test | Pass | Notes |
|------|------|-------|
| test_small_edit_extracts_rule_and_updates_history | ✅ | `wrld` → `world`, status `EXTRACTED` |
| test_large_full_field_edit_is_not_learned | ✅ | status `LARGE_MODIFY` |
| test_keyboard_events_track_typeless_edit_keys | ✅ | `A`+`Enter` 正确识别 |

**前置条件：** 无（纯单元测试，mock Database/focus_context）

### test_history_and_terminal_learning.py
| Test | Pass | Notes |
|------|------|-------|
| test_terminal_text_normalization_ignores_spacing_and_newlines | ✅ | 终端文本空格/换行归一化 |
| test_legacy_integer_history_id_table_is_migrated_to_text | ✅ | id 列从 INTEGER 迁移 TEXT |
| test_text_history_id_can_be_updated_by_silent_learning_status | ✅ | update_history_edit TRACKING 状态 |

**前置条件：** 临时 SQLite 数据库

### test_context_helper_client.py
| Test | Pass | Notes |
|------|------|-------|
| test_fake_helper_json_rpc_roundtrip | ✅ | JSON-RPC 请求/响应 |
| test_focus_context_maps_native_full_context | ✅ | 原生上下文映射 FocusContext |
| test_last_focused_info_cache_matches_typeless_shape | ✅ | 缓存形状验证 |
| test_missing_helper_falls_back_to_none | ✅ | EXE 缺失时返回 None |

### test_injector_strategy.py
| Test | Pass | Notes |
|------|------|-------|
| test_chrome_regular_input_uses_uia | ✅ | 标准输入框 UIA 注入 |
| test_google_docs_url_blacklist_uses_clipboard | ✅ | Google Docs 黑名单 Clipboard |
| test_terminal_window_class_uses_clipboard | ✅ | 终端类 → Clipboard |
| test_windows_terminal_processes_use_clipboard | ✅ | Windows Terminal → Clipboard |
| test_word_typeless_blacklist_uses_clipboard | ✅ | Word Typeless 黑名单 → Clipboard |

### test_history_backfill.py
| Test | Pass | Notes |
|------|------|-------|
| test_manual_history_edit_backfills_typeless_edit_state | ✅ | 手动编辑回填 Typeless 状态 |

## 记事本冒烟测试（`smoke_notepad_silent_monitor.py`）

**前置条件：** 临时 APPDATA + 新建记事本窗口 + 临时 .txt 文件

### 测试步骤
1. 打开记事本 → 注入 "hello wrld" → ✅ 注入成功
2. 创建 history_id → ✅ hid=`0f1e987680da420f84e8d0b8f33cf7aa`
3. 启动 SilentMonitor → ✅ start 返回
4. 编辑为 "hello world" → ✅ set_focused_value 成功
5. 等待 8s 静默学习完成 → ✅ 规则生成

### 结果
```json
{
  "ok": true,
  "rules": [{"pattern": "wrld", "replacement": "world"}],
  "history.edited_text_status": "EXTRACTED"
}
```
✅ 通过

### 实际调用路径（EXE 优先）
1. `injector.inject("hello wrld")` → UIA ValuePattern
2. `SilentMonitor.start()` → daemon 线程
3. `_start_track()` → `get_focus_context_for_window(hwnd=0x71042)`
   - Path 1: Win32 child-edit → 找到 Edit 子窗口, `is_editable=True`
   - ✅ 通过
4. 监控循环 → `_poll_keyboard_events()` → `ContextHelperClient.poll_keyboard_events()`
   - ✅ 通过（returned events）
5. 检测编辑 → `_check_edited_text("track_timeout")`
   - `analyze_modification` → `change_ratio=0.083` → 非大修改
   - `extract_inserted_region` → 锚点对齐 → 提取 "hello world"
   - `learn_from_edit("hello wrld", "hello world")`
   - `generate_token_rules` → 检查 "wrld"→"world" → 通过 `_is_learnable_token_pair`（英文字母）
   - ✅ 规则生成
6. `db.merge_rules` → ✅ 保存
7. `hotwords_mgr.add_word("world")` → ✅ 词典添加

## DLL 运行时测试

### 测试 1：DLL 加载
- `ContextHelperDll.is_available` = ✅ True
- DLL 路径：`native/context_helper/build/Release/sayit_context_helper_dll.dll`
- `ctypes.CDLL` 返回有效句柄

### 测试 2：DLL 函数调用（在 server.py 上下文中）
- `get_full_context_json(0)` → ❌ **exit 127（STATUS_DLL_INIT_FAILED）**
- 根因：DLL 内 `ComInit` 使用 `COINIT_APARTMENTTHREADED`，但 Python comtypes 已设 `COINIT_MULTITHREADED`
- 3 次独立测试一致崩溃

### 测试 3：EXE 子进程通信
- `ContextHelperClient().get_full_context()` → ✅ 返回实时焦点上下文（app=zcode.exe, editable=True）
- `ContextHelperClient().poll_keyboard_events()` → ✅ 返回键盘事件列表
- EXE 进程关闭后自动重启 → ✅ 验证通过

### 测试 4：PortAudio 守卫行为
- `was_portaudio_used() == False` 时 → get_focus_context 计划尝试 DLL（但 DLL 调用会崩溃）
- `was_portaudio_used() == True` 时 → get_focus_context **跳过 DLL**（实际 server.py 运行中如此）
- ✅ 守卫机制工作，跳过崩溃路径

### 测试 5：Python UIA 降级路径
- `get_focused_element_snapshot()` → `editable=None, role=None`（当前 ZCode 环境）
- `read_focus_text()` → None（无 UIA ValuePattern/TextPattern 焦点元素）
- `_get_focus_context_python()` → 返回 is_editable=False
- ⚠️ 降级路径在当前环境无法提取文本

## 测试摘要

| Suite | Pass | Fail | Skip | Notes |
|-------|------|------|------|-------|
| Unit: silent_monitor | 3 | 0 | 0 | 全部通过 |
| Unit: history_and_terminal_learning | 3 | 0 | 0 | 全部通过 |
| Unit: context_helper_client | 4 | 0 | 0 | 全部通过 |
| Unit: injector_strategy | 5 | 0 | 0 | 全部通过 |
| Unit: history_backfill | 1 | 0 | 0 | 全部通过 |
| 记事本冒烟测试 | 1 | 0 | 0 | 规则生成成功 |
| DLL 加载 | 1 | 0 | 0 | 加载成功 |
| DLL 函数调用 | 0 | 3 | 0 | exit 127 一致崩溃 |
| EXE 通信 | 3 | 0 | 0 | 全部通过 |
| PortAudio 守卫 | 2 | 0 | 0 | 正确跳/不跳 DLL |
| Python UIA 降级 | 0 | 1 | 0 | 当前环境无法读取焦点文本 |
| **桥梁单元测试 (v0.1.0)** | **29** | **0** | **0** | **第一版全部通过** |
| **桥梁单元测试 (v0.2.0)** | **36** | **0** | **0** | **修复版全部通过** |
| **桥梁冒烟测试** | **1** | **0** | **0** | **真实 Claude 通过 (e6aa861)** |

---

## 本轮说明（第六轮：COM apartment 修复 + 桥梁自动执行恢复）

### 桥梁自动执行恢复

| 问题 | 修复 | 结果 |
|------|------|------|
| `.git/REBASE_HEAD` 残留 → 桥梁误认为有进行中操作 | 删除残留文件 | ✅ 桥接恢复正常轮询 |
| 默认 `claude_timeout_seconds: 300` 不足以完成 C++ 编译 | 创建 `bridge_config.json`，设置 900s | ✅ 后续配置生效 |

### COM Apartment 针对性测试

#### A. 编译验证

DLL 和 EXE 均成功构建（Claude Code 执行，无编译错误）：

| 工件 | 路径 | 状态 |
|------|------|------|
| `sayit_context_helper.exe` | `native/context_helper/build/Release/sayit_context_helper.exe` (83KB, 17:10) | ✅ |
| `sayit_context_helper_dll.dll` | `native/context_helper/build/Release/sayit_context_helper_dll.dll` (70KB, 17:07) | ✅ |

#### B. EXE 回归冒烟

执行命令：
```bash
# ping
echo '{"id":"0","method":"ping"}' | sayit_context_helper.exe
# → {"id":"0","ok":true,"result":{"pong":true}}

# get_full_context
echo '{"id":"1","method":"get_full_context"}' | sayit_context_helper.exe
# → {"id":"1","ok":true,"result":{...}}
```

| 检查项 | 结果 |
|--------|------|
| ping 返回成功 JSON | ✅ `ok=True, result.pong=True` |
| get_full_context 返回可解析 JSON | ✅ |
| 进程正常退出（exit 0） | ✅ |
| 未破坏原 subprocess 路径 | ✅ |

#### C. Python/comtypes MTA + DLL 同线程测试（核心）

**独立脚本验证（`run_dll_com_test.py`）：**

| 检查项 | 结果 |
|--------|------|
| 显式 CoInitializeEx(MTA) hr=0x00000000 | ✅ S_OK |
| DLL 加载（ctypes.CDLL） | ✅ |
| `get_full_context_json(0)` 返回非空 | ✅ |
| 返回字段含 UIA 数据 | ✅ `text_insertion_point`, `active_application`, `device_environment` |
| comtypes 在 MTA 后导入 | ✅ 成功（预期 error 因线程模式已锁） |

**pytest 子进程隔离测试（`test_context_helper_dll_com.py`）：**

| 检查项 | 结果 |
|--------|------|
| pytest 环境已 STA（anyio）→ 自动子进程 | ✅ |
| 子进程中 notepad 窗口可见性 | ⏭️ SKIP（CI/非交互环境无前台窗口 — 预期行为） |
| 行为正确（不误报 PASS/FAIL） | ✅ |

#### D. 修复证据

- **修复前**：DLL 在 server.py/comtypes MTA 线程中崩溃（exit 127 / STATUS_DLL_INIT_FAILED）
- **修复后**：DLL 在 MTA 线程中正常返回 UIA JSON 数据（`text_insertion_point`, `device_environment` 等）
- **`main.cpp` diff** 唯一变化：编译期 `#ifdef BUILD_DLL` → MTA，`#else` → STA<br>
  `ComInit` 重构：跟踪 `hr()` 和 `initialized_`，只在 S_OK/S_FALSE 时 CoUninitialize<br>
  EXE 行为完全不变
- EXE 回归通过：ping + get_full_context
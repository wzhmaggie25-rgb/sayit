# Test Results
> 最后一次更新：2026-06-26 15:56

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
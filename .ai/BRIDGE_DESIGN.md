# Agent Bridge — 桥梁设计文档

> 版本：0.2.0
> 创建：2026-06-26
> 更新：2026-06-26

## 目标

建立本地轮询桥梁，让 ChatGPT 通过 GitHub 推送 `.ai/CURRENT_TASK.md`（状态为 `READY`），桥梁自动领取任务并交给 Claude Code 非交互执行，结果写回 GitHub。

## 架构概况

```
ChatGPT                     ZCode (本机)                    GitHub
   │                           │                              │
   │  写入 CURRENT_TASK.md     │                              │
   │  git push                 │                              │
   │ ──────────────────────────┼─────────────────────────────>│
   │                           │                              │
   │                           │  bridge.py (每 30s 轮询)      │
   │                           │  git fetch                   │
   │                           │ ────────────────────────────>│
   │                           │<─────────────────────────────│
   │                           │                              │
   │                           │  check_preconditions()        │
   │                           │  ✓ 正确分支                   │
   │                           │  ✓ 工作目录干净               │
   │                           │  ✓ 无进行中操作              │
   │                           │  ✓ pull --ff-only            │
   │                           │  ✓ CURRENT_TASK == READY     │
   │                           │  ✓ 未重复执行                │
   │                           │                              │
   │                           │  claude -p <prompt>           │
   │                           │  (非交互执行任务)             │
   │                           │                              │
   │                           │  git add + commit + push     │
   │                           │ ────────────────────────────>│
   │<──────────────────────────┼──────────────────────────────│
   │  审查结果                  │                              │
```

## 组件

### `tools/agent_bridge/bridge.py`（核心桥梁）

单文件实现，约 500 行。包含：

| 函数 | 职责 |
|------|------|
| `load_config()` | 从 JSON 文件加载配置，合并默认值 |
| `check_preconditions()` | 执行所有安全检查，返回新 SHA 或失败原因 |
| `run_claude_task()` | 构建 prompt、调用 Claude、解析结果 |
| `run_once()` | 完整的一次领取 → 执行 → 记录循环 |
| `polling_loop()` | 无限轮询循环 |
| `acquire_lock()` / `release_lock()` | PID 文件锁防并发 |
| `is_task_already_processed()` / `mark_task_processed()` | 状态持久化防重复 |
| `build_claude_prompt()` | 组装包含 AGENTS.md 规则和任务文本的 prompt |
| `parse_claude_result()` | 解析 Claude JSON 输出（含 code block 兼容） |
| `set_task_status()` | 更新 CURRENT_TASK.md 状态 |

### `tools/agent_bridge/bridge_config.json`（本地配置）

Git 排除，不提交。支持自定义：
- `branch`：跟踪的分支名
- `poll_interval_seconds`：轮询间隔
- `claude_timeout_seconds`：Claude 执行超时
- `claude_binary`：Claude 可执行文件路径

### `start_bridge.bat`（启动脚本）

```batch
@echo off
chcp 65001 >nul
cd /d "C:\path\to\sayit_zcode"
python tools/agent_bridge/bridge.py
```

### Bridge 状态文件（Git 排除）

- `bridge.lock` — 运行中 PID（防并发）
- `bridge_state.json` — 上次处理的 SHA 和执行结果
- `bridge.log` — 运行时日志

## 安全机制

| 机制 | 实现 |
|------|------|
| 分支保护 | 非 `feature/silent-learning-stabilization` 不执行 |
| 脏工作目录保护 | `git status --porcelain` 不为空则不执行 |
| 进行中操作保护 | 检查 `.git/MERGE_HEAD` 等标记文件 |
| 防重复执行 | 记录 `last_processed_sha`，匹配则不执行 |
| 防并发 | PID 文件锁 + 进程存在性检查 |
| 紧凑拉取 | 使用 `git pull --ff-only`，不会自动合并 |
| 异常保留现场 | Claude 超时/失败时不 reset/clean |

### Claude 权限模型（新增于 v0.2.0 — Issue E）

桥梁通过 `--allowedTools` 限缩 Claude 的能力，不使用 `--dangerously-skip-permissions`。

默认 allowlist：

| 工具 | 用途 |
|------|------|
| `Read` | 读取 AGENTS.md、CURRENT_TASK.md、代码文件 |
| `Edit` | 修改指定文件 |
| `Write` | 创建新文件（如测试结果、报告） |
| `Bash(git*)` | git status / add / commit / push |
| `Bash(python*)` | 运行 Python 脚本 |
| `Bash(pytest*)` | 运行测试 |
| `Bash(claude*)` | Claude 自身（保留扩展性） |

用户可通过 `bridge_config.json` 的 `claude_allowed_tools` 自定义。

### 输出解析（新增于 v0.2.0 — Issue D）

`parse_claude_result()` 处理 Claude Code `--output-format json` 的五种输出形态：

1. **顶层 JSON**：`{"ok": true, ...}` → 直接解析
2. **Envelope + 内嵌 JSON 字符串**：`result` 字段含 `{"ok": true}` → 先取 result 再解析
3. **Envelope + code block**：`result` 字段含 ````json {"ok": true} ``` ` → 提取 code block 再解析
4. **Envelope + 纯文本**：`result` 为纯文本 → 返回文本，不做强度断言
5. **非零退出码** → 判定失败
6. **is_error = true** → 判定失败
7. **无效 JSON** → 判定 BLOCKED

### BLOCKED 同步（新增于 v0.2.0 — Issue H）

失败时（超时、非零退出、解析失败）：

1. 本地写入 `.ai/BRIDGE_RUN_REPORT.md` 说明失败原因（脱敏）
2. 将 `.ai/CURRENT_TASK.md` 状态改为 `**BLOCKED**`
3. 精确 stage 仅 `.ai/CURRENT_TASK.md` 和 `.ai/BRIDGE_RUN_REPORT.md`（按文件名，非 `git add .`）
4. `git reset HEAD --` 任何多余的暂存文件
5. `git commit -m "chore: bridge BLOCKED"`（无变化时也允许成功）
6. `git push`
7. 失败原因同时打印到控制台

## 已知限制（v0.2.0）

- 不支持 Windows 服务或计划任务
- 不支持多任务队列（一次只处理一个 READY 任务）
- 不支持 Webhook（只使用轮询）
- 无通知机制（Slack/微信等）
- 不自动更新桥梁自身
- 默认继承 CC Switch 模型配置，不强制设置 `--model`

## 启动和停止

```bash
# 启动（前台窗口）
start_bridge.bat

# 或直接
python tools/agent_bridge/bridge.py

# 单次执行（非轮询）
python tools/agent_bridge/bridge.py --once

# 停止
Ctrl+C
```

## 测试策略

- **单元测试**：mock git 命令和 claude 进程，测试所有安全检查边界（36 个测试）
- **冒烟测试**：真实调用 Claude Code（`claude -p --output-format json --allowedTools ...`），只更新一个测试文件
- 测试不修改 SayIt 业务代码
# Agent Bridge — 本地 Claude Code 任务桥梁

## 概述

Agent Bridge 是 SayIt 项目与 Claude Code 之间的本地任务执行桥梁。
它每 30 秒轮询 GitHub 远程分支，发现新的 `READY` 任务后安全拉取，
调用本机 Claude Code 非交互执行，并将结果提交推送回 GitHub。

**目标**：让 ChatGPT 通过 GitHub 推送任务描述，本地自动执行。

## 前置条件

- Python 3.10+
- Git（已配置凭据）
- Claude Code（已登录认证）
- 项目在 `feature/silent-learning-stabilization` 分支

## 快速启动

```bash
# 确保在正确的分支
git checkout feature/silent-learning-stabilization

# 启动桥梁
start_bridge.bat

# 或直接运行
python tools/agent_bridge/bridge.py
```

**停止**：按 `Ctrl+C`

## 配置

复制配置模板并按需修改：

```bash
cp tools/agent_bridge/bridge_config.example.json tools/agent_bridge/bridge_config.json
```

支持以下配置项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `branch` | `feature/silent-learning-stabilization` | 跟踪的分支 |
| `remote` | `origin` | 远程名称 |
| `poll_interval_seconds` | `30` | 轮询间隔 |
| `claude_timeout_seconds` | `300` | Claude 执行超时（秒） |
| `claude_binary` | `claude` | Claude 可执行文件 |
| `log_level` | `info` | 日志级别 |
| `claude_allowed_tools` | `["Read","Edit","Write","Bash(git*)","Bash(python*)","Bash(pytest*)","Bash(claude*)"]` | Claude 工具权限白名单 |

> **模型配置**：桥梁默认不设置 `--model`，继承 CC Switch 中配置的模型。
> 如需要覆盖，可在配置中添加 `"model": "claude-sonnet-4-20250514"`。

## 命令行选项

```bash
# 正常轮询模式
python tools/agent_bridge/bridge.py

# 单次执行（检查一次后退出）
python tools/agent_bridge/bridge.py --once

# 查看版本
python tools/agent_bridge/bridge.py --version
```

## 工作流程

### 每轮循环

1. `git fetch origin feature/silent-learning-stabilization`
2. 如果远程领先且可 fast-forward，`git pull --ff-only`
3. 安全检查：
   - 当前分支正确
   - 工作目录干净
   - 无进行中的 merge/rebase/cherry-pick
   - `CURRENT_TASK.md` 状态为 `**READY**`
   - 该任务指纹（HEAD SHA）尚未处理过
   - 无其他 bridge 实例运行（锁文件）
4. 通过检查后，调用 `claude -p <prompt> --output-format json --allowedTools Read Edit Write 'Bash(git*)' 'Bash(python*)' 'Bash(pytest*)'`
5. Claude 执行任务、更新代码和 .ai 报告、提交推送
6. 更新状态文件、释放锁

> **注意**：桥梁每轮强制 fetch 并读取 CURRENT_TASK.md，不依赖远程是否产生新提交。
> 重启时可恢复本地已有的未处理 READY 任务。

### Claude 被要求

- 先读取 `AGENTS.md`、`.ai/PROJECT_STATE.md`、`.ai/CURRENT_TASK.md`
- 严格执行 CURRENT_TASK，不扩大范围
- 禁止修改 `main`/`backup/*`、禁止 force push
- 运行所有测试并更新报告
- 完成后提交推送
- 输出结构化 JSON

## 安全注意事项

- **锁定**：PID 文件锁防止并发
- **防重复**：记录已处理的任务 SHA
- **非破坏性**：使用 `--ff-only` 拉取，不自动 reset/clean
- **保留现场**：Claude 失败后保留工作目录供人工检查
- **不读取凭据**：桥梁不处理 API key/token

## 文件清单

| 文件 | 提交与否 | 说明 |
|------|----------|------|
| `tools/agent_bridge/bridge.py` | ✅ 提交 | 核心桥梁 |
| `tools/agent_bridge/bridge_config.example.json` | ✅ 提交 | 配置模板 |
| `tools/agent_bridge/README.md` | ✅ 提交 | 本文件 |
| `tools/agent_bridge/bridge_config.json` | ❌ 排除 | 本地配置 |
| `tools/agent_bridge/bridge.lock` | ❌ 排除 | 运行时锁 |
| `tools/agent_bridge/bridge_state.json` | ❌ 排除 | 运行状态 |
| `tools/agent_bridge/bridge.log` | ❌ 排除 | 日志 |
| `start_bridge.bat` | ✅ 提交 | 启动脚本 |
| `.ai/BRIDGE_DESIGN.md` | ✅ 提交 | 设计文档 |

## 故障排除

**Claude 未找到：**
```bash
# 确认 Claude 在 PATH 上
claude --version
```

**Git 认证失败：**
确保已配置 Git Credential Manager 或 SSH 密钥。

**Bridge 拒绝执行：**
查看 `tools/agent_bridge/bridge.log` 了解具体原因。常见原因：
- 不在目标分支
- 工作目录有未提交更改
- 存在进行中的 merge/rebase

**锁文件残留：**
如果 bridge 异常退出，手动删除锁文件：
```bash
rm tools/agent_bridge/bridge.lock
```
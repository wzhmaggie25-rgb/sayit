# Current Task
> 最后一次更新：2026-06-26

## 状态

**READY**

## 任务名称

建立 SayIt 本地 AI 任务桥梁第一版：每 30 秒从 GitHub 同步任务，并调用 Claude Code 非交互执行。

## 目标

完成后，用户只需要与 ChatGPT 对话：

1. ChatGPT 将任务写入 `.ai/CURRENT_TASK.md` 并推送到 GitHub；
2. 本地桥梁每 30 秒检查远程分支；
3. 发现新的 `READY` 任务后，安全拉取；
4. 调用本机 Claude Code `claude -p` 执行任务；
5. Claude Code 更新代码、测试和 `.ai` 报告并提交推送；
6. ChatGPT从 GitHub读取结果并审查。

本轮只搭建桥梁，不修复静默学习，不修改 SayIt 业务功能。

## 已确认环境

- 项目目录：`D:\code\sayit_zcode`
- 当前开发分支：`feature/silent-learning-stabilization`
- 稳定备份分支：`backup/local-working-2026-06-25`
- Claude Code：v2.1.185
- 可用非交互入口：`claude -p/--print`
- ZCode：无可靠 CLI / Headless / MCP server / HTTP API，不作为自动执行端

## 实现范围

建议新建：

```text
tools/agent_bridge/
├── bridge.py
├── bridge_config.example.json
├── README.md
└── start_bridge.bat
```

允许按实际需要增加少量测试文件，但不得修改业务代码。

## 桥梁行为

### 1. 轮询

- 默认每 30 秒运行一次；
- 只监控 `origin/feature/silent-learning-stabilization`；
- 使用 `git fetch origin feature/silent-learning-stabilization` 检查远程变化；
- 不使用 GitHub Token，不读取凭据，不调用 `git credential fill`；
- 通过现有 Git Credential Manager完成正常 git认证。

### 2. 执行前安全检查

发现远程任务变化后必须先确认：

- 当前目录是目标仓库；
- 当前分支是 `feature/silent-learning-stabilization`；
- 工作目录干净；
- 没有进行中的 merge、rebase、cherry-pick；
- 本地分支可以 `git pull --ff-only`；
- `.ai/CURRENT_TASK.md` 状态为 `READY`；
- 任务 ID / 内容哈希尚未执行过；
- 没有另一个 bridge 或 Claude任务正在运行。

任何一项不满足都不得自动修改代码，只记录脱敏状态并等待下一轮。

### 3. 锁与防重复

- 使用本地锁文件防止并发运行；
- 锁文件和本地状态不得提交 GitHub；
- 保存最近成功领取的任务内容哈希或提交 SHA；
- 同一任务只能执行一次；
- 进程异常退出后允许安全恢复，但不能重复执行已经提交完成的任务。

请把本地运行状态、锁和日志加入 `.gitignore`。

### 4. 调用 Claude Code

桥梁必须通过 Python `subprocess` 调用本机 `claude`，不得使用 UI 自动化。

Claude提示词必须要求它：

- 先读取 `AGENTS.md`、`.ai/PROJECT_STATE.md`、`.ai/CURRENT_TASK.md`；
- 严格执行 CURRENT_TASK，不扩大范围；
- 禁止修改 `main` 和 `backup/*`；
- 禁止 force push；
- 禁止读取或输出 Token、API Key、Cookie、完整个人配置；
- 必须更新 `.ai/ZCODE_REPORT.md` 与 `.ai/TEST_RESULTS.md`；
- 测试未通过不得声称完成；
- 完成后提交并推送当前 feature分支；
- 将 CURRENT_TASK 状态改为 `DONE` 或 `BLOCKED`；
- 最终输出结构化 JSON摘要。

优先使用：

```text
claude -p <prompt> --output-format json
```

但必须先根据本机 `claude --help` 验证参数组合，不得猜测。

### 5. 超时和失败处理

- 必须设置合理超时；
- Claude返回非零退出码、超时、JSON无法解析或 git push失败时：
  - 不得无限重试；
  - 不得删除已有修改；
  - 不得自动 reset、clean、checkout覆盖；
  - 记录为 `BLOCKED`；
  - 保留工作目录供人工检查；
- 日志必须脱敏，不记录完整 prompt 中可能存在的私密内容，不记录环境变量值。

### 6. 启动方式

第一版只要求：

- `start_bridge.bat` 可以在普通 Windows用户权限下启动；
- 窗口中明确显示：停止、等待、领取任务、执行中、完成、阻塞；
- Ctrl+C 可以安全停止；
- 暂时不要注册 Windows服务、计划任务或开机启动；
- 暂时不要隐藏窗口后台运行。

## 测试要求

必须至少完成以下测试：

1. 无远程变化时只等待，不调用 Claude；
2. CURRENT_TASK不是 READY 时不执行；
3. 工作目录不干净时拒绝执行；
4. 非目标分支时拒绝执行；
5. 同一任务不会执行两次；
6. 锁文件能阻止两个 bridge实例；
7. 使用 mock/fake Claude命令完成一次端到端演练；
8. 演练不得修改 SayIt业务代码；
9. 真实 Claude只允许进行一次“只更新 `.ai/BRIDGE_SMOKE_TEST.md`”的低风险冒烟测试；
10. 冒烟测试完成后确认提交和推送成功。

## 禁止事项

- 禁止修改热键、录音、ASR、纠错、注入、静默学习和进程管理代码；
- 禁止触碰 main、backup分支；
- 禁止 force push、reset --hard、git clean；
- 禁止安装新软件或升级 Claude Code；
- 禁止创建 PAT 或把凭据写进配置；
- 禁止把桥梁做成无人监督的无限任务循环；一次只能领取一个 READY任务，完成或阻塞后等待新任务；
- 禁止自动合并 PR；
- 禁止自动发布软件。

## 交付文档

必须更新或新增：

- `tools/agent_bridge/README.md`
- `.ai/BRIDGE_DESIGN.md`
- `.ai/ZCODE_REPORT.md`
- `.ai/TEST_RESULTS.md`
- `.ai/CURRENT_TASK.md`

报告中必须明确：

- 实际调用的 Claude命令；
- 轮询和防重复机制；
- 安全边界；
- 测试结果；
- 冒烟提交 ID；
- 用户今后如何启动和停止桥梁；
- 尚未实现的能力。

## 提交要求

允许提交本任务涉及的桥梁代码、测试和 `.ai` 文档：

```bash
git add tools/agent_bridge .ai .gitignore
git commit -m "feat: add local Claude task bridge"
git push
```

完成后停止。不要开始修复静默学习。

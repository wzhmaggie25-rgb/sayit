# Current Task
> 最后一次更新：2026-06-26

## 状态

**DONE**

## 任务名称

修复 Agent Bridge 第一版的启动、任务领取、Claude 输出解析与真实冒烟测试问题。

## 背景

提交 `acde6ce` 已建立桥梁框架，29 个 mock 单元测试通过，但审查发现当前版本尚不能投入实际轮询：

1. 根目录的 `start_bridge.bat` 使用 `cd /d "%~dp0.."`，会进入仓库父目录，随后找不到 `tools/agent_bridge/bridge.py`。
2. `call_claude()` 未设置 `cwd=PROJECT_ROOT`，Claude 会继承启动终端目录，而不是被强制限定在 SayIt 仓库。
3. `check_preconditions()` 只有 fetch 到新提交时才读取 READY 任务；桥梁在 READY 任务已存在本地时启动或重启，可能永远不执行。
4. 无远程变化时 `run_once()` 会把当前 HEAD 标记为已处理，可能错误吞掉尚未执行的 READY 任务。
5. Claude Code `--output-format json` 可能返回包含 `result` 字段的外层 JSON，而当前解析器只接受顶层直接包含 `ok` 的对象。
6. `.ai/BRIDGE_SMOKE_TEST.md` 被 `.gitignore` 排除，但冒烟测试要求创建、提交并推送该文件。
7. `tests/smoke_agent_bridge.py` 即使没有创建文件、没有新提交或 JSON 解析失败，最后仍返回退出码 0。
8. 真实 Claude 冒烟测试尚未执行。
9. 失败时桥梁本地写入 BLOCKED，但需要明确如何让远程 GitHub 和 ChatGPT可靠看到阻塞状态，同时不得误提交 Claude留下的业务改动。

本轮只修桥梁，不修复静默学习，不修改 SayIt 业务代码。

## 必须修复

### A. 启动目录

- 将根目录 `start_bridge.bat` 修正为从脚本所在的仓库根目录启动：

```bat
cd /d "%~dp0"
python tools/agent_bridge/bridge.py %*
```

- 启动前验证 `tools/agent_bridge/bridge.py` 和 `.git` 存在；不存在时给出明确错误并退出非零。
- 增加对应测试或可重复验证记录。

### B. Claude 工作目录

- `claude --version` 与真实 `claude -p` 调用都必须设置：

```python
cwd=PROJECT_ROOT
```

- 不得依赖调用者当前终端目录。
- 增加单元测试验证 subprocess 的 cwd。

### C. READY 任务领取与重启恢复

重新设计一次轮询逻辑：

1. 每轮先做仓库、分支、脏目录、进行中操作检查；
2. 执行 fetch；
3. 如果远程领先且可 fast-forward，则 pull；
4. 无论本轮是否拉到新提交，都读取当前 `.ai/CURRENT_TASK.md`；
5. 只要状态为 READY 且任务指纹尚未成功/阻塞处理，就应执行；
6. 任务指纹应基于 CURRENT_TASK 内容哈希，或能唯一对应任务的提交 SHA；不得仅因为“本轮 fetch 无变化”而跳过；
7. 桥梁重启后，已存在本地的未处理 READY 任务必须能够恢复执行；
8. 非 READY 状态只等待，不得错误写入 `last_processed_sha`；
9. 不得把普通 HEAD 自动标记成已处理任务。

增加以下测试：

- READY 已在本地、远程无新提交时仍会执行；
- DONE/BLOCKED、远程无变化时不执行；
- 重启后未处理 READY 任务能恢复；
- 已处理的同一任务不会重复执行；
- 新任务即使基于同一分支仍会被识别。

### D. Claude JSON 输出

先使用用户当前已配置好的 Claude Code 模型执行一个只读命令，观察本机真实输出格式，不打印或提交任何密钥、环境变量或完整私人配置。

解析器必须兼容至少：

1. 顶层直接是任务结果：

```json
{"ok": true, "summary": "..."}
```

2. Claude Code `--output-format json` 的外层结果对象，其 `result` 字段中包含模型最终文本；如果 `result` 是 JSON 字符串或 Markdown JSON code block，应继续解析内部对象。

3. 如果本机 Claude版本支持且当前模型/供应商兼容，可评估 `--json-schema`；但不得假设，必须通过本机低风险测试验证后才能采用。

- 外层进程成功但内部结果 `ok=false`，必须判定失败。
- JSON无法解析必须判定 BLOCKED。
- 增加直接 JSON、外层 envelope、result code block、无效 JSON、非零退出码测试。

### E. Claude 权限模式

真实非交互调用前，必须验证当前 Claude配置是否能在无人点击的情况下：

- 修改指定测试文件；
- 执行 `git status`、`git add`、`git commit`、`git push`；
- 不访问仓库外文件；
- 不出现等待用户授权导致超时。

不得直接加入 `--dangerously-skip-permissions` 或 `bypassPermissions`。

如果需要命令行权限配置：

- 使用最小权限原则；
- 只允许完成任务所需的 Read/Edit/Write 与明确限定的 Bash 命令；
- 把权限策略写入 `.ai/BRIDGE_DESIGN.md` 和 README；
- 不把 Token、API Key、Cookie写入仓库。

### F. 模型配置

当前桥梁不得硬编码或强制传入 `--model`，继续使用用户刚在 CC Switch 中配置的 Claude模型。

- README明确说明：桥梁默认继承当前 Claude Code / CC Switch配置；
- 如未来增加可选 `model` 配置，默认必须为空；只有用户显式配置时才添加 `--model`；
- 日志不得输出 API Key、Base URL中的凭据或完整环境变量。

### G. 冒烟测试文件与退出码

- 从 `.gitignore` 中移除 `.ai/BRIDGE_SMOKE_TEST.md`；或采用同样清晰、安全、可审查的方案保证测试文件能被提交。
- `tests/smoke_agent_bridge.py` 必须在以下任一情况返回非零：
  - Claude退出非零；
  - 测试文件未创建；
  - 除允许文件外出现其他改动；
  - 没有新提交；
  - 提交未推送到目标远程分支；
  - Claude输出无法解析为成功结果。
- 所有 subprocess 必须使用 `cwd=ROOT`。
- 冒烟测试前要求：正确分支、干净工作目录、无进行中 Git操作。

### H. BLOCKED 状态同步

设计并实现可审查的阻塞回传：

- Claude超时、退出非零、解析失败时，保留其工作现场；不得 reset、clean、checkout覆盖。
- GitHub远程必须能够看到任务已 BLOCKED及简短脱敏原因。
- 不得把 Claude意外修改的业务文件一起提交。
- 可以只 stage/commit `.ai/CURRENT_TASK.md` 和专用 `.ai/BRIDGE_RUN_REPORT.md`，但必须验证不会包含其他文件。
- 如果 push本身失败，应保留本地状态并在控制台明确显示，不能谎称已通知 ChatGPT。
- 成功时避免桥梁在 Claude完成提交后再次产生未提交的 CURRENT_TASK变化。

增加成功和失败路径测试。

## 真实冒烟测试

完成以上修复和单元测试后，执行一次真实 Claude低风险冒烟：

```bash
python tests/smoke_agent_bridge.py
```

真实 Claude只能：

- 创建或更新 `.ai/BRIDGE_SMOKE_TEST.md`；
- 写入测试时间和模型执行成功说明；
- commit：`test: bridge smoke test`；
- push 当前 `feature/silent-learning-stabilization` 分支。

必须记录：

- Claude版本；
- 实际命令（不得含密钥）；
- 退出码；
- 真实输出结构的脱敏摘要；
- 冒烟提交完整 SHA；
- push确认；
- 是否出现权限提示或等待；
- CC Switch模型配置是否被正常继承（只能记录可安全确认的模型名称，不得记录密钥/Base URL凭据）。

## 回归测试

至少运行：

```bash
python -m pytest tests/test_agent_bridge.py -v
python tests/smoke_agent_bridge.py
```

不得修改、删除测试来制造通过。

## 允许修改

- `start_bridge.bat`
- `tools/agent_bridge/*`
- `tests/test_agent_bridge.py`
- `tests/smoke_agent_bridge.py`
- `.gitignore`
- `.ai/BRIDGE_DESIGN.md`
- `.ai/BRIDGE_SMOKE_TEST.md`
- `.ai/BRIDGE_RUN_REPORT.md`
- `.ai/ZCODE_REPORT.md`
- `.ai/TEST_RESULTS.md`
- `.ai/CURRENT_TASK.md`

## 禁止修改

- 热键、录音、ASR、纠错、注入、静默学习、Electron、进程管理等业务代码；
- `main`；
- `backup/*`；
- 任何凭据、个人配置、数据库、录音或日志；
- 不得安装或升级 Claude Code；
- 不得 force push、reset --hard、git clean；
- 不得开始下一项静默学习修复任务。

## 提交要求

修复提交建议：

```bash
git add start_bridge.bat tools/agent_bridge tests/test_agent_bridge.py tests/smoke_agent_bridge.py .gitignore .ai
git commit -m "fix: stabilize local Claude task bridge"
git push
```

真实冒烟允许产生独立提交：

```text
test: bridge smoke test
```

完成后将本任务标记为 DONE，并停止。
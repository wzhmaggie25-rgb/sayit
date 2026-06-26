# AGENTS.md — AI 工作协约

> 本文档定义了 AI (ZCode / ChatGPT / Cursor 等) 在此仓库中工作的**永久规则**。
> 每次开始工作前，AI 必须先读取本文档。

---

## 1. 每次开始工作前必须读取

1. `AGENTS.md`（本文件）
2. `.ai/PROJECT_STATE.md`
3. `.ai/CURRENT_TASK.md`

## 2. 每次完成任务后必须更新

1. `.ai/ZCODE_REPORT.md` — 记录本次 session 做了什么
2. `.ai/TEST_RESULTS.md` — 记录测试结果

## 3. ZCODE_REPORT 必须包含

- **接收到的任务** — 原始描述
- **实际修改的文件** — 变更摘要
- **根因判断** — 问题根因，或"新建文件，无根因"
- **实施内容** — 做了什么
- **执行过的命令** — 关键命令列表
- **测试结果** — 实际输出，或"未运行测试"
- **未解决的问题** — 遗留事项
- **风险** — 可能的影响
- **当前提交ID** — 本次 commit hash

## 4. 禁止行为

- ❌ 未运行测试时，不得在报告或 commit message 中写"已经修复"
- ❌ 不允许擅自重构任务以外的模块
- ❌ 不允许删除失败测试
- ❌ 不允许输出或提交 API Key、Token、配置文件、数据库、录音文件或完整个人日志

## 5. 涉密文件（禁止上传）

以下内容不得出现在任何 commit 中：

- `.env` / `.env.*`
- `config.json`
- `*.db` / `*.sqlite` / `*.sqlite3`
- `*.log` / `*.wav` / `*.mp3` / `*.pcm`
- 任何包含 API Key、Token、本地缓存的文件

## 6. 分支策略

- `backup/*` — 稳定备份，**禁止直接修改**
- `feature/*` — 功能开发分支
- `main` — 仅从 PR 合并，**禁止直接推送**

## 7. 跨 session 交接

当 ChatGPT 或另一个 AI 接替工作时：

1. **接替方**先读取 `AGENTS.md`、`.ai/PROJECT_STATE.md`、`.ai/CURRENT_TASK.md`
2. **移交方**更新 `.ai/ZCODE_REPORT.md` 和 `.ai/TEST_RESULTS.md`
3. **移交方**将未解决的问题写入 `.ai/CURRENT_TASK.md` 的"备注"部分

---

_最后更新：YYYY-MM-DD_
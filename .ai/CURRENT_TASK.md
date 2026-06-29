# Current Task

> 最后一次更新：2026-06-29

## 状态

**BLOCKED_DATA_SAFETY**

> 禁止合并、禁止重跑现有 88 项定向测试。先保护并核查真实数据库。

---

## 当前分支

只允许在以下安全分支处理：

```text
backup/hermes-silent-learning-recovery
```

正式分支禁止修改、合并或推送：

```text
feature/silent-learning-stabilization
```

---

## 必读

```text
.ai/ROUND9_5A_FINAL_INDEPENDENT_REVIEW.md
```

该文件是当前最高优先级审查结论。

---

## 已确认的阻断

### 1. 集成测试数据库隔离失败

`tests/test_silent_learning_integration.py` 打补丁的位置错误：

```python
patch.object(infrastructure.paths, "database_path", ...)
```

但 `infrastructure.database` 已经直接导入并绑定：

```python
from infrastructure.paths import database_path
```

因此测试中的 `Database()` 很可能仍使用：

```text
%APPDATA%/Sayit/sayit.db
```

同时测试执行 `hw.clear()`，可能清空了真实个人词典。

在完成数据库保护和只读核查前，禁止再次运行该测试。

### 2. 原始中文错词 BDD 未实现

Feature 仍要求：

```text
民天 → 明天 → 学习“明天”
```

当前实现会拒绝所有单个中文字符替换。

测试却把原场景改成：

```text
光明 → 黑暗
```

因此当前实现是“保守拒绝单字纠正”，不是已完成原始产品定义。

### 3. 报告存在错误安全声明

以下声明必须撤回并更正：

- 未读取或修改真实数据库/词典；
- 临时数据库隔离已经验证；
- 没有弱化原始测试场景。

---

## 当前唯一任务：数据库止损与只读核查

执行器建议：Claude Code，先保持 Plan Mode / 只读模式。

### 第一步：停止写入

不要运行测试，不要启动 SayIt，不要启动 Agent Bridge、Hermes、Codex 或 ZCode。

### 第二步：先复制备份，再检查

在打开 SQLite 之前，复制以下文件（如存在）：

```text
%APPDATA%\Sayit\sayit.db
%APPDATA%\Sayit\sayit.db-wal
%APPDATA%\Sayit\sayit.db-shm
```

复制到仓库外的新时间戳恢复目录。

禁止删除、移动、重命名原文件。

### 第三步：只检查副本

只用 SQLite read-only 模式检查副本。

仅报告：

- dictionary 行数；
- dictionary 中非核心词数量；
- 最早/最晚 added_at；
- history 行数；
- correction_rules 行数；
- 数据库及 WAL/SHM 文件时间；
- 是否发现旧 DB、bak、backup、hotwords.txt、hotwords.json。

禁止输出：

- 词典具体词语；
- 历史正文；
- API Key；
- 配置内容。

### 第四步：停止并报告

只读核查后停止，不修代码、不恢复数据、不运行测试，等待独立判断。

---

## 后续修复要求（尚未授权执行）

测试修复必须：

- patch `infrastructure.database.database_path`；
- 隔离真实 `ConfigStore`；
- 第一次写入前断言 `Database()._db_path` 等于临时路径；
- 真实 APPDATA 路径出现时立即失败；
- 每个测试使用独立临时数据库；
- 不依赖 `hw.clear()` 清理共享状态；
- 修正所有错误报告。

中文单字纠正必须明确二选一：

1. v1 保守策略：明确承认不学习单字修改；或
2. 获取真实用户编辑/选择边界，实现 `民天 → 明天` 而不猜邻字。

未经用户确认，不得擅自修改 Feature 契约。

---

## 禁止事项

- 不运行现有 88 项测试；
- 不合并或修改正式 feature 分支；
- 不创建 PR；
- 不执行 pull/rebase/cherry-pick/reset/force push/git clean；
- 不删除或修改真实数据库；
- 不清空词典；
- 不恢复数据；
- 不继续修改静默学习算法；
- 不将状态改为 DONE。

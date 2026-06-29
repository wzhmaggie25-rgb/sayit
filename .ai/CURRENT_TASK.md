# Current Task

> 最后一次更新：2026-06-29

## 状态

**HERMES_FIX_READY**

---

## 当前分支

只在以下安全分支继续：

```text
backup/hermes-silent-learning-recovery
```

当前独立审查基线：

```text
b2f6fce70fc2d375dd8c7fb5eee63e74b4a1bfa6
```

ChatGPT审查提交：

```text
84be7f11079f33e8e74816b0bd0c8b5d69876ee2
```

不要切回、不要覆盖、不要合并：

```text
feature/silent-learning-stabilization
```

---

## 必须阅读

```text
.ai/ROUND9_5A_SILENT_LEARNING_CONTRACT_TASK.md
.ai/ROUND9_5A_INDEPENDENT_REVIEW.md
```

后者是本轮最新独立审查，冲突时优先级最高。

---

## 本轮唯一目标

修正并证明完整链路：

```text
用户明确修改一个错词
→ 精确提取正确词
→ 写入个人词典
→ 同步到下一次ASR使用的热词context
```

继续保持：

- 不建立或应用全局错词替换规则；
- 不从legacy correction_rules自动晋升热词；
- 不删除用户已有规则和词典数据。

---

## 三个阻断必须全部修复

### 1. 禁止猜测中文相邻字符

当前 `_expand_corrected_term()` 会把单字纠错随意拼接右边或左边字符，可能学习成错误词，例如：

```text
天汽 → 天气，可能错误学习“气很”或“气好”
豆抱助手 → 豆包助手，可能错误学习“包助”
百练平台 → 百炼平台，可能错误学习“炼平”
```

必须：

- 删除这种相邻字符猜测；
- 单个CJK字符修改且无法证明完整词边界时，一律不学习；
- 返回明确原因，例如 `ambiguous_single_cjk`；
- 只有修改片段本身就是干净的2-8字中文词时才允许学习；
- 英文/中英混合词只能按确定的字母数字token边界扩展。

### 2. 必须验证真实词典与ASR同步

新增隔离集成测试，必须使用：

- 临时SQLite；
- 真实 `Database`；
- 真实 `HotwordsManager`；
- fake ASR cascade记录 `set_hotwords_context()` 调用；
- fake ConfigStore，禁止读取真实配置。

测试必须证明：

- 正确词只写入一行；
- 重复学习不产生重复行；
- 第一次写入后，传给ASR的context包含正确词；
- 不创建或修改correction_rules；
- 不访问真实数据库路径。

### 3. 下一次streaming必须拿到最新context

修正 `AsrCascade.create_streaming_session()`：

- 动态 `_streaming_context` 必须优先于启动时旧的 `aliyun.context`；
- 增加生产路径测试，证明启动后新增词能够进入下一次streaming session；
- 不修改ASR引擎选择、超时、fallback顺序和SDK生命周期。

---

## BDD + TDD要求

先补会失败的测试，再改实现。

必须新增并执行以下边界测试：

```text
天汽 → 天气：不得学习气很/气好
豆抱 → 豆包（位于“豆包助手”中）：不得学习包助
百练 → 百炼（位于“百炼平台”中）：不得学习炼平
单纯标点修改：不学习
单个中文插入/删除：不学习
完整2-8字中文词替换：允许学习
中文误识别改英文品牌名：允许学习并保留大小写
英文token内部纠正：只能学习完整token
```

Gherkin每个场景必须在自审报告中对应一个真实可执行的pytest node id。

禁止源码grep、注释断言和测试专用复制实现。

---

## 测试方式

- 只运行Round 9.5A定向测试；
- 测试必须由进程正常返回exit code 0，不能只打印pass后挂起；
- 不在Codex内置终端运行全量pytest；
- 暂不处理历史6个失败和全量pytest退出挂起，单独记录，不扩大本轮范围；
- 4个untracked pytest日志继续保持未提交。

---

## 执行器与安全

- 唯一执行器：Hermes；
- 不启动Codex；
- 不启动ZCode/Agent Bridge；
- 不终止任何无关Hermes进程；
- 不执行 `reset --hard`、`git clean`、force push；
- 不读取或修改真实数据库、词典、历史、音频、剪贴板、API Key；
- 不改悬浮窗、Native热键、注入器、AI、ASR超时、后端恢复。

---

## 完成要求

完成后：

- 更新 `.ai/ROUND9_5A_SELF_REVIEW.md`；
- 准确更新 `.ai/TEST_RESULTS.md` 和 `.ai/ZCODE_REPORT.md`，注明执行器为Hermes；
- 记录失败测试提交、实现提交和最终HEAD；
- 记录每条BDD对应的pytest node id；
- 记录准确pass/fail/skip数量和进程exit code；
- 将本文件状态改为 `BLOCKED_REVIEW`；
- 不得改为 `DONE`；
- 只推送 `backup/hermes-silent-learning-recovery`，不要推正式feature分支。

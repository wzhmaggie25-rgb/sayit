# Claude Code Long Task — SayIt 稳定化交付

> 日期：2026-06-27
> 执行器：本地 SayIt Agent Bridge → Claude Code CLI
> 目标：在一次自主长任务中，把 Typeless 风格结果卡片、真实注入状态、剪贴板保护和静默学习热词提升做到可进入用户实机验收。

## 一、唯一总目标

完成并交付以下闭环：

```text
语音识别成功
→ 当前有可编辑输入目标时可靠输入
→ 能 readback 时才标记 verified
→ 无法 readback 时明确 attempted_unverified，绝不盲目二次输入
→ 当前无可编辑目标时保留原剪贴板并显示大结果卡片
→ 用户点击复制后才写入剪贴板
→ 只有 verified_success 才启动静默学习
→ 同一局部纠错在两个不同 history 中重复后安全提升个人热词
```

本任务不是“让测试变绿”，而是让代码行为、状态、UI、历史和测试彼此一致。

## 二、必须先读

开始编码前依次阅读：

```text
AGENTS.md
.ai/PROJECT_STATE.md
.ai/CURRENT_TASK.md
.ai/ROUND5_CODE_REVIEW.md
.ai/CURRENT_TASK_OVERRIDE.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
.ai/ZCODE_REPORT.md
.ai/TEST_RESULTS.md
```

以 `.ai/ROUND5_CODE_REVIEW.md` 的问题清单为代码审查基线。

## 三、自主执行规则

1. 不向用户提问；小型实现取舍采用最保守、最不丢数据、最不重复输入的方案。
2. 只有遇到外部凭据缺失、硬件不可用、操作系统权限无法绕过等真正外部阻塞，才允许 `BLOCKED`。
3. 不得因为已有测试通过就宣布完成；必须增加能复现本轮缺陷的测试。
4. 不得删除、弱化或跳过失败测试。
5. 不得读取、输出或修改用户真实数据库、真实词典、历史、录音、完整日志、API key、token 或私人文本。
6. 不得修改 `main`、`backup/*`、稳定 tag，不得 force push、reset --hard、git clean。
7. 保留 RAltStopWatcher、keyboard helper ABI v3、AudioCapture 快速 stop 和现有 ASR/AI 配置。
8. 不引入大型前端依赖；结果卡片优先使用原生 HTML/CSS/JavaScript。
9. 每一阶段先写测试或复现脚本，再改实现，再跑相关测试。
10. 每个阶段完成并通过相关测试后做 checkpoint commit 并 push，避免长任务中断时丢失进度。

## 四、阶段任务

### Phase 0 — 基线与复现

- 确认当前分支为 `feature/silent-learning-stabilization`；
- 确认工作目录干净；
- 记录当前 HEAD；
- 运行现有全量测试；
- 运行 `node --check frontend/main.js`；
- 为以下已知缺陷增加失败测试/离线复现：
  - result-card 页面未加载 React；
  - 首次窗口 ready 前 payload 丢失；
  - paste shortcut 被直接标记 verified；
  - 空剪贴板未恢复为空；
  - 非文本/多格式剪贴板被破坏；
  - no_editable_target 错误启动 SilentMonitor；
  - lastTranscription 未渲染；
  - 两个不同 history 后没有提升个人热词。

不得在没有复现证据的情况下直接大改。

### Phase 1 — 结果卡片成为可靠的离线 UI

#### 架构

- 将 `frontend/ui/result-card.html` 改为原生 HTML/CSS/JavaScript；
- 不依赖 CDN、React、ReactDOM、远程字体或网络资源；
- 由 Electron 主进程保存：

```text
pendingResultCardPayload
pendingResultText
```

- 新窗口未 ready 时缓存 payload；
- `did-finish-load` 后发送最新 payload；
- 已 ready 时立即发送；
- 连续结果以最新 payload 为准；
- 关闭后清除 pending payload。

#### 可信 IPC

- renderer 不向 REST 接口提交任意文字；
- preload 只暴露有限动作，例如：

```text
show payload listener
copyPendingResult()
closeResultCard()
```

- 主进程使用 Electron `clipboard.writeText(pendingResultText)`；
- 删除或停用 `/api/result-card/copy`、`/api/result-card/close` 的任意文本接口；
- 本机网页不能通过开放 CORS endpoint 任意覆盖剪贴板。

#### UI

必须包含：

1. 第一层：最近转录信息；
2. 第二层：本次 final_text 预览；
3. 长内容安全省略或滚动；
4. 下方复制按钮；
5. 右上角关闭按钮；
6. 点击复制后按钮左侧绿色勾；
7. 短暂反馈后关闭；
8. 点击关闭不修改剪贴板；
9. 窗口默认不抢焦点，但按钮必须可点击。

增加离线 smoke test，至少验证脚本无未定义全局、首次 payload 不丢、按钮动作和关闭流程。

完成后 checkpoint commit + push。

### Phase 2 — 剪贴板保护成为真实契约

实现明确的 snapshot 类型：

```text
EMPTY
TEXT(value)
UNSUPPORTED_OR_MULTIFORMAT
READ_FAILED
```

规则：

- `EMPTY`：临时粘贴后恢复为空；
- `TEXT(value)`：恢复原文本；
- `UNSUPPORTED_OR_MULTIFORMAT`：禁止使用会清空剪贴板的 paste 路径；
- `READ_FAILED`：禁止覆盖剪贴板；
- 图片、文件列表、HTML、RTF、自定义格式、多格式内容不得被静默破坏；
- 日志只能记录格式编号/名称和状态，不记录内容；
- 正常输入结束后 final_text 不留在剪贴板；
- no_editable_target 时不自动写入剪贴板；
- 只有用户点击结果卡片复制时才把 final_text 写入剪贴板；
- `copy_result_to_clipboard` 若保留，默认 false，不能影响上述默认行为。

测试必须覆盖：空、纯文本、图片/文件/HTML/多格式、读取失败、粘贴异常。

完成后 checkpoint commit + push。

### Phase 3 — 真实输入目标与注入状态机

#### 当前目标规则

- 注入时重新评估当前 focused editable control；
- 用户已经把光标移出输入框时，不得强抢焦点恢复录音开始时的旧输入框；
- 录音开始时捕获的 target 仅用于诊断、同一控件识别和 readback anchors，不作为强制恢复依据；
- 如果当前焦点在有效可编辑控件，可向当前控件输入；
- 当前无可编辑控件，返回 `no_editable_target`。

#### 可编辑判断

- Win32 跨进程 focus 使用 `GetGUIThreadInfo` 或等价可靠方法，不依赖本线程 `GetFocus()`；
- UIA ValuePattern 必须检查 `CurrentIsReadOnly == false`；
- TextPattern 单独存在不能证明可编辑；
- 结合 ControlType、IsKeyboardFocusable、ValuePattern/TextPattern、Win32 Edit/RichEdit；
- known app strategy 只决定注入方式，不能证明当前有输入焦点。

#### readback

动作前后捕获目标快照：

- Win32 Edit/RichEdit：文本、选择区、光标前后 anchor；
- UIA ValuePattern：Value；
- 可访问 TextPattern：文本范围；
- 只在 final_text 出现在预期插入位置或内容变化与预期一致时 `verified=True`。

状态至少包括：

```text
verified_success
attempted_unverified
no_editable_target
injection_failed
recognition_failed
```

规则：

- Ctrl+V、SendInput、SetValue 调用成功不等于 verified；
- 已发送动作但目标不可 readback：`attempted_unverified`；
- `attempted_unverified` 后不得再执行另一条可能重复输入的路径；
- 明确 readback 未变化：`injection_failed`；
- 无 final_text：`recognition_failed`；
- `ok` 与 `verified` 分离；
- `INJECTION_DONE`、历史和日志应携带结构化状态，不再只靠 bool 表达语义。

对于 `attempted_unverified`：

- 不自动复制；
- 保留用户剪贴板；
- 不启动 SilentMonitor；
- 用中性结果卡片告知“无法确认是否已输入”，允许用户主动复制；
- 不显示“识别失败”。

测试必须覆盖：

- shortcut sent + readback 正确；
- shortcut sent + readback 无变化；
- shortcut sent + 不可 readback；
- 不可 readback 不再走 SendInput；
- no target；
- read-only target；
- 1000+ 中文字符；
- Electron/终端/微信类不可验证策略不重复输入。

完成后 checkpoint commit + push。

### Phase 4 — Pipeline、历史与 SilentMonitor

- `verified_success + target_verified`：历史标记成功，允许启动 SilentMonitor；
- `attempted_unverified`：历史标记识别成功但未验证，不启动 SilentMonitor；
- `no_editable_target`：历史标记识别成功但无目标，显示结果卡片，不启动 SilentMonitor；
- `injection_failed`：历史标记识别成功但注入失败，显示结果卡片，不启动 SilentMonitor；
- `recognition_failed`：只有无 final_text 时使用；
- no target 不能使用旧 `last_target_hwnd` 启动监控；
- UI 小浮窗不能把注入问题显示成“识别失败”；
- 结果卡片出现时，小浮窗应正确退出，不重复弹状态。

增加 pipeline/event/history 测试。

完成后 checkpoint commit + push。

### Phase 5 — 重复纠错提升个人热词

完成本轮不得再次推迟：

1. 同一 `(pattern, replacement)` 在两个不同 history ID 中出现后才有资格提升；
2. 同一 history 重复扫描不增加证据；
3. 只有 replacement 进入个人词典，pattern 永不进入；
4. 同一个 pattern 多个 replacement 分别累计；
5. 平票、接近竞争或没有明显唯一赢家时不提升；
6. 只有唯一赢家达到阈值并明显领先才提升；
7. 整句、追加句子、多处修改、删除、整段重写、过长短语不提升；
8. 单次最多提升一个词；
9. 重复扫描和重复启动幂等；
10. 提升后调用 HotwordsManager 同步 ASR；
11. 不清洗、不覆盖用户已有词典；
12. 数据迁移向后兼容；来源字段可记录 `silent_learning`，但不得破坏旧数据。

至少增加测试：

- 两个不同 history 后提升；
- 同 history 不提升；
- pattern 不入词典；
- 冲突 replacement 不提升；
- 唯一赢家明显领先后提升；
- 整句/追加/多处编辑不提升；
- 提升后 ASR sync；
- 重复扫描幂等。

完成后 checkpoint commit + push。

### Phase 6 — 全量回归与自主代码审查

必须运行：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
```

还要运行新增的 result-card 离线 smoke test和所有定向测试。

然后重新逐项阅读：

```text
.ai/ROUND5_CODE_REVIEW.md
.ai/CLAUDE_LONG_TASK.md
```

创建：

```text
.ai/CC_SELF_REVIEW.md
```

对每一项写：

```text
PASS / FAIL
实现位置
对应测试
剩余风险
```

只要任何 P0、验收标准或必需测试是 FAIL，就继续修复，不能结束任务。

## 五、提交与报告

### Checkpoint

每个 Phase 完成后：

- 只提交该阶段相关文件；
- 运行阶段测试；
- commit；
- push 当前 feature 分支。

禁止把明显失败或无法启动的中间状态标记为 DONE。

### 最终报告

更新：

```text
.ai/ZCODE_REPORT.md
.ai/TEST_RESULTS.md
.ai/PROJECT_STATE.md
.ai/CC_SELF_REVIEW.md
```

`.ai/ZCODE_REPORT.md` 必须包含：

- 根因；
- 每阶段修改；
- 执行过的命令；
- 精确测试数量；
- 未解决问题；
- 风险；
- 至少一个真实 `implementation_commit` SHA。

最终：

1. 将 `.ai/CURRENT_TASK.md` 状态改成 `DONE`；
2. commit；
3. push；
4. 输出最终 JSON，包含最终远端 HEAD SHA。

如果遇到真正外部阻塞：

1. 保留已通过测试的 checkpoint commits；
2. 写清楚已完成/未完成和精确阻塞；
3. 状态改为 `BLOCKED`；
4. commit 并 push；
5. 输出 `ok: false` JSON。

## 六、最终验收门禁

只有同时满足以下条件才允许 DONE：

- 结果卡片离线可运行，首次 payload 不丢；
- 复制走可信 Electron IPC；
- 原剪贴板为空后恢复为空；
- 非文本/多格式剪贴板不被破坏；
- verified 只来自目标 readback；
- attempted_unverified 不重复注入；
- no editable target 不强抢旧输入框；
- no target/unverified/failed 不启动 SilentMonitor；
- 结果卡片符合用户验证的两层文字、复制、绿色勾、右上角关闭；
- 两个不同 history 的同一局部纠错可安全提升个人热词；
- 冲突、整句和重复扫描不会误提升；
- RAlt、音频、ASR/AI 和现有功能回归通过；
- 全量测试通过；
- 自审全部 P0 为 PASS；
- 报告包含真实 commit SHA；
- 已 push 当前 feature 分支。

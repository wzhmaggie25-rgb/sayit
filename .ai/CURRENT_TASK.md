# Current Task

> 最后一次更新：2026-06-26

## 状态

**ZCODE_READY**

> 本轮继续由 ZCode GUI 可视化执行。不要由 Agent Bridge / Claude Code 后台接管。

## 任务名称

采用 Typeless 风格的无损注入降级体验，修复剪贴板污染与注入假验证，并完成重复纠错安全提升为个人热词。

## 基线与分支

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 代码基线 HEAD：`8bbb05bff949ffa29a0ef16569f04a5790ccac44`
- 本任务说明提交：上一轮 `f8afbf240069ac7b82c2dc1079358e4a42f0776a`，本文件是其产品体验补充并覆盖冲突描述
- 稳定备份：commit `0d69a98`，tag `local-working-2026-06-25`
- 本地目录：`D:\code\sayit_zcode`
- 执行方式：ZCode GUI

开始前确认目录、分支和最新 HEAD。不得修改 main、backup 分支和稳定 tag；不得 force push、reset --hard、git clean；不得读取、复制、清洗或修改用户真实数据库、真实词典、历史、录音、完整日志和私人文本。

---

## 用户产品决策：采用 Typeless 风格的注入失败降级

用户实际使用 Typeless 后认为其注入失败处理体验较好，SayIt 应参考其核心体验。

这里的“Typeless 风格”定义为：

1. 语音识别和 AI 整理已经成功时，即使自动注入失败，也绝不能显示为“识别失败”；
2. final_text 必须完整保留，不能丢字；
3. 自动注入失败或无法确认时，立即将 final_text 放入剪贴板；
4. 悬浮窗给出简短、可执行的提示：

   `未自动输入，已复制，按 Ctrl+V 粘贴`

5. 用户无需进入历史页寻找文字；
6. 失败提示不应弹出阻塞式对话框，不抢焦点，不中断当前工作；
7. 用户按 Ctrl+V 后即可继续；
8. 历史页仍保存完整结果，并明确记录“识别成功、注入失败”；
9. 悬浮提示可点击再次复制，或至少保证点击不会清除尚未粘贴的结果；
10. 提示在合理时间后自动隐藏，但不能在隐藏时清空剪贴板；
11. 不要增加复杂的重试弹窗或要求用户做多步操作；
12. 不照搬无法确认的 Typeless 内部实现，只复刻用户认可的无损、低打扰降级体验。

### 成功与失败状态必须分离

状态至少区分：

- `recognition_success + injection_verified`
- `recognition_success + injection_unverified`
- `recognition_success + injection_failed + clipboard_fallback`
- `recognition_failed`

不得把第三种状态合并为第四种。

---

## A. 剪贴板正确策略

### A1. 成功输入时默认不污染剪贴板

- 剪贴板只是兼容性注入的临时通道，不是每次识别的永久输出；
- verified success 后恢复用户注入前的剪贴板；
- 原剪贴板为空时恢复为空；
- 原剪贴板为文本时精确恢复；
- 原剪贴板为图片、文件、HTML、RTF 或多格式时，尽可能完整恢复；
- 不能完整保护非文本格式时，不得无提示覆盖，报告中明确限制；
- 可增加 `copy_result_to_clipboard: false`，默认 false；只有用户主动开启才在成功后保留 final_text。

### A2. 失败或不可确认时采用 Typeless 风格 fallback

以下情况 final_text 必须留在剪贴板：

- 目标窗口或输入控件丢失；
- 所有注入路径失败；
- 发送粘贴后目标内容验证失败；
- 目标不可读回，无法确认是否插入且产品策略选择安全降级；
- 注入过程中发生异常。

此时：

- 不恢复旧剪贴板；
- `clipboard_preserved=True`；
- 显示 `未自动输入，已复制，按 Ctrl+V 粘贴`；
- 历史标记识别成功但注入失败；
- 不得自动再用另一条可能重复输入的路径盲目注入。

### A3. 删除错误的 clipboard-consumed 判断

当前“Ctrl+V 成功后目标会消费或改变剪贴板”的假设错误。普通 Windows 粘贴不会清空剪贴板。

必须删除：

- `post_clip != final_text` 即 verified success；
- “目标程序消费剪贴板”的注释；
- 测试中人为让目标修改剪贴板来证明成功；
- 任何仅凭剪贴板内容变化设置 `verified=True` 的逻辑。

---

## B. 正确验证注入

### B1. 捕获目标输入控件

录音开始时尽量保存：

- 顶层 hwnd、pid、proc、class、title；
- focused child hwnd；
- Win32 Edit/RichEdit 当前文本和选择区；
- UIA AutomationId、ControlType、ValuePattern/TextPattern 信息；
- 可访问的输入框内容、光标前后 anchor。

### B2. 从目标控件 readback 验证

verified 只能来自目标自身的内容变化，例如：

- Win32 Edit/RichEdit WM_GETTEXT readback；
- UIA ValuePattern/TextPattern readback；
- 可访问浏览器/Electron 字段的前后内容对比；
- final_text 出现在预期插入位置且前后 anchor 正确。

以下均不能单独视为 verified：

- SendInput 返回成功数量；
- Ctrl+V 已发送；
- 顶层窗口在前台；
- 剪贴板仍存在或发生变化。

### B3. 不可验证应用

对微信、Notion、部分 Electron/WebView、终端等不可稳定 readback 的应用：

- `ok` 与 `verified` 分离；
- 可以返回 `ok=True, verified=False, reason=unverifiable_target`；
- 采用保守策略时保留 final_text 在剪贴板；
- UI 显示 `已尝试输入，文字同时保留在剪贴板`；
- 不要再自动逐字 SendInput，避免双份文字；
- 不得写成 verified success。

### B4. InjectionResult

至少包含：

```text
ok
verified
method
reason
clipboard_preserved
clipboard_restored
target_restored
target_verified
```

`INJECTION_DONE` 应传结构化数据，不再只传 bool。

历史至少区分：

- verified success；
- probable/unverified success；
- failed + clipboard fallback；
- recognition failure。

日志只写脱敏原因码，不记录用户全文。

---

## C. 悬浮窗体验

### C1. 成功

- verified success：显示 `完成`；
- 默认恢复原剪贴板；
- 正常自动隐藏。

### C2. 尝试成功但不可验证

- 显示 `已尝试输入，文字已保留` 或同等简短文案；
- final_text 保留在剪贴板；
- 不显示红色“识别失败”；
- 点击提示可再次复制；
- 不抢焦点。

### C3. 确认注入失败

- 显示 `未自动输入，已复制，按 Ctrl+V 粘贴`；
- final_text 留在剪贴板；
- 提示保持足够时间供用户看清；
- 自动隐藏后剪贴板仍保持 final_text；
- 用户无需去历史页面复制；
- 识别结果仍正常保存历史。

### C4. 真正识别失败

只有 ASR/AI 无法产出 final_text 时，才显示 `识别失败`。

---

## D. 完成重复纠错提升为个人热词

上一轮只完成中文局部 replacement 提取及 `(pattern, replacement)` 规则合并。本轮完成：

1. 第一次明确局部纠错：建立或更新 correction rule；
2. 同一 `(pattern, replacement)` 在两个不同 history 中重复后，才提升 replacement 到个人词典；
3. 同一 history 重复扫描不得重复计数；
4. 只有 replacement 进入词典，pattern 永不进入；
5. 提升后调用 HotwordsManager 同步 ASR；
6. 同一个 pattern 有多个 replacement 时分别累计；
7. 平票或接近冲突不提升；
8. 只有唯一赢家达到阈值且明显领先才提升；
9. 整句、追加句子、多处修改、删除、整段重写、长短语仍不得入词典；
10. 单次最多提升一个词；
11. 不删除或清洗用户已有词典；
12. 最好记录词条来源 `manual / silent_learning / built_in`，迁移必须向后兼容和幂等。

---

## E. 保留 RAlt 修复

上一轮已有：

- ABI v3 native event ring；
- RAltStopWatcher；
- AudioCapture 快速 stop；
- recording_stopping 前端反馈。

本轮不得因注入和学习返工删除或弱化这些修复。运行全部相关回归。最终仍需用户做长语音 ≥15 秒、第二次 RAlt 真实停止验证。

---

## 必须修正的测试

### Clipboard / Typeless fallback

- 原剪贴板为空，verified success 后恢复为空；
- 原剪贴板为文本，success 后精确恢复；
- 非文本/多格式剪贴板不被静默永久覆盖；
- failed 后 final_text 留在剪贴板；
- unverified 路径按策略保留 final_text；
- `copy_result_to_clipboard=false` 默认不留下结果；
- 配置 true 时成功后留下结果；
- 删除全部“目标会消费剪贴板”的模拟测试；
- fallback UI 文案和状态不等于 recognition_failed；
- fallback 提示隐藏后剪贴板仍保留；
- 点击 fallback 提示可再次复制且不抢焦点。

### Injection verification

- Win32 Edit readback；
- UIA readback；
- Ctrl+V 已发送但目标无变化 -> failed；
- 目标变化正确 -> verified success；
- 无 readback -> verified=False；
- unverified 不触发第二次盲目 SendInput；
- 1000+ 中文字符长文本；
- history、事件、UI 与 InjectionResult 一致。

### Hotword promotion

- 同一 pair 两个不同 history 后提升；
- 同 history 重复不提升；
- 冲突 replacement 不提升；
- 唯一赢家明显领先后提升；
- 原错误词不入词典；
- 整句/追加/多处编辑不入词典；
- 提升后 ASR hotword sync；
- 重复扫描幂等。

### Regression

- RAlt watcher；
- keyboard helper；
- orchestrator；
- audio capture；
- pipeline；
- silent monitor；
- dictionary/correction；
- injector/context helper；
- frontend event mapping。

---

## 允许修改

- `infrastructure/injector.py`
- `infrastructure/context_helper_client.py`
- `infrastructure/focus_context.py`
- `application/pipeline.py`
- `application/eventbus.py`
- `frontend/main.js`
- `frontend/ui/float.html`
- `infrastructure/config_store.py`
- `server.py`
- `domain/correction.py`
- `infrastructure/silent_monitor.py`
- `infrastructure/database.py`
- `infrastructure/hotwords_manager.py`
- 直接相关测试
- `.ai/CURRENT_TASK.md`
- `.ai/ZCODE_REPORT.md`
- `.ai/TEST_RESULTS.md`
- `.ai/PROJECT_STATE.md`
- `CHANGELOG.md`

除非修复回归所必需，不修改 native RAlt 核心、ASR/AI 供应商、采样率、增益算法、Agent Bridge、main/backup/tag、用户真实数据。

---

## 验收标准

1. 成功输入默认不污染剪贴板；
2. 失败/不可确认时 final_text 保留且无需去历史页；
3. fallback UI 按 Typeless 风格低打扰提示 Ctrl+V；
4. 注入失败不再显示为识别失败；
5. 删除 clipboard-consumed 假验证；
6. verified 只来自目标控件 readback；
7. 不可验证明确标记，不产生重复输入；
8. 历史正确区分识别和注入状态；
9. 重复纠错可安全提升热词；
10. 冲突和整句不误提升；
11. RAlt、音频和现有功能回归通过；
12. 报告使用真实 GitHub 提交 SHA；
13. 提交并推送 feature 分支。

建议提交信息：

```text
fix: add Typeless-style injection fallback and safe hotword promotion
```

完成后状态改为：

**BLOCKED_USER_VALIDATION**

并提供四项人工验证：

1. 长语音第二次 RAlt；
2. verified success 后原剪贴板保持；
3. 注入失败后看到 Typeless 风格提示并可直接 Ctrl+V；
4. 同一正确词在不同输入中修正两次后进入个人热词。

# Current Task

> 最后一次更新：2026-06-26

## 状态

**ZCODE_READY**

> 本轮继续由 ZCode GUI 可视化执行。不要由 Agent Bridge / Claude Code 后台接管。

## 任务名称

修复剪贴板污染与注入假验证，完成重复纠错提升为个人热词，并保留上一轮 RAlt 可靠停止方案等待实机验收。

## 基线与分支

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 本任务基线 HEAD：`8bbb05bff949ffa29a0ef16569f04a5790ccac44`
- 稳定备份：commit `0d69a98`，tag `local-working-2026-06-25`
- 本地目录：`D:\code\sayit_zcode`
- 执行方式：ZCode GUI，可视化开发

开始前必须确认当前目录、分支和 HEAD；不修改 main/backup/tag；不 force push/reset --hard/git clean；不读取或修改用户真实数据库、词典、历史、录音、完整日志和私人文本。

---

## 用户最新反馈与产品决策

### 1. 当前每次识别后的文字都会留在系统剪贴板

用户观察到：SayIt 每次完成语音识别后，最终文字会自动成为系统剪贴板内容。

产品决策：

- **默认情况下，成功注入不应改变用户原来的剪贴板。**
- 剪贴板只是兼容性注入的临时通道，不应成为每次识别的永久输出。
- **只有注入失败或无法可靠确认注入时，才把 final_text 留在剪贴板作为保险，并明确提示用户。**
- 可以保留一个显式设置 `copy_result_to_clipboard`，默认 `false`；用户主动开启后才在成功时复制结果。

### 2. 上一轮存在明确实现错误

当前 `Injector.paste()` 使用错误假设：

> 目标程序成功粘贴后，会“消费/改变”系统剪贴板；如果剪贴板仍是 final_text，就判定粘贴失败。

普通 Windows Ctrl+V 不会消费或清空剪贴板。粘贴成功后剪贴板仍保持原值是正常行为。因此：

- 当前 clipboard verification 逻辑无效；
- 对普通应用会产生大量假失败；
- 测试中模拟“目标程序改变剪贴板”不符合真实 Windows 行为；
- `verified=True` 不能来自剪贴板内容变化。

### 3. 当前备份只保存文本，无法保护图片/文件等剪贴板内容

`_clipboard_get_text()` 只能读取文本。如果用户剪贴板原来是图片、文件列表、富文本或其他格式，会得到 `None`；成功路径只在 `backup is not None` 时恢复，因此 final_text 会永久留在剪贴板，原内容可能丢失。

### 4. 热词功能仍未完成

上一轮只完成：

- 中文整句中的局部纠错提取；
- correction_rules 按 `(pattern, replacement)` 合并。

尚未完成：

- 同一明确纠错跨不同 history 重复后，自动提升 replacement 到个人词典/热词；
- 冲突 replacement 的安全处理；
- 用户词典页能够看到提升结果。

### 5. 上一轮报告提交号错误

`.ai/CURRENT_TASK.md` / 报告中写了不存在的提交 `1a9d24d...`。实际 GitHub HEAD 是：

`8bbb05bff949ffa29a0ef16569f04a5790ccac44`

本轮必须修正报告，不得再记录不存在的提交。

---

## 总体目标

1. 成功输入后，默认完整保留用户原剪贴板；
2. 注入失败时，final_text 留在剪贴板并有明确 UI 提示；
3. 删除“剪贴板内容改变=粘贴成功”的错误验证；
4. 使用目标输入控件的前后内容/选择区/UIA/Win32 readback 来验证注入；
5. 无法验证的路径必须标记 `verified=False`，不能谎称已验证；
6. 历史记录区分 verified success、probable/unverified、failure；
7. 完成重复纠错安全提升为个人热词；
8. 不重新引入整句误入词典；
9. 保留上一轮 RAltStopWatcher、快速 AudioCapture.stop 和 native diagnostics；除非测试发现回归，不要重写 RAlt 架构；
10. 更新真实提交号、报告和测试结果。

---

## A. 剪贴板策略

### A1. 成功时默认恢复原剪贴板

实现明确策略：

- 录音/注入前捕获剪贴板快照；
- clipboard paste 只临时放入 final_text；
- 成功后恢复原剪贴板；
- 原剪贴板为空时，成功后恢复为空，而不是留下 final_text；
- 原剪贴板是普通文本时精确恢复；
- 原剪贴板是图片、文件、HTML、RTF 或多格式内容时，尽可能完整恢复全部格式。

优先使用可靠的 Windows/OLE clipboard snapshot/restore。若完整多格式恢复在本轮无法安全实现：

- 不得声称已经完整保护；
- 对不能备份的剪贴板格式，优先使用非 clipboard 注入路径；
- 必须避免无提示覆盖；
- 报告中明确支持范围和限制。

### A2. 失败时保留 final_text

只有以下情况才默认让 final_text 成为当前剪贴板：

- 目标窗口丢失；
- 所有注入路径失败；
- 发送了粘贴但目标内容验证失败；
- 目标内容不可验证且产品选择按失败处理。

失败 UI 必须显示类似：

`未能输入，文字已复制`

不要只显示模糊的“识别失败”，因为 ASR 已成功。

### A3. 可选“成功后也复制”设置

新增或补充配置：

```text
copy_result_to_clipboard: false
```

- 默认 false；
- true 时成功输入后 final_text 可留在剪贴板；
- 不要求本轮做复杂设置页面，可先支持 config/API 并保持向后兼容；
- 默认行为必须是不污染剪贴板。

---

## B. 正确的注入验证

### B1. 删除错误的 clipboard-consumed heuristic

删除：

- `post_clip != text` 即成功；
- 目标程序会消费剪贴板的注释、测试和逻辑；
- 任何基于剪贴板内容是否改变的 `verified=True`。

Windows 粘贴不会改变剪贴板，不能以此验证。

### B2. 基于目标输入控件验证

录音开始时捕获尽可能稳定的目标：

- 顶层 hwnd/pid/proc/class/title；
- 实际 focused child hwnd；
- Win32 Edit/RichEdit 内容、选择区；
- UIA AutomationId/ControlType/Value/TextPattern 信息；
- 浏览器/Electron 可访问字段的内容、光标前后 anchor。

注入后用目标自身 readback 判断：

- final_text 是否出现在预期插入位置；
- 前后 anchor 是否保持；
- 不是仅仅“窗口仍在前台”；
- 不是仅仅“SendInput 返回了数量”；
- 不是读取剪贴板。

对 Win32 Edit/RichEdit 和 UIA ValuePattern 路径必须做到真实 readback。

### B3. 无法 readback 的应用

对于微信、Notion、部分 Electron/WebView/终端等无法稳定读取字段的应用：

- `ok` 与 `verified` 必须分开；
- 可以返回 `ok=True, verified=False, method=clipboard, reason=unverifiable_target`，但历史和 UI 不得写成“已验证成功”；
- 产品默认优先保证内容不丢失：根据应用策略决定是否保留 final_text 在剪贴板；
- 若保留 final_text，提示“已尝试输入，文字同时保留在剪贴板”；
- 不要把 unverified 自动等同 verified；
- 不要无条件再逐字 SendInput，避免重复输入。

### B4. InjectionResult 与历史

完善结构：

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

历史 `pasted/status/error_msg/debug_info` 必须真实反映：

- verified success；
- unverified probable success；
- failed + clipboard fallback。

建议加入脱敏原因码，不记录 final_text。

### B5. 事件/UI

`INJECTION_DONE` 不应只传 bool。至少传：

- ok；
- verified；
- reason；
- clipboard_preserved。

悬浮窗区分：

- 完成；
- 已尝试输入；
- 未能输入，文字已复制。

---

## C. 重复纠错提升为个人热词

### C1. 两阶段学习

- 第一次明确局部纠错：建立/更新 correction rule；
- 同一 `(pattern, replacement)` 在不同 history 中重复达到阈值后，提升 replacement 到个人词典；
- 建议阈值为 2 次不同 history；
- 同一 history 重复扫描不能重复计数；
- 只有 replacement 进入词典，pattern 永不进入；
- 提升后调用 HotwordsManager 同步到 ASR。

### C2. 冲突处理

同一个 pattern 对应多个 replacement 时：

- 分别累计；
- 有平票或接近冲突时不提升；
- 只有唯一赢家达到阈值且明显领先时提升；
- 不错误强化旧 replacement；
- 规则应用也不能随机选择。

### C3. 安全门禁继续有效

- 中文局部 replacement 必须短、连续、anchor 稳定；
- 追加句子、整段重写、多处改动、删除、粘贴段落不提升；
- 完整句子和普通长短语不能进入词典；
- 单次最多一个词；
- 不清理用户已有词典。

### C4. 来源与幂等

个人词典条目最好能够区分：

- manual；
- silent_learning；
- built_in/core。

如需 schema migration，必须向后兼容、可重复运行、不改写现有词内容。若本轮不做 UI 来源展示，至少数据库/API 能保留来源。

---

## D. RAlt 保持与最终验收

上一轮已经新增：

- ABI v3 native event ring；
- RAltStopWatcher；
- AudioCapture 快速 stop；
- `recording_stopping` 前端反馈。

本轮要求：

- 运行现有相关测试，防止剪贴板/学习修改破坏 RAlt；
- 不因其他模块返工删除 watcher；
- 最终报告提供真实启动步骤；
- 最终仍标记 `BLOCKED_USER_VALIDATION`，等待用户长录音 ≥15 秒后验证第二次 RAlt；
- 第三次 RAlt 应当是在上一轮完全结束后开始新录音，而不是用于停止上一轮。

---

## 必须增加/修正的测试

### Clipboard

- 原剪贴板为空，verified success 后恢复为空；
- 原剪贴板为文本，success 后精确恢复；
- 原剪贴板为非文本/多格式时不被静默覆盖；
- failure 后 final_text 留在剪贴板；
- `copy_result_to_clipboard=false` 默认不留下结果；
- 配置 true 时成功后留下结果；
- 删除所有“paste 会消费 clipboard”的模拟测试。

### Injection verification

- Win32 Edit readback 成功；
- UIA readback 成功；
- Ctrl+V 已发送但目标没有变化 -> failed；
- Ctrl+V 成功且目标变化 -> verified success；
- 无 readback 应用 -> verified=False，不谎称 verified；
- 不因 unverified 再次 SendInput 导致重复文本；
- 1000+ 中文字符长文本；
- history 和事件字段与 InjectionResult 一致。

### Hotword promotion

- 同一 pair 两个不同 history 后提升；
- 同 history 重复不提升；
- pattern 相同、replacement 冲突不提升；
- 唯一赢家明显领先后提升；
- 原错误词不入词典；
- 整句/追加/多处编辑不入词典；
- 提升后 ASR hotword sync 被调用；
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

只有同时满足以下条件才能提交：

1. 删除错误的 clipboard consumed 验证；
2. 成功注入默认恢复原剪贴板；
3. 空剪贴板成功后仍为空；
4. 非文本剪贴板不会被无提示永久覆盖；
5. 失败才默认保留 final_text；
6. UI 明确提示失败已复制；
7. verified 只来自目标字段 readback；
8. unverifiable 明确标记，不谎称验证；
9. 不产生二次注入或重复文字；
10. 重复纠错跨不同 history 后可安全提升热词；
11. 冲突 replacement 不误提升；
12. 整句误入词典不回归；
13. RAlt/音频相关回归测试通过；
14. 全量相关测试通过；
15. 报告使用真实 GitHub 提交 SHA；
16. 提交并推送 feature 分支。

建议最终提交信息：

```text
fix: preserve clipboard and complete safe hotword learning
```

完成后状态改为：

**BLOCKED_USER_VALIDATION**

并提供：

- 长语音第二次 RAlt 验收步骤；
- 成功注入剪贴板保护验证；
- 失败后剪贴板 fallback 验证；
- 重复修改两次后热词提升验证。

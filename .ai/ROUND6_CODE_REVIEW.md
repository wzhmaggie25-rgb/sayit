# Round 6 Code Review — 阻止实机验收

> 审查日期：2026-06-27
> 审查基线：`35219427ab4c6d82b0644022bbb790ca65056ca3`
> Claude 实现提交：`9876412cc97e91ee859abfab8d78d354de21b5a2`
> 当前远端 HEAD：`ae0dba8ce60d8599e1eb42ac78c08b11d6fce24b`
> 结论：**未通过代码审查，不得进入用户实机验收。**

## 总结

Round 6 确实完成了大量有效工作：

- result card 已脱离 React/CDN；
- pending payload 已缓存；
- arbitrary-text REST copy 已失效；
- clipboard snapshot 四态已建立；
- attempted_unverified 与 SilentMonitor 门禁已加入；
- distinct history IDs 与 promotion 表结构已加入；
- 新增了较多测试。

但是当前实现仍存在会造成：

- 抢回旧焦点；
- 覆盖输入框已有内容；
- UIA 已经改写后再次粘贴，造成重复或覆盖；
- 假 verified；
- 剪贴板恢复失败却宣称已恢复；
- 单次纠错直接进入个人词典，绕过“两次不同 history”门禁；
- 同一 history 重复提升 correction rule 置信度；
- Bridge 将真实 DONE 错改为 BLOCKED；

的阻塞缺陷。

---

## P0-1：仍然强制恢复录音开始时的旧窗口

`Injector._inject_locked()` 在存在 captured target 时调用 `_focus_window(target.hwnd)`，最多尝试三次；`_focus_window()` 还会执行：

- BringWindowToTop；
- SetForegroundWindow；
- SetFocus；
- SwitchToThisWindow；
- 临时 TOPMOST。

这与已确认产品行为直接冲突：

> 注入时应重新检查当前 focused editable control；用户已把光标移出输入框时，不得抢回录音开始时的旧输入框。

### 必须修改

- captured target 只用于诊断、同一控件 identity 和 readback anchor；
- 注入时重新获取当前 focused editable control；
- 当前焦点不是 captured control 时，不恢复旧窗口；
- 当前焦点是新的有效输入控件时，输入到当前控件；
- 当前无有效输入控件时返回 `no_editable_target` 并显示结果卡片。

---

## P0-2：Win32 child route 使用 WM_SETTEXT，会覆盖整个输入框

`_inject_win32_child_edit()` 找到第一个 Edit/RichEdit child 后调用 `WM_SETTEXT(text)`，随后要求完整字段内容等于 text。

这不是“在光标处输入”，而是“把整个控件替换成 final_text”。如果输入框原本有内容，会造成数据丢失；找到的第一个 child 也不一定是当前 focused control，可能是搜索框或其他编辑框。

### 必须修改

- 禁止用 `WM_SETTEXT` 作为通用注入路径；
- 只对明确 focused control 使用 selection-aware insertion；
- 无法确认 selection/caret 时，宁可 `attempted_unverified` 或结果卡片，不得覆盖整个字段；
- 增加“已有前后文 + 光标中间插入”的测试。

---

## P0-3：UIA SetValue 是替换，不是光标插入；失败后还会继续粘贴

`_inject_uia()` 调用 `ValuePattern.SetValue(text)`。这会设置整个 Value，而不是在 caret 位置插入。

更危险的是：SetValue 可能已经成功改变目标，但只要 readback 超时/不匹配，函数返回 False，外层继续 clipboard paste。这样会产生：

- 整个字段先被替换；
- 再粘贴一次；
- 文本重复或原内容丢失。

此外，TextPattern fallback 调用 `DocumentRange.Select()`，随后外层 clipboard paste 可能直接替换整篇文档。

### 必须修改

- 禁止将 ValuePattern.SetValue 作为一般文本插入；
- 禁止 `DocumentRange.Select()` 后再走通用 paste；
- 任何可能已修改目标的 UIA 动作，只要不能证明结果，就返回 `attempted_unverified`，不得再走第二条输入路径；
- 使用 selection/caret-aware UIA TextPattern2、Win32 selection 或安全 keyboard/clipboard route；
- 增加“UIA action dispatched but readback unavailable must not paste again”测试。

---

## P0-4：UIA readback 存在确定性假阳性

`_verify_uia_readback()` 当前判断：

```python
if expected in read_text or read_text in expected:
    return True
```

问题：

- `read_text == ""` 时，空字符串永远属于 expected，会错误 verified；
- 只读回 expected 的任意短片段也会 verified；
- 没有比较 pre/post；
- 没有验证插入位置、anchor 或 caret。

Win32 `_verify_target_text()` 也只检查 `expected in post`。若 expected 原本已经存在，目标发生了无关变化，也可能被错误 verified。

### 必须修改

verified 必须来自 pre/post diff 与预期插入一致：

- post 必须能由 pre 在确定位置插入 expected 得到；或
- 使用 selection/caret anchors 验证；
- empty、partial、pre-existing expected、unrelated change 均不得 verified。

---

## P0-5：可靠 readback 未变化时状态错误

任务契约是：

> 目标可可靠 readback 且内容未变化 → `injection_failed`。

当前 clipboard path 将 `verdict == "unchanged"` 返回 `attempted_unverified`，而 SendInput path 返回 `injection_failed`，语义不一致。测试还把错误行为固化成预期。

### 必须修改

- reliable pre/post identical → `injection_failed`；
- no readback → `attempted_unverified`；
- 两者测试必须分开。

---

## P0-6：剪贴板恢复失败仍宣称 preserved/restored

`paste()` 调用 `restore_snapshot(snap)` 后，即使返回 False，只记录 warning，仍返回 `(True, snap.kind)`。

随后 `_ok()` / `_attempted_unverified()` 固定写入：

```text
clipboard_preserved=True
clipboard_restored=True
```

若恢复失败，final_text 可能仍留在剪贴板，状态和事实相反。

### 必须修改

- paste 返回结构化结果：shortcut_sent、snapshot_kind、restore_ok；
- restore 失败必须重试有限次数；
- 最终失败时明确 `clipboard_preserved=False`、`clipboard_restored=False`；
- 不得宣称默认契约已满足；
- 增加 EMPTY/TEXT restore failure 测试。

---

## P0-7：attempted_unverified 结果卡片没有风险提示

Pipeline 对 attempted_unverified 与 no target 使用相同 `RESULT_CARD_SHOW(final_text, last_transcription)`；result card 没有 state/message 字段。

用户无法知道文字“可能已经输入”，点击复制后很容易再粘贴一次造成重复。

### 必须修改

Result card payload 增加 mode/state：

- `no_editable_target`：未找到输入位置；
- `attempted_unverified`：可能已经输入，请先检查，避免重复粘贴；
- `injection_failed`：确定未输入；

renderer 显示清晰但中性的提示。复制仍只由用户主动点击。

---

## P0-8：单次纠错仍直接加入个人词典，绕过两次 history 门禁

`SilentMonitor._learn()` 在 merge rules 后先调用：

```python
added_terms = self._auto_add_dictionary_terms(original_text, edited_text)
```

`_auto_add_dictionary_terms()` 会直接调用 `HotwordsManager.add_word(term)`。

这意味着只发生一次用户编辑，replacement 就可能进入个人词典；后面的 `decide_promotion()` 两次 distinct history 门禁被绕过。

### 必须修改

- 静默学习自动进入个人词典必须只有一个入口：promotion engine；
- 删除或禁用单次 edit 的 `_auto_add_dictionary_terms()` 自动添加；
- 手动用户添加词典不受影响；
- 增加“第一次纠错不入词典，第二个不同 history 后才入词典”端到端测试。

---

## P0-9：同一 history 重复扫描仍增加 correction rule 置信度和 match_count

`Database.merge_rules()` 虽然 dedupe `source_history_ids`，但无论 new_hid 是否已经存在，都会执行：

```text
confidence += 0.15
match_count += 1
```

同一个 history 被重复处理三次，可让 correction rule 达到自动应用阈值，违反“同一 history 不重复计数”。

### 必须修改

- 只有新增 distinct history id 时才能增加 evidence、confidence、match_count；
- 同 history 重放完全幂等；
- 增加 match_count/confidence 不变测试。

---

## P1-1：焦点/可编辑判断仍未完成上一轮要求

当前仍存在：

- 使用 thread-local `GetFocus()` 做跨进程判断；
- ValuePattern 不检查 `CurrentIsReadOnly`；
- TextPattern 存在即判 editable；
- UIA 无 pattern 时过早返回 no_editable，后续 child/strategy fallback 逻辑不可达；
- known app strategy 可被当作 editable 证明。

### 必须修改

- 使用 `GetGUIThreadInfo` 或可靠 UIA focused element；
- ValuePattern 必须 `CurrentIsReadOnly == false`；
- TextPattern 单独存在不是 editable 证明；
- known app 只决定策略，不证明当前焦点可输入。

---

## P1-2：Hotword 冲突判断不够保守

`decide_promotion()` 在分组冲突前先过滤 evidence < 2 的 candidate，因此 2 vs 1 会被当作“无竞争者”直接提升。

此外 already_promoted competitor 被过滤；以后另一个 replacement 达标时，可能再次为同一 pattern 提升第二个冲突热词。

### 必须修改

- 冲突判断必须考虑所有 replacement evidence，包括 1 次证据与 already-promoted 记录；
- 2 vs 1 属于接近竞争，不提升；
- 建议：无竞争时 2 次可提升；有竞争时 winner 至少领先 2 个 distinct histories；
- 同一 pattern 已提升后，后续冲突 replacement 默认锁定不再自动提升，除非有明确撤销/替换流程。

---

## P1-3：promotion 写入失败仍永久 mark promoted

`_maybe_promote_hotword()` 不论 HotwordsManager/DB add 是否成功，都会 `mark_rule_promoted()`。

临时 DB 或 sync 失败后，该候选永远不重试。

### 必须修改

- 只有词已确认存在于 dictionary 且同步动作成功/已排队成功后才 mark promoted；
- 已存在词可视为成功；
- 临时失败保留待重试状态。

---

## P1-4：结构化状态没有贯穿事件总线

内部有 InjectionResult.state，但 Pipeline 仍发：

```python
Events.INJECTION_DONE, True/False
```

server WebSocket 也只发送 `{ok: bool}`。下游无法区分 no target / unverified / failed。

### 必须修改

- INJECTION_DONE payload 携带 state、verified、method、reason、clipboard_restored；
- 保留兼容 ok 字段；
- 前端和历史以 state 为主。

---

## P1-5：测试存在“镜像实现”而非真实集成

`PipelineSilentMonitorGatingTests` 没有运行 RecordingPipeline，只在测试里重新写了一遍 `can_learn` 布尔表达式，因此实现改坏后测试仍可能通过。

缺少关键测试：

- stale captured target 不抢焦点；
- 新 focused target 被使用；
- WM_SETTEXT/SetValue 不覆盖已有内容；
- UIA action 后不可验证不再 fallback；
- empty/partial/pre-existing expected 不得 verified；
- clipboard restore failure；
- attempted_unverified card warning；
- 首次 edit 不入词典；
- duplicate history 不增加 match_count/confidence；
- 2 vs 1 conflict 不提升；
- actual pipeline 不启动 SilentMonitor。

---

## P1-6：Bridge 完成判定会覆盖真实 DONE

Claude 已完成代码、测试、提交并把 CURRENT_TASK 改成 DONE，但最终 stdout 没有可解析 JSON。Bridge 只因 parse failure 就执行 `commit_and_push_blocked()`，把 DONE 覆盖为 BLOCKED。

### 必须修改 Bridge

- config 用 `utf-8-sig` 兼容 BOM；
- parser 支持 noisy stdout / JSON envelope；
- Claude exit 0 + CURRENT_TASK 已为 DONE + working tree clean 时，JSON parse failure 不得覆盖 DONE；
- `commit_and_push_blocked()` 发现 CURRENT_TASK 已 DONE 时必须拒绝覆盖；
- 保存/记录 raw stdout 摘要以便诊断；
- 增加自动化测试。

---

## 审查结论

当前状态：

```text
ROUND6_REVIEW_FAILED
```

暂时不要启动 SayIt 做实机验收。

下一轮只做：

> 注入非破坏性、真实 readback、当前焦点行为、剪贴板恢复事实一致、两次 history 热词门禁，以及 Bridge 完成判定可靠化。

完成后再进入用户实机验收。
# Round 7 Code Review — 未通过

> 审查日期：2026-06-27
> 审查对象：`a0e5ae667a23ecd3336c48637d42f7aad8e76254`
> 结论：**暂时不得进入用户实机验收。**

Round 7 有明显进展：

- 当前注入流程已不再主动恢复 captured target；
- result card 已增加 state/message；
- clipboard restore 结果开始向 InjectionResult 传播；
- 单次 edit 直接入词典的绕行入口已删除；
- structured INJECTION_DONE 已接入 Pipeline/WebSocket；
- Bridge 已支持 BOM 和更多 stdout JSON 格式。

但自审报告与实际代码存在多处不一致，仍有会覆盖用户文字、误判 verified、污染学习证据和错误覆盖任务状态的阻塞问题。

---

## P0-1：UIA 仍然使用 ValuePattern.SetValue 覆盖整个输入框

`infrastructure/injector.py::_inject_uia()` 仍直接执行：

```python
vp.SetValue(text)
```

这不是“在光标处插入”，而是设置整个控件 Value。输入框原有内容可能被全部替换。

Round 7 任务明确要求：

```text
禁止通用 ValuePattern.SetValue(final_text)
```

自审也承认 SetValue 仍是替换，却错误标记 PASS。

### 必须修复

- 从一般注入路径完全删除/禁用 ValuePattern.SetValue；
- 只允许 selection/caret-aware insertion；
- 无可靠 selection/caret API 时走安全 clipboard/SendInput；
- 动作不可验证时 attempted_unverified，不得再尝试第二条输入路径。

---

## P0-2：UIA verified 仍然只是 substring，没有 pre/post 证据

`_verify_uia_readback()` 当前仍使用：

```python
if expected and expected in read_text:
    return True
```

没有 pre snapshot、selection、caret 或 anchor。

如果 expected 原本就在输入框中，或 SetValue 已把整字段覆盖成 expected，会直接被标记 verified_success。

### 必须修复

- UIA readback 必须采集动作前后完整值/selection/caret；
- verified 必须证明本次插入而不是“字段中包含 expected”；
- 没有 pre 证据时不能 verified。

---

## P0-3：Win32 通用 WM_SETTEXT 仍存在

`_inject_win32_child_edit()` 仍保留 WM_SETTEXT，只在 length > 0 时拒绝。

问题：

- 任务要求禁止通用 WM_SETTEXT；
- `_find_child_edit()` 只取第一个 Edit/RichEdit child，不证明它是当前 focused control；
- 某些非标准控件可能错误报告 length=0；
- 空字段也不应依赖替换整个控件的 API 作为常规插入策略。

### 必须修复

- 删除/停用通用 WM_SETTEXT 路径；
- 只对明确 focused Win32 control 使用 EM_GETSEL/EM_REPLACESEL 或等价 selection-aware insertion；
- 找不到 focused control 时不得使用第一个 child 猜测。

---

## P0-4：可编辑性判断仍是 Round 6 旧实现

`_assess_target_editability()` 仍然：

- 使用跨进程不可靠的 thread-local `GetFocus()`；
- ValuePattern 存在即判 editable，不检查 `CurrentIsReadOnly`；
- TextPattern 存在即判 editable；
- UIA element 无 pattern 时立即 no_editable，后续 child fallback 不可达；
- 未使用 GetGUIThreadInfo；
- unknown 仍可能继续向 0 hwnd/错误目标发送输入。

### 必须修复

- 使用 GetGUIThreadInfo 或可靠 UIA focused element；
- ValuePattern 必须检查 read-only=false；
- TextPattern 单独存在不能证明 editable；
- unknown 不得盲目发送输入；保守返回 no_editable_target。

---

## P0-5：Win32 readback 在无 pre 时仍使用弱 substring

`_verify_target_text()` 在 `pre_text is None` 时仍：

```python
return "verified" if expected and expected in post else "no_readback"
```

这违反“没有 pre 证据不能 verified”。expected 可能原本已存在，或 readback 来自错误 child。

### 必须修复

- pre 不可读 → no_readback / attempted_unverified；
- 不得使用 substring fallback；
- readback 必须绑定当前 focused control identity。

---

## P0-6：同一 history 重放仍增加 confidence 和 match_count

`infrastructure/database.py::merge_rules()` 实际代码没有按自审所说修改。

即使 `new_hid` 已经在 `source_history_ids` 中，仍无条件执行：

```python
new_conf = min(0.95, existing['confidence'] + 0.15)
new_count = existing['match_count'] + 1
```

所以同一个 history 重复扫描仍会让 correction rule 达到自动应用阈值。

现有测试只检查 source_history_ids 不增长，没有检查 confidence/match_count。

### 必须修复

- 只有新增 distinct history id 时才增加 confidence/match_count；
- 同 history 重放完全幂等；
- 增加真实 DB 测试，断言三个字段都不变。

---

## P0-7：clipboard restore 失败在 injection_failed 分支仍会被错误宣称 preserved

clipboard path 得到 `restore_ok=False` 后：

- verified 和 attempted_unverified 分支会传播 restore_ok；
- 但 reliable unchanged 分支调用 `_fail("paste_target_unchanged")`；
- `_fail()` 不接收 restore_ok，会把 `clipboard_preserved` 按 config 默认为 True。

因此恢复失败 + 目标未变化时，结果仍可能错误宣称剪贴板已保留。

### 必须修复

- `_fail()` 接收并传播 restore_ok；
- 任何 paste 已覆盖 clipboard 后的退出路径都必须保留事实状态；
- shortcut dispatch exception + restore fail 时不得继续 SendInput。

---

## P1-1：promotion fallback 可能绕过 ASR sync

`_maybe_promote_hotword()` 在 HotwordsManager.add_word 失败后直接 fallback 到 `db.add_dictionary_word()`。

如果 HotwordsManager 存在但同步失败，DB fallback 可能写入词典并 mark promoted，却没有完成 ASR sync。

### 必须修复

- 区分“词已存在”和“同步失败”；
- 只有 dictionary 已确认存在且 ASR sync 成功/已可靠排队后 mark promoted；
- 临时失败不 mark，允许重试。

---

## P1-2：Bridge v0.2.1 未支持 BLOCKED_USER_VALIDATION 成功终态

Bridge parse fallback 只把 `DONE` 视为成功；`commit_and_push_blocked()` 也只保护 DONE。

本项目长任务的正确成功终态是：

```text
BLOCKED_USER_VALIDATION
```

若 Claude 正确完成并设置该状态，但最终 JSON 丢失，Bridge 仍会把它覆盖成 BLOCKED。

此外 `_has_new_commits_since()` 虽已实现，但 parse fallback 实际没有使用，和注释/任务要求不一致。

### 必须修复

- 定义成功终态集合：DONE、BLOCKED_USER_VALIDATION；
- 两者都不得被 commit_and_push_blocked 覆盖；
- fallback 必须同时验证：exit=0、tree clean、HEAD 相对 task SHA 有新提交；
- 增加对应测试。

---

## P1-3：结果卡片 IPC 没有校验 sender

`result-card:copy-pending` 和 `result-card:close` handler 没有检查事件 sender 是否为 resultCardWin.webContents。

preload 虽然不传任意 text，但其他 renderer 仍可 invoke 同一 IPC channel。

### 必须修复

- handler 接收 event；
- 校验 event.sender.id === resultCardWin.webContents.id；
- 非 result card sender 拒绝。

---

## 测试审查问题

当前 302 tests 通过不能证明上述行为正确，原因包括：

- 自审明确承认 SetValue 仍替换整个字段，却将其标记 PASS；
- duplicate history 测试只检查 ID 数组，不检查 confidence/match_count；
- Bridge 测试没有 BLOCKED_USER_VALIDATION；
- UIA tests 主要 mock tri-state，没有验证不覆盖已有文本；
- `_assess_target_editability()` 实际没有完成 GetGUIThreadInfo/read-only 修复。

---

## 结论

当前状态：

```text
ROUND7_REVIEW_FAILED
```

不要启动 SayIt 进行正式实机验收。

下一轮必须只做剩余阻塞修复，不扩展功能。
# Round 5 代码审查：Typeless 结果卡片与剪贴板

> 日期：2026-06-27
> 审查提交：`bff31037d6992b421c60f91d41a515e1565a16ce`
> 结论：**CHANGES_REQUIRED — 不得进入用户人工验收**

## 总结

本轮方向正确：删除了 clipboard-consumed heuristic、默认关闭自动复制、增加了结果卡片和状态路由。

但代码仍有多个阻塞问题，会导致：

- 结果卡片首次打开为空或直接报错；
- Ctrl+V 已发送仍被标记为 verified success；
- 原剪贴板为空时语音结果残留；
- 非文本/多格式剪贴板被破坏；
- 无输入目标时仍可能启动静默学习并监控错误窗口；
- 用户要求的重复纠错提升个人热词没有实现。

因此 `.ai/CURRENT_TASK.md` 不应处于 `BLOCKED_USER_VALIDATION`，必须回到 `ZCODE_READY` 修复。

---

## P0-1：结果卡片 HTML 无法运行

`frontend/ui/result-card.html` 使用：

```js
const {useState,useEffect,useCallback,createElement:h}=React;
ReactDOM.createRoot(...)
```

但页面没有加载 React/ReactDOM，`frontend/preload.js` 也没有注入它们。

结果：页面加载时会发生 `ReferenceError: React is not defined`，卡片无法正常渲染。

### 修复要求

优先将结果卡片改成**原生 HTML/CSS/JavaScript**，不要依赖 CDN 或 React。

必须增加 Electron/HTML smoke test，至少验证：

- 页面脚本无未定义全局；
- 显示函数存在；
- 复制和关闭按钮可绑定；
- 页面离线可运行。

---

## P0-2：首次 `result_card_show` payload 会丢失

`frontend/main.js` 当前顺序：

```js
createResultCardWindow();
pushToResultCard(...);
```

而 `pushToResultCard()` 在 `resultCardReady === false` 时直接 return。

新窗口的 `did-finish-load` 是异步事件，因此第一次显示时 payload 大概率在页面 ready 前被丢弃，之后不会重发。

### 修复要求

维护可信的主进程 pending payload：

```text
pendingResultCardPayload = { finalText, lastTranscription }
```

- 如果窗口尚未 ready：保存 payload；
- `did-finish-load` 后主动发送最新 pending payload；
- 如果窗口已 ready：立即发送；
- 连续两次结果时以最新 payload 为准；
- 关闭后清除 pending payload。

增加测试覆盖“首次创建窗口 + 异步 ready”场景。

---

## P0-3：注入仍然是假验证

`Injector.paste()` 的新语义是：

> 只要发送了 Ctrl+V 就返回 True。

但 `_inject_locked()` 看到 True 后立即：

```python
return _ok("clipboard", verified=True, ...)
```

没有任何目标控件 readback。

因此“Ctrl+V 已发送”仍被错误标记为 `verified_success`，与任务要求完全冲突。

### 修复要求

在任何注入动作前后捕获目标控件快照：

- Win32 Edit/RichEdit：文本、选择区、anchor；
- UIA ValuePattern：Value；
- 可访问 TextPattern：文本范围；
- 只在 final_text 出现在预期位置或目标内容发生符合预期的变化时，设置 `verified=True`。

必须区分：

```text
verified_success
attempted_unverified
no_editable_target
injection_failed
recognition_failed
```

规则：

- `Ctrl+V` / `SendInput` 已发送但无法 readback：`attempted_unverified`；
- 不得标成 verified；
- 对可能已成功但无法验证的路径，不再盲目执行第二条输入路径，避免重复文字；
- 只有 readback 明确未变化时才进入 confirmed injection failure。

增加测试：

- shortcut sent + target unchanged -> failed；
- shortcut sent + target contains expected text -> verified success；
- shortcut sent + no readback -> attempted_unverified；
- attempted_unverified 不触发 SendInput 二次注入。

---

## P0-4：空剪贴板没有恢复为空

当前：

```python
backup = _clipboard_get_text()
...
if backup is not None:
    _clipboard_set_text(backup)
else:
    # no restore
```

当原剪贴板为空或无法读取时，临时写入的 final_text 会继续留在剪贴板。

现有测试甚至把该错误行为写成“无需恢复”。

### 修复要求

建立明确的 clipboard snapshot 状态：

```text
EMPTY
TEXT(value)
UNSUPPORTED_OR_MULTIFORMAT
READ_FAILED
```

- `EMPTY`：粘贴后调用 Win32 `EmptyClipboard()` 恢复为空；
- `TEXT(value)`：精确恢复；
- `UNSUPPORTED_OR_MULTIFORMAT`：如果不能完整快照/恢复，**禁止使用 clipboard 注入路径**，改用可验证的 UIA/SendInput；仍不能安全输入则显示结果卡片；
- `READ_FAILED`：禁止覆盖剪贴板，跳过 clipboard 路径。

删除/改写 `test_paste_empty_backup`，必须断言最终剪贴板恢复为空。

---

## P0-5：非文本/多格式剪贴板仍会被永久破坏

当前 `_clipboard_get_text()` 只保存 Unicode text；`_clipboard_set_text()` 会 `EmptyClipboard()`，图片、文件列表、HTML、RTF 等格式全部丢失。

这不符合“原剪贴板不被自动复制污染”的产品承诺。

### 修复要求

本轮不强求实现所有 Windows clipboard format 的完整克隆，但必须做到安全：

- 注入前枚举剪贴板格式；
- 只有 EMPTY 或可安全恢复的 TEXT_ONLY 才允许 clipboard paste；
- 检测到图片、文件、HTML、RTF、多个格式或未知格式时，跳过 clipboard 注入；
- 不得静默清空这些格式；
- 日志只记录格式编号/名称，不记录内容。

增加空、纯文本、图片/文件/HTML/多格式的单元测试或 Win32 fixture 测试。

---

## P0-6：结果卡片 UI 与已验证的 Typeless 行为不一致

当前卡片：

- 只显示静态标题“最后一次识别”和 final_text；
- `lastTranscription` state 被保存但根本没有渲染；
- 关闭按钮在底部，不在右上角；
- 报告却声称已实现两层信息。

### 修复要求

卡片至少包括：

1. 第一层：最近转录信息；
2. 第二层：本次 final_text 预览；
3. 长文字安全省略或滚动；
4. 下方复制按钮；
5. 右上角关闭按钮；
6. 点击复制后按钮左侧绿色勾；
7. 短暂反馈后窗口关闭；
8. 点击关闭不改变剪贴板。

不得把没有使用的 `lastTranscription` 参数写成“已实现”。

---

## P0-7：无输入目标时错误启动 SilentMonitor

Pipeline 把 `no_editable_target` 设置为 `ok=True`，随后使用：

```python
if ok and silent_learning_enabled and injector.last_target_hwnd:
    silent_monitor.start(...)
```

因此没有注入任何文字时，也可能对旧窗口或非输入窗口启动静默监控，产生错误学习。

### 修复要求

SilentMonitor 只能在以下条件同时满足时启动：

```text
inject_result.state == verified_success
AND inject_result.target_verified == True
AND 实际目标控件标识有效
```

`no_editable_target`、`attempted_unverified`、`injection_failed` 均不得启动静默学习。

增加对应 pipeline 测试。

---

## P1-1：焦点/可编辑判断可能误判

问题包括：

- `GetFocus()` 只返回调用线程队列的 focus，跨进程通常为 0；
- UIA `TextPattern` 存在并不代表可编辑，许多只读文本也支持；
- UIA 没有 pattern 时立即返回 `no_editable`，后面的 known app strategy 和 child edit fallback 不会执行；
- 代码仍优先恢复录音开始时的旧 target，可能违背用户已经把光标移出输入框的意图。

### 修复要求

- 使用 UIA focused element + ControlType + `IsKeyboardFocusable`；
- ValuePattern 必须检查 `CurrentIsReadOnly == false`；
- TextPattern 不能单独证明可编辑；
- Win32 focus 使用 `GetGUIThreadInfo` 或正确的目标线程 focus；
- 在注入时重新评估当前 focused editable control；
- 用户已将光标移出输入框时，不强抢焦点恢复旧输入框；应进入 `no_editable_target` 卡片；
- known app strategy 只能决定尝试方式，不能证明当前真的有输入焦点。

---

## P1-2：结果卡片复制接口不应接受任意文本

当前 renderer 向开放的本地 REST endpoint 提交 `{text}`，而服务端 CORS 为 `*`。本机网页可以请求该 endpoint 修改用户剪贴板。

### 修复要求

改成 Electron IPC：

- 主进程保存 `pendingResultText`；
- preload 仅暴露 `copyPendingResult()` 和 `closeResultCard()`；
- renderer 不把文本传回；
- main process 使用 Electron `clipboard.writeText(pendingResultText)`；
- 删除 `/api/result-card/copy` 和 `/api/result-card/close`，或至少不得接受任意 text；
- 复制完成后 main 通知 renderer 显示绿色勾并关闭。

---

## P1-3：任务未完整执行

ZCode 报告明确写明：

> Hotword promotion 尚未实现，推迟到下次迭代。

但 `.ai/CURRENT_TASK.md` 的任务名称和验收标准明确要求本轮完成；不允许自行降级或宣布完成。

### 修复要求

完成重复纠错提升个人热词：

- 同一 `(pattern, replacement)` 在两个不同 history 后提升；
- 同一 history 不重复计数；
- 只有 replacement 入词典；
- 冲突/平票/接近竞争不提升；
- 整句、追加、多处编辑、长短语不提升；
- 单次最多一个；
- 幂等；
- 提升后调用 HotwordsManager 同步 ASR；
- 不修改或清洗用户真实词典。

---

## P1-4：报告未填写真实 commit SHA

`.ai/ZCODE_REPORT.md` 仍写：

```text
（待 commit 后更新）
```

必须在最终报告中填写真实完整 SHA，并保证远端分支 HEAD 与报告一致。

---

## 必须执行的验证

### Python

```text
python -m pytest tests/ -v --timeout=30
```

### Frontend

- `node --check frontend/main.js`
- 对 result-card 页面执行离线 smoke test；
- 验证首次窗口创建不会丢 payload；
- 验证复制、绿色勾、关闭；
- 验证关闭不改剪贴板；
- 验证窗口不抢焦点且按钮可以点击。

### 实机前置检查

只有代码审查通过后，才让用户测试：

1. 正常输入框注入且原剪贴板保持；
2. 原剪贴板为空后仍为空；
3. 复制图片/文件后语音输入不会破坏原剪贴板；
4. 光标移出输入框后出现大卡片；
5. 不点击复制时 Ctrl+V 仍为旧剪贴板；
6. 点击复制后绿色勾、窗口消失、Ctrl+V 为 final_text；
7. 两个不同 history 的同一纠错提升个人热词；
8. 长语音第二次 RAlt 正常停止。

## 完成状态

修复完成、测试通过、报告包含真实 SHA、commit 并 push 后，才改为：

```text
BLOCKED_USER_VALIDATION
```

当前必须保持：

```text
ZCODE_READY
```

# Round 9.2 P0 Runtime Bug Review

> 日期：2026-06-28
> 结论：**P0_BUG_CONFIRMED**
> 用户现象：右 Alt开始/停止后状态混乱，长期停留“思考中”；后台仍在识别或处理；悬浮条不消失；文字未注入；结果卡片为空。

## 总结

当前不是单一 UI 问题，而是四个生产缺陷串联：

```text
Alt停止
→ Pipeline进入ASR/AI阶段
→ 流式ASR收尾可能永久阻塞，或任一未捕获异常终止Pipeline
→ Orchestrator只写日志，不发送终态
→ Float永远停在STOPPING/“思考中”
→ 未到达注入
```

另一条路径：

```text
真实输入框被误判为no_editable_target
→ RESULT_CARD_SHOW创建窗口
→ PIPELINE_DONE立刻清空pending payload
→ result-card renderer稍后加载
→ 卡片为空
```

当前版本不得继续用户验收、不得合并main、不得创建发布分支。

---

## P0-1 Pipeline未捕获异常不会通知前端终止

`application/orchestrator.py::_pipeline_wrapper()` 当前：

```python
try:
    _my_pipeline.run(...)
except Exception as e:
    logger.error("[orchestrator] pipeline crashed: %s", e)
finally:
    ... release mutex ...
```

问题：

- 只记录日志；
- 不emit `PIPELINE_ERROR`；
- 不emit明确的terminal/session结束事件；
- Float已经进入STOPPING后无法收到DONE/ERROR；
- 前端永久显示“思考中”；
- 用户不知道文本是否还可能注入，不能安全重试。

任何下列异常都能触发：

```text
db.get_rules / update_rules_apply_counts
streaming finish
batch ASR
history save
未知第三方SDK异常
事件处理之外的运行错误
```

这是用户现象的直接结构性原因。

---

## P0-2 Streaming ASR finish存在无界阻塞

`infrastructure/asr_streaming.py::finish()` 当前第一步：

```python
self._audio_queue.put(None)
```

这是阻塞式put，没有timeout。

若：

- send worker因SDK错误已经退出；
- send_audio_frame永久卡住；
- audio queue已经满；

则没有线程继续消费queue，`put(None)`会永久等待。后面的worker join、recognition.stop和45秒deadline根本不会执行。

结果：

- Pipeline永久停在TRANSCRIBING；
- UI永久停在“思考中”；
- 没有ASR结果；
- 不会注入；
- 不会弹出有效结果。

此外当前Pipeline调用：

```python
streaming_session.finish(timeout=max(45.0, seconds * 0.35))
```

即使没有永久阻塞，也会至少等待45秒，再进入batch fallback；用户会认为软件卡死。

---

## P0-3 Result card first-open race会清空文字

事件顺序：

```text
RESULT_CARD_SHOW
PIPELINE_DONE
```

main process在`RESULT_CARD_SHOW`中保存：

```text
pendingResultCardPayload
pendingResultText
pendingSessionId
```

result-card BrowserWindow首次创建需要异步加载；正常依赖`did-finish-load → flushPendingResultCardPayload()`。

但`PIPELINE_DONE`当前立即清空同session：

```js
pendingResultCardPayload = null
pendingResultText = ''
pendingSessionId = ''
```

若renderer尚未加载完成，flush时已经没有payload，所以窗口显示为空，复制按钮也无内容。

`error`事件也有同类清空风险。

这与用户报告“文字窗口是空的”完全一致。

---

## P0-4 真实输入框被误判为no_editable_target

`Injector._assess_target_editability(target)`：

- 参数接收了录音开始时的target，但实现完全不使用该target；
- 只认Win32 Edit/RichEdit；
- UIA只认ValuePattern且非只读；
- TextPattern-only直接判定`no_editable`；
- 随后`_inject_locked()`立即返回`no_editable_target`，不会进入clipboard/SendInput策略。

大量真实可编辑控件属于：

```text
Chrome contenteditable
Obsidian CodeMirror
微信/飞书自绘输入框
Electron富文本编辑器
```

这些可能只有TextPattern/Document或不稳定UIA模式，但原本应该使用已配置的clipboard策略。

结果：

- 用户明明有光标，仍判定无输入目标；
- 文字不注入；
- 错误弹结果卡片；
- 再叠加P0-3，卡片还是空的。

这违反用户明确要求：

> 只有输入框真正丢失焦点、且没有输入任何文字时才弹结果卡片。

---

## P0-5 own-window资格参数被硬编码

Pipeline调用生产资格函数时：

```python
target_is_sayit_window=False
```

没有从真实foreground/target计算。生产函数虽然存在，但第四个门禁没有真实数据。

---

## P1-1 缺少端到端terminal状态契约

当前不同路径可能发：

```text
PIPELINE_DONE
PIPELINE_ERROR
RECORDING_ERROR
AI_ERROR
```

但没有一个强制保证“每个session恰好一个terminal事件”的契约。

建议建立：

```text
pipeline_terminal
- session_id
- outcome: success / no_target / attempted_unverified / failed / aborted
- final_text_available
- stage
- reason_code
```

前端只以terminal事件结束“思考中”，并设置最大等待保护。

---

## P1-2 ASR fallback总等待过长

最坏路径可能包括：

```text
streaming finish ≥45s
DashScope batch 15s
Volcengine 30s
本地模型加载/推理
AI 25s
```

即使每层最终返回，用户也可能等待很久。需要全局ASR预算，而不是每层各自叠加。

---

## P1-3 当前自动测试没有覆盖真实失败组合

需要新增端到端/生产路径测试：

1. streaming worker已退出 + queue满，finish不能阻塞；
2. Pipeline任意stage抛异常，前端收到terminal error并复位；
3. `RESULT_CARD_SHOW → PIPELINE_DONE → did-finish-load`，文字仍存在；
4. Chrome/Obsidian/微信类contenteditable目标不被误判为无目标；
5. 真正桌面无焦点才显示结果卡片；
6. 一个session只能有一个terminal事件；
7. terminal后Float在有限时间内消失/复位；
8. 不重复注入。

---

## 当前结论

```text
Round 9.1 用户验收：FAIL
当前严重度：P0
可合并main：否
可进入Release Foundation：否
```

下一步执行：

```text
.ai/ROUND9_2_P0_FIX_TASK.md
```

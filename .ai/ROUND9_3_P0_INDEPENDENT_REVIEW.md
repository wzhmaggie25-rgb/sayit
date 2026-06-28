# Round 9.3 Independent Review — Round 9.2 P0 修复复核

> 日期：2026-06-28
> 审查基线：`a5912b67abdf78d762a104e7964e1fbadeb5aa82`
> 分支：`feature/silent-learning-stabilization`
> 结论：**P0_BLOCKERS_REMAIN — 暂停用户实机验收**

## 总结

Round 9.2 修复了部分原始故障，但尚未真正满足“Alt → 录音 → ASR → AI → 注入 → 唯一终态”的生产契约。

当前至少存在 4 个 P0 阻塞问题，并有若干 P1 契约/测试缺口。不得开始用户实机验收，不得进入安装包、更新、登录、订阅或场景化写作。

## P0-1 前端 watchdog 生命周期错误，长录音必然误报

位置：`frontend/main.js`

当前在 `recording_started` 时立即调用 `startSessionWatchdog(activeSessionId)`，固定 120 秒后强制退出并清空结果卡片 payload。

故障链：

```text
开始录音
→ watchdog 同时开始计时
→ 用户正常录音超过 2 分钟（计划中的 5 分钟测试必现）
→ watchdog 把仍在录音的正常 session 判为异常
→ Float 显示错误并清空 pending result payload
→ 后端仍继续录音/处理，前后端状态再次分裂
```

要求：watchdog 只能在 `recording_stopping` 后启动；录音阶段不得计入“思考中”预算；所有 terminal outcome 都必须取消 watchdog 并结束视觉等待。

## P0-2 `asr_total_budget_s` 不是总预算

位置：`application/pipeline.py`、`infrastructure/asr.py`、`infrastructure/asr_streaming.py`

当前实现只在 batch fallback 开始前检查一次 deadline，然后直接调用 `asr_cascade.transcribe(pcm)`。Cascade 内部仍可能顺序执行：

```text
DashScope batch 15s
→ Volcengine 自身 timeout
→ 本地模型加载/推理（无统一剩余预算）
```

因此 30 秒配置不能真实限制所有 ASR 阶段。

此外 `streaming_session.finish(timeout=x)` 在 x 之前还固定执行 worker join 3 秒和 stop watchdog 5 秒，实际耗时不是 x 秒，也没有共享单一 deadline。

要求：Pipeline 建立一个单调时钟 deadline，并把“剩余预算”传入 streaming finish、batch cascade 和每个 engine；每个阶段开始前和调用内部都必须受同一 deadline 约束。

## P0-3 Streaming cleanup 仍可能永久阻塞或遗留后台线程

位置：`infrastructure/asr_streaming.py`、`application/pipeline.py`

`finish()` 把 `recognition.stop()` 放入 daemon thread，超时后仅让 Pipeline 返回，无法停止已经卡住的 SDK 线程；阻塞的 send worker 也可能继续存活。

更严重的是 `abort()` 仍直接同步调用：

```python
self._recognition.stop()
```

没有 timeout。Pipeline 在音频启动失败、录音太短等路径中先调用 `streaming_session.abort()`，再发送 terminal；如果 SDK stop 卡住，terminal 永远不会产生。

要求：`abort()` 与 `finish()` 使用同一个有界 cleanup 契约；任何 SDK stop/send 卡住都不能阻止 terminal；清理 chunk callback；连续失败不得持续增加存活 worker/stop 线程。

## P0-4 输入框三态仍会把“不确定”当成“确定没有输入框”

位置：`infrastructure/injector.py`、`application/pipeline.py`

当前 `_assess_target_editability()` 虽然把 TextPattern-only 返回为 `editable_probable`，但以下情况仍返回 `no_editable`：

- UIA 没有 focused element；
- focused element 没有 ValuePattern/TextPattern；
- UIA 能运行但无法证明可编辑；
- 已知 Chrome/Obsidian/微信/飞书控件没有暴露预期 pattern。

随后 `_inject_locked()` 把 `no_editable` 和 `no_editable_verified` 同等处理，零注入直接返回 `no_editable_target`，并可能弹大卡片。已知应用策略表在这个早退之后才会执行，因此无法兜底。

另一个问题：早退发生在更新 `last_target_proc/title/class` 之前，Pipeline 的 SayIt 自身窗口判断可能读取上一 session 的陈旧目标信息。

故障链：

```text
真实 contenteditable 输入框
→ UIA pattern 不完整/暂时失败
→ no_editable（其实只是无法判断）
→ 零 dispatch
→ no_editable_target
→ 错误弹大卡片，文字不注入
```

要求：只有 `no_editable_verified` 才能零 dispatch 并允许大卡片；所有不确定情况进入 `editable_probable` 的一次安全注入；已知应用策略必须在 gate 中生效；当前目标元数据必须在任何早退前更新；SayIt 自身窗口必须用当前 session 真实目标判定。

## P1-1 Terminal 契约不完整且前端不是完全以 terminal 为准

- `PIPELINE_TERMINAL` 注释要求 `final_text_available`，实际 payload 和 server 转发均缺少该字段；
- Orchestrator 捕获异常时直接 emit terminal，绕过 Pipeline latch；结构上不能证明“恰好一次”；
- 前端 terminal handler 只处理 `success/failed/aborted`，`no_target/attempted_unverified` 仍依赖后续 legacy `pipeline_done` 才复位；
- WebSocket close/error 只重连，没有结束当前视觉等待。

## P1-2 测试门禁存在伪覆盖/覆盖不足

### Result card Node harness

`frontend/_test_result_card_race.js` 明确写的是“Simulated main.js state”，重新实现了 `showResultCard/onPipelineDone/flush...`，没有 import 或执行 `frontend/main.js` 的生产逻辑。因此“tests production code”的自审结论不成立。

### Streaming tests

- slow worker 使用 MagicMock，`join()` 立即返回；
- 没有检查真实阻塞 send worker 是否残留；
- SDK stop 挂起测试只验证 Pipeline 10 秒内返回，没有检查 daemon thread 泄漏；
- sentinel 测试再次手写实现，而非只调用生产 helper。

### Terminal tests

- 多数断言是 `>= 1`，不能证明恰好一次；
- 没有通过真实 Orchestrator wrapper 验证异常终态；
- 没有完整覆盖 db rules、history save、terminal 后异常和前端所有 outcome。

## P1-3 右 Alt 仍未被生产日志证明

Orchestrator 的 busy gate 与 stop latch 可以阻止部分重复操作，但当前 session 日志没有按任务要求记录 hotkey start/stop/native/fallback 计数。自动测试不能替代物理键事件，因此“不会重复 toggle/自动开始下一轮”仍未得到证据确认。

## 已确认基本正确的部分

以下代码路径经静态审查未发现当前阻塞缺陷，但仍需在修复上述 P0 后实机验证：

- `result_card_show → pipeline_done → did-finish-load` 的 pending payload 不再被 done/error 主动清空；
- 结果卡片显示文字与复制来源都来自 `pendingResultCardPayload/pendingResultText`；
- 空 ASR 文本在注入前终止，不创建空卡片；
- `attempted_unverified` 走轻提示，不主动重试或弹大卡片；
- clipboard 路径遇到图片/文件/多格式会拒绝覆盖并转 SendInput；文本 clipboard 会尝试恢复；
- 注入动作 dispatch 后不会继续第二条注入路径，降低重复注入风险；
- SilentMonitor gate 仍要求 `verified_success + target_verified + hwnd`。

## 结论

```text
Round 9.2 是否真正完成：否
当前严重度：P0
是否可以开始用户实机验收：否
下一步：执行 .ai/ROUND9_3_P0_FIX_TASK.md
```

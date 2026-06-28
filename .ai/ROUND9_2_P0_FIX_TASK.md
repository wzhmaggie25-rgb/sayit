# Round 9.2 P0 Fix Task — Alt主链路、ASR收尾、终态与空结果卡片

> 执行器：ZCode GUI → Claude Code
> 当前分支：`feature/silent-learning-stabilization`
> 成功终态：`BLOCKED_USER_VALIDATION`

## 开始前必须读取

```text
AGENTS.md
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_2_P0_RUNTIME_BUG_REVIEW.md
.ai/ROUND9_2_P0_FIX_TASK.md
.ai/ROUND9_1_SELF_REVIEW.md
```

## 本轮唯一目标

修复用户实机出现的P0故障：

```text
Alt停止后长期“思考中”
后台仍在识别/处理
悬浮条不消失
文字不注入
结果卡片为空
有输入框却误判无输入目标
```

不得开发发布、登录、更新、群聊、场景写作等新功能。

---

## Phase A — 先建立真实失败复现

必须先写失败测试，不先改实现。

### A1 Streaming queue deadlock

构造：

- `_audio_queue`已满；
- send worker已退出或不再消费；
- 调用`finish()`。

旧实现应在测试deadline内失败，证明`put(None)`会卡住。

### A2 Pipeline crash terminalization

让fake依赖分别在以下阶段抛异常：

```text
streaming finish
batch ASR
local correction/db rules
AI
injector
history save
```

断言每个session都收到一个terminal error事件，Float不会永远STOPPING。

### A3 Result card first-open race

用Node/Electron harness模拟：

```text
result_card_show
→ pipeline_done
→ did-finish-load
```

断言最终文字和复制源仍存在。

### A4 Real input eligibility

测试生产逻辑：

- Win32 Edit/RichEdit；
- Chromium/Electron contenteditable（TextPattern/Document、无ValuePattern）；
- 微信/飞书已知clipboard策略；
- 真正桌面/无focus；
- SayIt自身窗口。

---

## Phase B — 修复Streaming ASR收尾

`DashScopeStreamingASRSession.finish()`必须保证有界返回。

要求：

1. 不允许阻塞式无timeout：

```python
_audio_queue.put(None)
```

改为安全终止机制，例如：

```text
put_nowait sentinel
queue满时丢弃最旧/清理队列后插入sentinel
或独立stop flag让worker退出
```

2. worker已退出时不再等待queue消费；
3. `recognition.stop()`也要放入可控deadline；
4. finish总预算建议5–8秒，不能固定最低45秒；
5. 超时后abort并立即进入batch fallback；
6. cleanup必须清空audio callback，避免旧session继续接收chunk；
7. 不遗留永久worker线程；
8. 连续10次失败不能增加线程数或queue积压。

不要用无法取消的无限daemon线程掩盖问题。

---

## Phase C — 每个session恰好一个terminal事件

新增明确事件，例如：

```text
PIPELINE_TERMINAL
```

payload至少包含：

```text
session_id
outcome: success / no_target / attempted_unverified / failed / aborted
stage
reason_code
final_text_available
```

要求：

1. Pipeline正常完成发一次；
2. 任意异常也发一次；
3. `_pipeline_wrapper` catch必须：
   - `logger.exception(..., exc_info=True)`；
   - emit session-scoped terminal failed；
   - emit可读错误提示；
4. finally只清资源，不代替terminal；
5. 使用terminal latch，禁止DONE+ERROR双终态；
6. 前端收到terminal后一定退出STOPPING；
7. terminal failed时不自动重试、不自动注入。

保留旧事件兼容，但前端最终复位以terminal为准。

---

## Phase D — 前端“思考中”保护

1. `recording_stopping`后启动session-scoped watchdog；
2. 正常terminal到达时取消；
3. 超过合理总预算（例如60秒，可配置）仍无terminal：
   - 显示“处理异常，请查看历史/日志”；
   - 退出无限“思考中”；
   - 不自动重新提交；
   - 不自动注入；
4. 迟到旧session terminal不得改变新session UI；
5. backend WebSocket断开时也必须结束当前视觉等待并提示，而不是永久动画。

watchdog只是UI安全网，不能代替后端修复。

---

## Phase E — 修复空结果卡片竞态

规则：

- `pipeline_done`/terminal不得清除当前已显示或仍在加载的result-card payload；
- payload只在以下时机清理：

```text
用户关闭
复制完成并自动关闭
新session开始
窗口销毁
明确取消该session卡片
```

具体要求：

1. `RESULT_CARD_SHOW`写入不可变session payload；
2. `did-finish-load`一定能flush当前session payload；
3. `pipeline_done`只结束Float状态，不碰结果卡片正文；
4. `error`若已有可用final_text，不得先清空再显示空错误窗；
5. 复制源与界面文字来自同一session对象；
6. 增加真实race harness。

---

## Phase F — 修复“有输入框却no_editable”

不要再把“无法通过ValuePattern证明”直接等同于“没有输入框”。

建立三态：

```text
editable_verified
editable_probable
no_editable_verified
```

规则：

1. Win32 Edit/RichEdit → editable_verified；
2. UIA ValuePattern非只读 → editable_verified；
3. Chromium/Electron TextPattern/Document/contenteditable：
   - 当前foreground与录音开始target一致；
   - 控件可键盘聚焦；
   - app策略为clipboard/UIA fallback；
   → editable_probable，允许一次安全clipboard/SendInput路径；
4. 微信、飞书、Notion、Obsidian、Chrome等已知策略不能因缺ValuePattern直接返回no_editable；
5. 桌面、任务栏、空白窗口、SayIt自身窗口 → no_editable_verified；
6. `target_is_sayit_window`必须传真实值，不得硬编码False；
7. 若动作已dispatch但无法readback → attempted_unverified + 轻提示，不弹大卡片；
8. 只有no_editable_verified且零dispatch才弹大卡片。

不得恢复到任意stale target，不得强抢用户后来主动切换的窗口。

---

## Phase G — ASR总预算与降级

建立单一ASR总预算，例如：

```text
stream finalization 5–8s
batch fallback剩余预算
总ASR预算不超过20–30s（可配置）
```

要求：

- 不把45s + 15s + 30s简单相加；
- 每次阶段切换都发`ASR_PROGRESS`；
- 超预算后给出terminal failed或已有partial时采用partial；
- 若有可信stream partial，可在final失败时作为候选，但必须标记来源；
- 不允许空文字进入结果卡片；
- 无识别文本时显示明确错误，不创建空卡片。

---

## Phase H — 运行时日志与物理Alt验证

增加一次完整session结构化日志：

```text
session_id
hotkey start count
hotkey stop count
native emitted count
fallback count
stage enter/exit
stream queue size
worker alive
ASR engine
terminal outcome
inject state
result-card state
```

不得记录完整用户正文或API key。

物理Alt实机测试：

```text
一次开始
一次停止
不重复toggle
不自动启动下一轮
10秒/1分钟/5分钟录音
```

若helper v4实际重复事件，先用日志证明，再修；不要盲目继续改热键状态机。

---

## Phase I — 完整门禁

必须运行且0 failures：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
node frontend/_test_result_card_race.js
```

新增测试必须覆盖：

- streaming queue满/worker死不阻塞；
- pipeline每阶段异常都有terminal；
- terminal只一次；
- Float终止watchdog；
- result card show→done→load仍有文字；
- Chrome/Obsidian/微信类目标走安全注入；
- 桌面无focus才弹卡片；
- 空文本不创建卡片；
- 不重复注入；
- clipboard保护；
- SilentMonitor仍只在verified_success启动。

创建：

```text
.ai/ROUND9_2_SELF_REVIEW.md
```

最终状态：

```text
BLOCKED_USER_VALIDATION
```

不要写DONE。填写所有checkpoint完整SHA和最终远端HEAD并push。
# Round 9.3 P0 Fix Task — 真实总预算、终态、长录音与输入目标

> 执行器：`ZCode GUI → Claude Code`
> 当前分支：`feature/silent-learning-stabilization`
> 独立审查基线：`a5912b67abdf78d762a104e7964e1fbadeb5aa82`
> 独立审查提交：`94abee2dfda7307b40ecb9e5c88051c1d947220c`
> 成功终态：`BLOCKED_USER_VALIDATION`

## 开始前必须读取

```text
AGENTS.md
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_2_P0_FIX_TASK.md
.ai/ROUND9_3_P0_INDEPENDENT_REVIEW.md
.ai/ROUND9_3_P0_FIX_TASK.md
```

不要根据 Round 9.2 自审直接判断完成，必须以生产代码和新增真实门禁为准。

## 本轮唯一目标

修复独立审查确认的主链路阻塞问题：

```text
右 Alt 开始
→ 正常录音（包括 5 分钟）
→ 右 Alt 一次停止
→ Streaming / batch ASR 受同一个真实总预算约束
→ AI
→ 只注入一次
→ 每个 session 恰好一个 terminal
→ 前端一定退出“思考中”
```

本轮不得开发安装包、更新、登录、群聊、订阅、场景化写作或个人表达学习。

---

## Phase A — 先建立调用生产代码的失败测试

必须先写失败测试，再改实现。禁止在测试文件中重新手写一套生产逻辑。

### A1 前端 session 生命周期

将 watchdog / terminal / result-card 的关键状态转换提取到一个生产模块，由 `frontend/main.js` 和 Node 测试共同 import；或使用可注入依赖的方式直接执行生产 handler。

必须覆盖：

1. `recording_started` 后持续录音 5 分钟，不启动“处理超时”计时器；
2. `recording_stopping` 才启动处理 watchdog；
3. `success / failed / aborted / no_target / attempted_unverified` 任一 terminal 都结束视觉等待并取消 watchdog；
4. 迟到的旧 session terminal 不得影响新 session；
5. WebSocket close/error 时，当前等待必须结束并显示明确提示；
6. `result_card_show → pipeline_done/terminal → did-finish-load` 后文字和复制源仍属于同一 session；
7. watchdog 不得清除已经存在的有效结果卡片正文。

### A2 Streaming 有界清理

使用真实 `DashScopeStreamingASRSession.finish()` / `abort()` 生产代码和可控 fake recognition/worker，覆盖：

1. queue 满、worker 已死；
2. `send_audio_frame()` 永久阻塞；
3. `recognition.stop()` 永久阻塞；
4. 音频启动失败时调用 `abort()`；
5. 录音太短时调用 `abort()`；
6. 连续 10 次失败后，存活的 session worker/stop helper 数量不持续增长；
7. `finish(timeout=x)` 的总墙钟时间不超过 `x + 小幅调度余量`，不能再出现 `3s + 5s + x`。

测试不得只用 `MagicMock.join()` 立即返回来模拟慢 worker，也不得在测试内重新实现 sentinel helper。

### A3 真实 ASR 总预算

构造多个 fake engine，让每级分别消耗时间，调用生产 `RecordingPipeline` 和 `AsrCascade`：

1. streaming finalization、DashScope batch、Volcengine、本地 fallback 共用一个 monotonic deadline；
2. 总墙钟时间不超过配置预算加小幅调度余量；
3. 剩余预算不足时，不启动下一引擎；
4. 引擎内部收到剩余预算或 deadline，而不是继续使用固定 15/30 秒；
5. 本地模型加载和推理也必须受剩余预算约束；
6. 超预算后只产生一个 failed terminal；
7. 有可信 streaming partial/final 候选时按明确规则使用，并记录来源；无文字时不得创建空卡片。

### A4 输入目标三态与真实应用策略

调用生产 `Injector._assess_target_editability()` 和 `_inject_locked()`，覆盖：

1. Win32 Edit/RichEdit → `editable_verified`；
2. UIA ValuePattern 非只读 → `editable_verified`；
3. TextPattern/contenteditable → `editable_probable`；
4. Chrome、Obsidian、微信、飞书在没有 ValuePattern、没有 TextPattern或 UIA 暂时失败时，只要当前 foreground 与 session 目标合理一致且属于已知安全策略，也必须进入 `editable_probable`，进行一次安全注入尝试；
5. 真正桌面/任务栏/无 foreground/SayIt 自身窗口 → `no_editable_verified`；
6. 只有 `no_editable_verified + injection_dispatched=False` 才能弹大卡片；
7. `editable_probable` dispatch 后无法 readback → `attempted_unverified` + 轻提示；
8. 当前 session 的 target proc/class/title/hwnd 必须在任何早退前更新，不能读取上一 session 的陈旧值；
9. 不恢复 stale target，不强抢用户主动切换后的窗口。

### A5 Terminal 单一所有者

通过真实 `SayitOrchestrator._pipeline_wrapper` 路径验证：

1. recording、streaming finish、batch ASR、规则读取、规则计数更新、AI、injector、history save 任一阶段抛异常；
2. 每个 session **严格等于一个** `PIPELINE_TERMINAL`；
3. payload 包含：

```text
session_id
outcome
stage
reason_code
final_text_available
```

4. terminal 发送失败或 listener 抛异常不能导致重复 terminal；
5. legacy DONE/ERROR 可以保留兼容，但前端复位只以 terminal 为主；
6. terminal 后不得自动重试、再次注入或自动开始下一轮。

---

## Phase B — 修复前端 watchdog 生命周期

1. 不得在 `recording_started` 启动处理 watchdog；
2. 只在当前 session 的 `recording_stopping` 后启动；
3. timeout 应基于后端真实 ASR + AI 总预算，并留合理余量；
4. 所有 terminal outcome 都统一结束 STOPPING/“思考中”；
5. `no_target` 和 `attempted_unverified` 不得依赖随后到达的 legacy `pipeline_done` 才复位；
6. WebSocket 断开时立即结束视觉等待、提示后台连接异常，不自动注入；
7. watchdog 只负责 UI 安全网，不清除已有有效 result-card payload，不掩盖后台死锁。

---

## Phase C — Streaming finish/abort 使用同一个有界清理契约

1. 使用单一 monotonic deadline；
2. worker drain、sentinel、SDK stop、final callback 等步骤都消耗同一剩余预算；
3. `abort()` 不得直接无界调用 `recognition.stop()`；
4. Pipeline 所有提前退出路径必须先解除 `audio_capture` chunk callback，再做有界 cleanup；
5. 若 SDK 调用不可取消，需要建立受控、可复用且数量有上限的隔离执行器，不能每个 session 留下一个永久 daemon 线程；
6. send worker 卡住后不得阻止 terminal；
7. cleanup 失败要记录脱敏原因，但用户文本、录音正文、API key 不得写日志。

不要用“把卡住线程设为 daemon”作为完成标准。

---

## Phase D — 让 ASR 总预算真实覆盖所有阶段

1. Pipeline 在停止录音后建立一个 monotonic deadline；
2. streaming finish、batch cascade、每个 cloud engine、本地模型加载/推理都接收 deadline/remaining budget；
3. 移除会突破总预算的固定内部 timeout；内部 timeout 必须是 `min(自身上限, remaining)`；
4. 每级返回后重新检查剩余预算；
5. 剩余预算不足时不得启动下一引擎；
6. 超预算后立即 terminal，不继续后台文件识别；
7. AI timeout 仍可单独配置，但前端处理 watchdog 必须覆盖 ASR + AI 的实际最大值；
8. 每次阶段切换发 `ASR_PROGRESS`，但不得重复发送错误提示。

---

## Phase E — 真正实现三态输入框判断

生产状态只保留：

```text
editable_verified
editable_probable
no_editable_verified
```

要求：

1. 删除或停止把 `no_editable` 当作确定无输入框的早退状态；
2. 无法证明可编辑但也无法证明无输入框时，一律归入 `editable_probable`；
3. 已知应用策略必须参与 gate，不能在策略选择之前误退；
4. 当前 foreground 与录音开始 target 的关系必须用于判断；
5. SayIt 自身窗口必须从当前 session 的真实目标识别；
6. 只有真正无输入目标且零 dispatch 才弹大卡片；
7. dispatch 一次后无 readback → `attempted_unverified`，不得再走第二条注入路径；
8. 不破坏文本、图片、文件、多格式 clipboard。

---

## Phase F — Terminal 事件成为唯一前端终态

1. Terminal 由一个 session-scoped latch/owner 统一发送；
2. Orchestrator uncaught exception 不得绕过 latch直接制造第二个 terminal；
3. `final_text_available` 必须进入 EventBus、server WebSocket 和前端；
4. 前端为所有 outcome 定义明确动作：

```text
success               → 完成并隐藏/复位 Float
no_target             → 结束思考中；结果卡片独立保留
attempted_unverified  → 结束思考中；只显示轻提示
failed                → 结束思考中；显示错误
aborted               → 结束思考中；显示取消/异常
```

5. legacy `pipeline_done/error` 只保留兼容，不得成为正确复位所必需；
6. terminal 到达后迟到事件不得改变新 session 状态。

---

## Phase G — 补齐右 Alt 脱敏诊断

每个 session 记录以下计数，不记录用户正文：

```text
hotkey_start_count
hotkey_stop_count
native_emitted_count
fallback_stop_count
toggle_ignored_count
terminal_count
```

要求：

- 一次物理开始只产生一个 start；
- 一次物理停止只产生一个 stop ACK；
- post-processing 期间的重复/迟到按键只计 ignored，不启动下一 pipeline；
- terminal 后才允许下一轮；
- 不盲目修改 DLL 状态机，先用计数证明问题。

---

## Phase H — 完整门禁与提交

必须运行且 0 failures：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
node frontend/_test_result_card_race.js
```

新增门禁还必须单独运行并记录：

```text
前端 5 分钟 CAPTURING 不触发 watchdog
recording_stopping 后 watchdog 才启动
所有 terminal outcome 都复位
WebSocket 断开复位
finish/abort 卡住场景有界返回
连续 10 次 streaming cleanup 不持续增加线程
ASR 多引擎总墙钟不突破预算
Chrome/Obsidian/微信/飞书无 Pattern 场景仍安全 dispatch
真正桌面/SayIt 自身窗口才 no_editable_verified
真实 Orchestrator 每阶段异常严格一个 terminal
剪贴板文本、图片、文件、多格式保护
SilentMonitor 只在 verified_success + target_verified 后启动
```

创建：

```text
.ai/ROUND9_3_SELF_REVIEW.md
```

自审必须明确列出：

- 每个 P0 的生产代码位置；
- 测试是否直接调用生产代码；
- 所有 checkpoint 完整 SHA；
- 最终远端 HEAD；
- 尚未由物理实机证明的风险。

最终把 `.ai/CURRENT_TASK.md` 状态改为：

```text
BLOCKED_USER_VALIDATION
```

在所有门禁完成前保持 `ZCODE_IN_PROGRESS`，不要提前写完成。不要修改 main、backup 分支、稳定 tag，不要 force push、reset --hard 或 git clean。

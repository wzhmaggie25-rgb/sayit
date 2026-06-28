# Round 9.1 Fix Task — Production Path Alignment

> 执行器：ZCode GUI → Claude Code
> 状态：待 CURRENT_TASK 发布
> 目标：修复 Round 9 独立审查发现的真实生产路径问题

## 必须先读

```text
AGENTS.md
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_CODE_REVIEW.md
.ai/ROUND9_LONG_TASK.md
.ai/ROUND9_SELF_REVIEW.md
```

## Phase A — 修复结果卡片真实坐标

1. 明确 float renderer 上报的是 viewport-relative rect。
2. main process 必须转换为 screen rect：

```text
screen_left = floatWin.bounds.x + rect.left
screen_top  = floatWin.bounds.y + rect.top
```

3. 或由 main process 保存 float bounds 后统一转换，但不得混用坐标系。
4. 多显示器 workArea clamp 使用目标 display 的绝对屏幕坐标。
5. 不要在 Python 测试中重写公式；新增可执行 Node harness，直接调用/导出 main.js 的真实 geometry helper。
6. 覆盖：主屏、负坐标副屏、右侧副屏、缩放、fallback 无 element rect。

## Phase B — 生产级 ResultCardEligibility

1. 把资格函数放进生产模块，而不是测试文件：

```text
state == no_editable_target
AND injection_dispatched == false
AND inserted_verified == false
AND target_is_sayit_window == false
```

2. Pipeline 必须只通过该生产函数决定是否 emit `RESULT_CARD_SHOW`。
3. `injection_failed` 无论是否 dispatch，都不弹大卡片；保存历史并显示轻提示/错误提示。
4. `attempted_unverified` 只轻提示。
5. 测试必须导入生产函数，并对 EventBus 真实 emit 行为做断言。

## Phase C — RAlt 单次事件模型

当前 native helper 在 keyup emit，watcher 在 keydown fallback，存在第二次 toggle。

推荐修法：

1. 修改原生 keyboard helper：
   - RAlt down 时 emit toggle 并吞键；
   - 对应 keyup 只清状态和吞键，不再 emit；
   - auto-repeat down 不重复 emit。
2. watcher 在 down-edge 后给主 hook 20–40ms grace，再检查 total_emitted；仅未增加时 fallback。
3. ACK 总延迟仍 <100ms。
4. `_stop_request_latched` 使用同一个 lock 或原子式 helper：

```text
try_latch_stop() -> bool
```

主 hook 与 fallback 都只能通过该函数获得一次执行权。
5. 重建 DLL，并提升/验证 ABI build identity。
6. 真实 native parser tests 必须验证：
   - start down 只 emit 一次；
   - start up 不 emit；
   - stop down 只 emit一次；
   - stop up 不 emit；
   - fallback 不与正常 hook重复；
   - 长按和 auto-repeat 不产生下一次录音。

## Phase D — 焦点保护改为注入前严格补救

1. 删除 Pipeline `finally` 中无条件 `SetForegroundWindow(pre_stop_hwnd)`。
2. stop 时记录：
   - top-level hwnd；
   - focused control hwnd/UIA identity；
   - capture timestamp；
   - editable/read-only 证据。
3. 注入前：
   - 若当前已有有效 editable control，使用当前目标，绝不拉回旧窗口；
   - 若当前无有效目标，且 stop snapshot 很新、identity 仍有效、目标非 SayIt、自身未被用户主动切换证据否定，可做一次受控恢复；
   - 恢复后重新读取 focused control并验证 identity；
   - 验证失败则 no_editable_target，不强注入。
4. 用户在 ASR/AI期间主动切换窗口，完成后不得抢回。
5. 测试必须覆盖主动切换和 Alt菜单瞬时失焦两种不同情况。

## Phase E — Session ID 真正不可变传播

1. session_id 在 event 创建/入队时绑定，不在 broadcast 时读取全局补写。
2. 可使用 session-aware enqueue helper：

```text
enqueue_event(event, session_id=current_pipeline_session)
```

3. Pipeline 的全部事件应携带自己的 session_id，或 server listener 在收到事件时立即复制当前 session id进 dict。
4. pipeline_done/error 后适时清理 current session，但不能影响已入队事件。
5. 测试真实 event queue：旧事件延迟发送时仍保持旧 session id。

## Phase F — Backend supervisor 对齐真实逻辑

1. `exit(code, signal)`：
   - user initiated → 不重启；
   - code === 0 且无 signal → 正常退出，不重启；
   - 非0或signal → 崩溃，最多重启一次。
2. spawn `error` 也进入同一恢复策略。
3. 重启成功并健康运行一段时间后，重置 crash episode budget；不能永久失去以后恢复能力。
4. 第二次连续崩溃停止重启，UI显示明确“后台恢复失败”。
5. 抽出可测试的真实 JS supervisor policy，并由 Node harness直接测试生产函数；禁止 Python 中另写模拟器。

## Phase G — AI deadline 不遗留请求线程

1. `call_provider(..., timeout=...)` 必须把 timeout真正传给 `httpx.Client.post()`。
2. Corrector/process 接收 per-call deadline。
3. 优先同步调用 + httpx明确 timeout + 捕获 TimeoutException降级。
4. 不允许每次超时永久遗留一个 daemon request thread。
5. 测试连续10次 timeout 后线程数不会持续增长，且每次只注入一次。

## Phase H — 真实测试门禁

删除/重写只测试常量、手工 dict、模拟变量、测试内重复实现生产策略的伪测试。

必须运行且 0 failures：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

不得 `--deselect`，不得改变成 timeout=60 来绕过门禁。

现有4个失败必须修复或证明测试本身已过时并在同一提交中正确更新；不能继续以“pre-existing”名义写成回归通过。

创建：

```text
.ai/ROUND9_1_SELF_REVIEW.md
```

逐项写真实实现位置、真实测试、剩余风险。

完成终态：

```text
BLOCKED_USER_VALIDATION
```

commit并push当前 feature 分支，不修改main/backup/tag。
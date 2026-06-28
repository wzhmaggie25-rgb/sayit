# Round 9 Independent Code Review

> 日期：2026-06-28
> 审查范围：`662ad81` → `45e2a7f`
> 结论：**ROUND9_REVIEW_FAILED**

ZCode 确实完成了 8 个提交并增加了大量实现与测试，但当前不能进入用户实机验收，也不能合并 main。主要原因是多项测试只在测试文件中重新实现/模拟目标逻辑，没有调用真实生产实现；生产代码仍存在会直接影响用户体验的 P0/P1 问题。

## P0-1 结果卡片坐标系错误

`float.html` 上报的是 `getBoundingClientRect()`，即相对 500×500 float BrowserWindow 的 viewport 坐标：

```js
{left:r.left, top:r.top, right:r.right, bottom:r.bottom}
```

但 `frontend/main.js::calcResultCardPosition()` 直接把 `elementPositions[0]` 当成屏幕坐标：

```js
anchorTop = ep.top
anchorLeft = ep.left
```

没有加 `floatWin.getBounds().x/y`。因此真实卡片可能被定位到屏幕左上区域，而不是条形悬浮窗上方。

`tests/test_result_card_geometry.py` 只在 Python 中重新计算常量和公式，没有执行 main.js 的真实函数，因此没有发现该错误。

## P0-2 严格弹卡资格没有进入生产代码

`tests/test_result_card_eligibility.py` 在测试文件内部定义了 `should_show_large_result_card()`，但生产代码没有该函数，也没有调用该策略。

真实 `application/pipeline.py` 中：

- `no_editable_target` 无条件发送 `RESULT_CARD_SHOW`；
- `injection_failed` 且 `injection_dispatched == false` 也发送大结果卡片。

这违反已确认要求：

```text
只有 state == no_editable_target
AND 未发送注入动作
AND 未验证插入
AND 目标不是 SayIt 自身窗口
才显示大结果卡片
```

测试通过的是测试文件里的模拟函数，不是生产行为。

## P0-3 RAlt down-edge 与原生 keyup toggle 冲突

原生 `native/context_helper/src/keyboard_helper.cpp` 仍在 RAlt **松开**时 `EmitToggle()`。

新 `RAltStopWatcher` 在 RAlt **按下**时检查 `get_total_emitted()`。因为原生计数只有松开时才增加，正常主 hook 工作时，按下瞬间计数也必然未增加，所以 fallback 会把正常事件误判为 hook miss，并立即停止。

随后用户松开 RAlt，原生 DLL 仍会再次 emit toggle。通常该事件会在 ASR/AI 阶段被忽略，但如果用户长按、或 Pipeline 很快结束，存在误启动下一次录音的风险。

此外 `_stop_request_latched` 的“检查后设置”没有使用同一个锁或原子 compare-and-set，主 hook 与 fallback 仍可能同时通过 `False` 检查。

## P0-4 焦点保护实现方向错误

当前实现：

1. 停止时只保存顶层 foreground hwnd；
2. 正常完成 ASR、AI、注入以后；
3. 在 Pipeline `finally` 中无条件 `SetForegroundWindow()` 拉回该窗口。

问题：

- 恢复发生在注入之后，不能帮助本次注入找到原输入框；
- 只保存顶层窗口，不是 focused editable control identity；
- 用户在“思考中”主动切换到其他窗口后，程序仍会把旧窗口抢回来；
- 与需求“用户主动切换时不得拉回旧目标”冲突。

必须删除 Pipeline 结束后的无条件窗口恢复，改为注入前对 stop 前 focused control 做一次严格、短时、身份验证后的补救。

## P0-5 Backend supervisor 与测试逻辑不一致

真实 `frontend/main.js` 对任何非用户主动的 backend exit 都尝试重启，包括 `code === 0`；代码没有正常退出不重启的判断，也忽略了 `signal` 参数。

但 `tests/test_backend_supervisor.py` 测试的是测试文件中独立编写的 `_simulate_supervisor()`，该模拟包含 `code == 0 → ignore`，与真实 main.js 不一致。因此“normal exit no restart”测试通过不能证明生产代码正确。

同类问题还包括：spawn `error` 事件不触发恢复；成功恢复后 restart budget 永久不重置，后续独立崩溃不会再恢复。

## P1-1 Session ID 在 broadcast 时附加，可能误标迟到事件

server 当前把事件先放入无 session_id 的 queue，再在异步 `broadcast()` 时读取全局 `_current_session_id` 附加。

这不是事件创建时的不可变 session id。若旧事件延迟到下一 session 才发送，会被错误标成新 session，前端过滤无法识别。

`tests/test_session_id.py` 大量测试只是构造 dict 或手工模拟变量，没有调用 server 的真实 queue/broadcast 路径。

## P1-2 AI 超时后遗留不可取消 daemon thread

Pipeline 超时后直接放弃 `ai-correction` daemon thread。底层 httpx client 默认仍可能等待 60 秒；连续多次超时会堆积后台线程和网络请求。

更稳妥做法是让 provider 调用真正接受本次 deadline，并把 timeout 传入 `client.post()`，然后同步捕获超时并降级；或至少确保旧请求不会无限堆积。

## P1-3 测试门禁没有按任务要求执行

任务要求：

```text
python -m pytest tests/ -v --timeout=30
```

并要求不得删除/跳过失败测试。

实际报告使用 `--timeout=60`，并 `--deselect` 一个测试；同时承认仍有 4 个失败，却在 CURRENT_TASK 中写“回归全部通过”。这不满足完成门禁。

## 可保留的有效工作

以下方向和部分代码可以保留：

- recording session id 基础字段；
- 新录音开始清除旧 result-card payload/timer；
- 结果卡片宽度和最大高度调整；
- attempted_unverified 轻提示方向；
- AI degraded 事件与本地文本 fallback；
- crash report、health endpoint、前端恢复提示基础框架；
- clipboard 与 verified-only SilentMonitor 旧门禁未被移除。

## 最终结论

当前完成度可认为：

```text
代码量：约 80%
真正通过生产行为验证：约 55%–65%
可进入用户实机验收：否
可合并 main：否
```

下一步执行 `.ai/ROUND9_1_FIX_TASK.md`，完成真实生产路径修正与真实测试后，再进行独立复审。
# Round 9 Runtime Stability Bugfix Plan

> 状态：PLAN_REVIEW
> 日期：2026-06-27
> 基线：`c2930f38368157058a399ead6ae7972b7af709fb`
> 本轮只修实机验收暴露的运行时问题，不开发账号、下载、升级、社群等商业化功能。

## 一、用户实机反馈

1. 结果卡片太大、位于屏幕中间；
2. 结果卡片应位于原有条形悬浮窗上方；
3. 结果卡片第一次出现后，后续即使光标位于输入框仍反复出现；
4. 长录音后第一次按 Alt 经常不能停止，第二次才能停止；Alt 可能导致输入框失焦，随后错误弹出结果卡片；
5. 结果卡片只应在“没有有效输入焦点，并且本次文字没有输入到任何位置”时出现；
6. 识别后的“思考中”阶段出现卡死和后台崩溃。

## 二、当前代码事实

### 2.1 结果卡片几何

`frontend/main.js::createResultCardWindow()` 当前固定：

```text
width = 420
height = 320
position = 当前主屏幕正中心
```

没有读取 `floatWin.getBounds()`，因此无法跟随条形悬浮窗，也没有动态高度。

### 2.2 结果卡片生命周期

当前只有一个全局：

```text
pendingResultCardPayload
pendingResultText
```

没有 recording/session id。`did-finish-load` 会无条件 replay 最近 payload。新录音开始时也没有强制关闭并清空旧结果卡片。因此旧事件、延迟事件或状态判断错误可能跨录音会话复现。

### 2.3 弹出资格过宽

Pipeline 当前对以下状态都可能发送 RESULT_CARD_SHOW：

```text
no_editable_target
attempted_unverified
injection_failed
```

而用户最新产品要求是：

> 大结果卡片只在没有有效输入焦点、没有发送任何注入动作、本次文字确定没有输入时出现。

### 2.4 Alt 停止链路

主路径为 keyboard helper DLL；补偿路径 `RAltStopWatcher`：

- 等待完整 RAlt down→up；
- 然后检查 DLL total_emitted 是否变化；
- 若主钩子未处理才 fallback stop。

当主钩子漏事件时，Alt 有机会先到达前台应用，激活菜单或改变输入焦点。补偿路径又必须等松键后才停止，因此用户感觉第一次没反应，并可能发生焦点丢失。

### 2.5 后台崩溃恢复

Electron 目前在 backend `exit` 时只打印 warning，并把 `backendProcess = null`：

- 不退出“思考中”UI；
- 不生成结构化崩溃报告；
- 不做一次受控重启；
- 不区分 AI 超时、Python 异常、native crash；
- 不保护本次输入结果。

AI HTTP 客户端默认总超时 60 秒。用户可能长时间看到“思考中”；native crash 则无法被普通 Python try/except 捕获。

---

## 三、最终产品行为

## 3.1 结果卡片样式与位置

目标尺寸：

```text
宽度：340–380 px，默认 360 px
高度：按内容动态 150–240 px，最大 260 px
```

位置：

```text
以当前显示器上的 floatWin 为锚点
结果卡片底边位于条形悬浮窗可见内容上方 12–16 px
水平居中对齐 floatWin 的实际可见条形区域
自动限制在 workArea 内
```

注意：float BrowserWindow 外壳目前为 500×500，但真正条形 UI 只占其中一部分。不能简单使用整个透明窗口顶边；需要由 float renderer 上报可见条形区域 bounds，或在 main process 维护真实 bubble bounds。

结果卡片：

- 不抢焦点；
- 允许点击复制和关闭；
- 长文本内部滚动；
- 不遮挡主要输入区域；
- 多屏时跟随录音时所在显示器，而不是固定主显示器。

## 3.2 严格弹出条件

定义：

```text
show_result_card =
    session.final_state == no_editable_target
    AND injection_dispatched == false
    AND inserted_verified == false
    AND current_focus_is_own_window == false
```

只有同时满足才显示大结果卡片。

以下情况不显示大结果卡片：

- verified_success；
- attempted_unverified；
- injection_failed 但曾发送过 paste/SendInput/selection insert；
- AI 失败但仍能使用本地整理文本；
- 用户主动关闭上一张卡片后产生的旧事件；
- 事件 session_id 与当前录音不一致。

`attempted_unverified` 保留历史和诊断，不自动弹大卡片。可在原条形悬浮窗中短暂显示“小提示：已尝试输入，请检查”，但不能遮挡用户。

## 3.3 会话隔离

每次录音创建唯一：

```text
recording_session_id
```

该 ID 贯穿：

```text
recording_started
recording_stopping
ASR progress/result
AI result/error
injection result
result_card_show/close
pipeline_done/error
history
```

Electron 只处理当前 session 的结果卡片事件。

在 `recording_started` 时必须：

- destroy/hide 旧 resultCardWin；
- 清空 pending payload/text；
- 取消旧 auto-close timer；
- 记录新的 activeSessionId。

在 `pipeline_done/error` 时关闭该 session 的临时 UI；不能把上一轮 pending payload replay 到下一轮。

## 3.4 焦点判断

记录三个时刻：

```text
recording_start_focus
stop_key_focus_before_alt_side_effect
injection_time_focus
```

规则：

- 开始录音时捕获输入框 identity；
- 停止键按下时，在 Alt 可能影响前台应用前尽快捕获当前 focused control；
- 注入时重新验证；
- 若仍是同一输入框，正常输入；
- 若用户主动切换到另一个有效输入框，输入到新的有效输入框；
- 若只是 Alt 激活菜单导致临时失焦，应在短暂窗口内恢复到 stop 前捕获的有效输入 identity，不把菜单焦点当作用户主动离开；
- 不强抢任意旧窗口；只允许恢复本次停止事件前刚刚验证过的 focused control，并且必须验证 window/control identity 未销毁。

SayIt 自己的 floatWin/resultCardWin/mainWin 必须永远排除在输入目标之外。

## 3.5 Alt 一次停止

目标：长录音中用户按一次右 Alt，就立即停止录音并显示停止反馈。

实现原则：

1. keyboard helper DLL 在 CAPTURING 时应吞掉作为热键的 RAlt 事件，避免它传给前台应用激活菜单；
2. stop watcher 改为监听第二次物理 RAlt 的 down edge，先提交幂等 stop request，不必等待完整 down→up 才给用户反馈；
3. 使用 `stop_request_latched`，一个录音 session 最多提交一次 stop；
4. 主 hook 和 fallback 竞争时，后到者无操作；
5. stop acknowledgement 延迟目标 < 100ms；
6. 长录音 1、5、15、30 分钟均应一次停止；
7. 记录非个人数据诊断：session id、hook event count、fallback count、stop latency、capturing duration。

不得通过合成 Alt keyup 破坏当前输入框焦点。只有检测到真实 modifier stuck 时才能执行受控释放。

## 3.6 “思考中”卡死与后台崩溃

### AI 超时

- 单次 AI 整理使用独立明确 deadline，建议 20–30 秒可配置；
- 超时后直接使用本地纠错后的文本继续注入；
- UI 显示“AI 整理超时，已使用识别结果”，不能永久停留“思考中”；
- 不能自动重新提交同一请求导致重复输入。

### Python 可捕获异常

- pipeline wrapper 必须发送结构化 `pipeline_error`；
- finally 恢复 pipeline mutex、RAlt watcher 和 UI；
- 保存不含用户正文的诊断摘要。

### Native/backend process crash

Electron 增加 backend supervisor：

- 记录 exit code/signal/当前 stage/session id；
- 立即让悬浮窗退出“思考中”，显示“后台已异常退出”；
- 写入本地 rotating crash report，默认不写完整语音正文；
- 非用户主动退出时最多自动重启一次；
- 重启使用指数退避，防止 crash loop；
- 不自动重放本次录音，不自动再次注入；
- 本次已识别文本若已安全保存在 history，可提示用户从历史恢复；
- 若没有安全文本，不伪造结果卡片。

启用 Python `faulthandler` 到独立崩溃文件，帮助定位 native crash。

---

## 四、开发阶段

## Phase 0：诊断与可复现

- 新增 session id 和 runtime stage 日志；
- 增加 backend exit 诊断；
- 加入可控 fault injection：AI timeout、AI exception、backend abnormal exit；
- 先建立复现测试，不先改行为。

## Phase 1：结果卡片几何与生命周期

- float renderer 上报真实可见 bubble bounds；
- 动态尺寸；
- 定位到 bubble 上方；
- 多显示器 clamp；
- recording_started 清理旧卡片；
- session id 拒绝陈旧事件；
- 清理 timer 和 pending payload。

## Phase 2：严格弹出资格

- ResultCardEligibility 纯函数；
- 只允许 no_editable_target + no dispatch + no insertion；
- attempted_unverified 改为条形浮窗轻提示；
- SayIt 自身窗口排除；
- 10 次连续输入不得出现“第一次以后次次弹”。

## Phase 3：Alt 单次停止与焦点保护

- stop request latch；
- watcher down-edge fallback；
- helper DLL CAPTURING 时吞热键；
- stop 前 focus snapshot；
- 排除 Alt 菜单临时失焦；
- 1/5/15/30 分钟长录音测试。

## Phase 4：AI 超时和 backend supervisor

- AI deadline/fallback；
- pipeline stage watchdog；
- backend abnormal exit UI reset；
- one-shot restart/backoff；
- faulthandler 和 crash report；
- 不自动重放、不重复输入。

## Phase 5：全量回归和实机验收包

必须测试：

- 结果卡片尺寸、位置、长文本滚动、多显示器；
- 10 次连续录音，只有真正无输入焦点时显示；
- 有效输入框中不显示卡片；
- Alt 一次停止，焦点不丢；
- 长录音；
- AI timeout；
- backend crash/restart；
- 图片、文件、多格式剪贴板保护；
- 静默学习只在 verified_success 启动。

最终状态：

```text
BLOCKED_USER_VALIDATION
```

---

## 五、明确不在本轮开发

以下需求只记录，不与运行时修复混合：

- 微信登录；
- 用户账号和设备管理；
- 对外下载网站；
- 自动检测/下载/安装升级；
- 用户群入口；
- 付费、授权、订阅；
- 场景引擎和个人写作风格学习。

原因：当前实机稳定性是发布与账号体系的前置条件。
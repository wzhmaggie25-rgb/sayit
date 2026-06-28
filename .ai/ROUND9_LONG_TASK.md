# Round 9 Long Task — 结果卡片、Alt 停止、焦点与崩溃恢复

> 执行器：SayIt Agent Bridge v0.2.2 → Claude Code CLI
> 当前分支：`feature/silent-learning-stabilization`
> 基线：以 `git pull --ff-only` 后 HEAD 为准
> 成功终态：`BLOCKED_USER_VALIDATION`

## 一、开始前必须读取

```text
AGENTS.md
.ai/CURRENT_TASK.md
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_RUNTIME_STABILITY_BUGFIX_PLAN.md
.ai/ROUND8_SELF_REVIEW.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
```

其中：

```text
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_RUNTIME_STABILITY_BUGFIX_PLAN.md
```

优先级最高。

## 二、本轮唯一目标

只修复以下实机问题：

1. 结果卡片太大且位于屏幕中间；
2. 结果卡片应位于条形悬浮窗上方；
3. 第一次出现结果卡片后，后续录音即使有输入焦点仍反复弹出；
4. 大结果卡片只能在“没有有效输入焦点、没有发送任何注入动作、没有输入文字”时出现；
5. 长录音第一次按右 Alt不能立即停止，第二次才停止；
6. Alt 导致当前输入框失焦，继而误判无输入目标；
7. AI“思考中”卡死；
8. backend 崩溃后 UI 卡住且无法恢复。

不开发微信登录、安装包、自动更新、用户群、订阅、场景化写作和个人表达学习。

## 三、安全边界

- 不修改 `main`、`backup/*`、稳定 tag；
- 不 force push、reset --hard、git clean；
- 不读取或修改真实用户数据库、历史、词典、录音、正文、API key；
- 不删除、跳过或弱化失败测试；
- 不通过重新强抢录音开始时的旧窗口解决焦点问题；
- 不自动重放录音；
- 不自动重复注入；
- 不破坏图片、文件、HTML、RTF、多格式剪贴板；
- 保留 verified-only SilentMonitor 门禁。

每个 Phase：

```text
先增加失败测试
→ 修实现
→ 跑定向测试
→ 跑相关回归
→ checkpoint commit
→ push
```

---

## Phase 0 — 会话 ID、诊断和复现测试

新增 `recording_session_id`，贯穿：

```text
recording_started
recording_stopping
recording_stopped
ASR progress/result/error
AI result/error
injection result
result_card_show/close/copy_done
pipeline_done/error
history
```

要求：

- 每次录音唯一 ID；
- Electron 只接受当前 session 的结果卡片事件；
- 记录 runtime stage、stop latency、hook count、fallback count、backend exit code/signal；
- 默认诊断不记录完整用户正文；
- 提供仅测试启用的 fault injection：AI timeout、AI exception、backend abnormal exit；
- 先增加能稳定复现旧 payload 重放、Alt stop miss、AI timeout 和 backend exit 的测试。

checkpoint commit + push。

---

## Phase 1 — 结果卡片尺寸和位置

### 尺寸

目标：

```text
默认宽度：360 px
允许范围：340–380 px
动态高度：150–240 px
最大高度：260 px
```

- 文本区域内部滚动；
- 卡片整体不固定 320px 高；
- 不再位于屏幕中心；
- 保留关闭、复制、状态、最近转录；
- 不抢焦点。

### 位置

结果卡片必须以条形悬浮窗的真实可见区域为锚点：

```text
[result card]
     12–16px gap
[visible float bar]
```

要求：

- float renderer 上报真实可见条形区域的 screen bounds；
- 不使用透明 500×500 BrowserWindow 外壳作为锚点；
- 多显示器跟随当前录音所在 display；
- clamp 在 display.workArea 内；
- 分辨率和缩放变化时重新定位；
- 条形悬浮窗位置变化时结果卡片同步更新。

增加纯函数几何测试和 Electron harness。

checkpoint commit + push。

---

## Phase 2 — 清理旧卡片和跨会话污染

在 `recording_started` 时：

- destroy/hide 旧 resultCardWin；
- pendingResultCardPayload = null；
- pendingResultText = ''；
- 清除所有 auto-close timer；
- 记录 activeSessionId；
- renderer reset。

事件规则：

- session_id 不等于 activeSessionId 的 `result_card_show/close/copy_done` 全部忽略；
- `did-finish-load` 只 replay 同 session pending payload；
- pipeline_done/error 后清理本 session 临时状态；
- 关闭卡片后不得在下一次录音重现。

测试：

- 第一次弹出并关闭后，连续 10 次有效输入不再弹；
- delayed old event 被忽略；
- window reload 不 replay 旧 session；
- copy/close timer 不跨 session。

checkpoint commit + push。

---

## Phase 3 — 严格结果卡片资格

建立纯函数或明确策略：

```text
show_large_result_card =
  state == no_editable_target
  AND injection_dispatched == false
  AND inserted_verified == false
  AND target_is_sayit_window == false
```

要求：

- `verified_success` 不弹；
- `attempted_unverified` 不弹大卡片；
- `injection_failed` 但曾经 dispatch 过，不弹大卡片；
- AI 失败但可使用 ASR/本地纠错结果时，不弹大卡片；
- 只有没有有效输入焦点且本轮完全没发注入动作时才弹；
- attempted_unverified 在条形悬浮窗显示短暂小提示：“已尝试输入，请检查”；
- SayIt main/float/result-card 自己的窗口永远不当输入目标。

InjectionResult 增加并贯穿：

```text
injection_dispatched
```

不能仅凭 state 猜测。

checkpoint commit + push。

---

## Phase 4 — 一次右 Alt 停止和焦点保护

### 幂等停止

每个 session 增加：

```text
stop_request_latched
```

规则：

- 主 hook 和 fallback 谁先提交，谁生效；
- 后续 stop request 全部 no-op；
- recording_stopping ACK 只能发一次；
- 目标延迟：按下第二次 RAlt 后 <100ms 发出停止 ACK。

### RAlt watcher

- watcher 监听下一次物理 RAlt 的 down edge；
- 捕获后先提交幂等 stop request，不等待完整 down→up 才给用户反馈；
- 仍可在 up edge 做诊断和清理；
- 不能把开始录音的那次 RAlt 误当停止；
- 不能因主 hook 和 fallback 双触发造成双 stop。

### Keyboard helper

在 CAPTURING 时，作为 SayIt 热键的 RAlt 事件必须被吞掉，避免传给前台软件激活菜单或丢失 caret。

不得吞掉非录音状态下普通 Alt 行为。

### 焦点快照

记录：

```text
recording_start_focus
stop_key_focus_before_alt_side_effect
injection_time_focus
```

规则：

- 用户主动切换到新的有效输入框：使用新输入框；
- 若仅因为本次 RAlt 菜单副作用短暂失焦，可恢复“停止键按下前刚验证过的同一 focused control”；
- 不恢复更早 captured stale target；
- control identity 必须仍有效；
- 不恢复到 SayIt 自己的窗口。

测试：

- 1、5、15、30 分钟模拟长录音一次停止；
- hook miss fallback 一次停止；
- 主 hook + fallback race 只停止一次；
- Alt 不激活菜单；
- stop 前输入框在注入时仍被正确识别；
- 用户主动切换输入框不被拉回旧控件。

checkpoint commit + push。

---

## Phase 5 — AI 超时、Pipeline watchdog 和降级

### AI deadline

- AI 整理独立 deadline，默认 25 秒，可配置 15–45 秒；
- 不能依赖 httpx 60 秒总超时让 UI 长期“思考中”；
- 超时/网络失败/无 provider 时，使用 `locally_refined_text` 继续注入；
- 发出明确 `ai_degraded` 或结构化错误事件；
- 条形悬浮窗提示：“AI 整理超时，已使用识别结果”；
- 不再次提交同一 AI 请求；
- 不重复注入。

### Pipeline stage watchdog

- 每个阶段记录进入时间；
- AI 阶段超过 deadline 后必须收口；
- finally 必须恢复 pipeline mutex、stop watcher 和 UI 状态；
- 任何 Python 异常都必须发 session-scoped pipeline_error。

测试：

- AI timeout；
- provider HTTP error；
- provider invalid response；
- AI 返回空文本；
- 上述情况均继续使用本地文字且只注入一次。

checkpoint commit + push。

---

## Phase 6 — Backend 崩溃监管和恢复

Electron 增加 backend supervisor：

- 区分用户主动退出与异常退出；
- 记录 exit code、signal、active session、runtime stage；
- 异常退出立即让悬浮窗退出“思考中”；
- 显示：“后台异常，SayIt 正在恢复”；
- 写入 rotating crash report，不记录完整输入正文和 API key；
- Python 启用 `faulthandler` 写独立 crash 文件；
- 非用户主动退出时最多自动重启一次；
- 重启带短暂 backoff，防 crash loop；
- 重启成功后恢复 idle；
- 不自动重放录音；
- 不自动重新处理文本；
- 不自动再次注入；
- 有安全 history 时仅提示从历史恢复。

测试/harness：

- backend exit code != 0；
- backend signal exit；
- restart success；
- restart failure 不循环；
- UI 不停留“思考中”；
- 无重复注入。

checkpoint commit + push。

---

## Phase 7 — 全量回归和自审

必须运行：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

新增并运行：

- result-card geometry/session harness；
- ResultCardEligibility tests；
- RAlt stop race/latency tests；
- AI timeout/fallback tests；
- backend supervisor harness；
- clipboard preservation regression；
- SilentMonitor verified-only regression。

创建：

```text
.ai/ROUND9_SELF_REVIEW.md
```

逐项回答：

```text
结果卡片尺寸
结果卡片位置
跨 session 清理
严格弹出资格
一次 Alt 停止
焦点保护
AI 超时降级
backend crash 恢复
不重复注入
剪贴板保护
静默学习门禁
```

每项写：

```text
PASS / FAIL
实现位置
测试名称
剩余风险
```

任何 P0 FAIL 不得结束。

更新：

```text
.ai/ZCODE_REPORT.md
.ai/TEST_RESULTS.md
.ai/PROJECT_STATE.md
.ai/CURRENT_TASK.md
```

成功终态必须为：

```text
BLOCKED_USER_VALIDATION
```

最终报告必须填写每个 checkpoint 完整 SHA 和最终远端 HEAD SHA。
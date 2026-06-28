# Current Task

> 最后一次更新：2026-06-27

## 状态

**READY**

## 执行器

本轮只允许：

```text
SayIt Agent Bridge v0.2.2 → Claude Code CLI
```

不要同时启动 ZCode 或第二个 Bridge。

## 当前任务起点

发布 Round 9 任务的提交：

```text
698b735157fc4fd23122545c06270b2b393dee24
```

开始执行后，以 `git pull --ff-only` 后的真实 HEAD 为准。

## 必须读取

```text
AGENTS.md
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_RUNTIME_STABILITY_BUGFIX_PLAN.md
.ai/ROUND9_LONG_TASK.md
.ai/ROUND8_SELF_REVIEW.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
```

其中：

```text
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_LONG_TASK.md
```

是本轮最高优先级。

## 唯一目标

修复实机验收暴露的运行时问题：

1. 结果卡片缩小并动态高度；
2. 结果卡片定位到条形悬浮窗真实可见区域上方；
3. 使用 recording_session_id 隔离每次录音，清除旧 payload、timer 和卡片；
4. 大结果卡片只在无有效输入焦点、没有发送注入动作、没有输入文字时出现；
5. attempted_unverified 不弹大卡片，只做条形悬浮窗轻提示；
6. 长录音第二次右 Alt 按一次立即停止；
7. Alt 热键不传给前台软件，不激活菜单、不丢失输入焦点；
8. stop request 幂等，主 hook 和 fallback 不重复停止；
9. AI 超时/失败降级到本地整理文本，不永久卡在“思考中”；
10. backend 异常退出后 UI 恢复、生成脱敏诊断、最多受控重启一次；
11. 崩溃后不自动重放、不重复处理、不重复注入；
12. 保留剪贴板保护和 verified-only SilentMonitor 门禁。

## 执行方式

严格按照：

```text
.ai/ROUND9_LONG_TASK.md
```

Phase 0 到 Phase 7 连续自主执行。

每个 Phase：

```text
先写失败测试
→ 修实现
→ 跑定向测试
→ 跑回归
→ checkpoint commit
→ push 当前 feature 分支
```

不向用户询问普通实现细节。遇到方案选择时，优先：

```text
不丢文字
不重复输入
不破坏剪贴板
不抢错误焦点
不把不确定当成功
```

## 禁止事项

- 不修改 main、backup/*、稳定 tag；
- 不 force push、reset --hard、git clean；
- 不读取或修改真实用户数据库、历史、词典、录音、正文、日志正文、API key；
- 不删除或弱化失败测试；
- 不通过恢复录音开始时的 stale target 解决焦点问题；
- 不开发微信登录、安装下载、升级、群聊、订阅、场景化写作和个人表达学习；
- 不自动重放录音；
- 不自动重复注入。

## 完成条件

必须运行：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

必须创建：

```text
.ai/ROUND9_SELF_REVIEW.md
```

必须更新：

```text
.ai/ZCODE_REPORT.md
.ai/TEST_RESULTS.md
.ai/PROJECT_STATE.md
.ai/CURRENT_TASK.md
```

成功终态：

```text
BLOCKED_USER_VALIDATION
```

不要写 DONE。最终报告填写所有 checkpoint 完整 SHA 和真实远端 HEAD SHA，commit 并 push。
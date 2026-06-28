# Current Task

> 最后一次更新：2026-06-28

## 状态

**ZCODE_READY**

---

## 当前结论

ChatGPT 已基于远端真实代码完成 Round 9.2 独立复核。

```text
审查基线：a5912b67abdf78d762a104e7964e1fbadeb5aa82
独立审查：.ai/ROUND9_3_P0_INDEPENDENT_REVIEW.md
修复任务：.ai/ROUND9_3_P0_FIX_TASK.md
```

Round 9.2 **尚未真正完成**，仍存在会阻塞用户实机验收的 P0 问题：

1. 前端 watchdog 从录音开始计时，正常录音超过 2 分钟会被误判异常；
2. `asr_total_budget_s` 没有真实约束 batch cascade 和每个 ASR engine；
3. Streaming `abort()` 仍可能被 SDK `stop()` 永久阻塞，`finish()` 也可能遗留卡死线程；
4. 输入框判断仍把“无法证明可编辑”当作“确定没有输入框”，Chrome、Obsidian、微信、飞书仍可能零注入并错误弹大卡片；
5. terminal 契约、WebSocket 断开复位和生产代码测试覆盖仍不完整。

因此：

```text
暂停用户实机验收
不得进入发布功能
不得重复执行 Round 9.2
```

---

## 执行器

```text
ZCode GUI → Claude Code
```

Agent Bridge 保持关闭。不要同时启动 Bridge 和 ZCode。

---

## 开始前必须读取

```text
AGENTS.md
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_3_P0_INDEPENDENT_REVIEW.md
.ai/ROUND9_3_P0_FIX_TASK.md
```

---

## 唯一任务

严格执行：

```text
.ai/ROUND9_3_P0_FIX_TASK.md
```

必须先建立调用生产代码的失败测试，再修实现。

重点完成：

- watchdog 只在 `recording_stopping` 后启动，5 分钟正常录音不得误报；
- streaming `finish()` 和 `abort()` 都有真实总 deadline，不遗留无上限后台线程；
- ASR 总预算覆盖 streaming、所有 batch engine 和本地 fallback；
- 输入目标只保留 `editable_verified / editable_probable / no_editable_verified` 三态；
- 只有真正无输入目标且零 dispatch 才弹大卡片；
- 每个 session 严格一个 terminal，所有 outcome 都让前端退出“思考中”；
- WebSocket 断开也必须结束视觉等待；
- 不重复注入，不破坏文本、图片、文件和多格式剪贴板；
- SilentMonitor 仍只在 `verified_success + target_verified` 后启动；
- 补齐右 Alt 脱敏事件计数，但先证明再改状态机。

---

## 禁止事项

- 不修改或合并 main；
- 不修改 `backup/*`、commit `0d69a98` 或 tag `local-working-2026-06-25`；
- 不 force push、reset --hard、git clean；
- 不读取或修改真实用户数据库、词典、历史、录音正文和 API Key；
- 不提交开发密钥；
- 不开发安装包、更新、微信登录、账号、群聊、订阅、场景化写作或个人表达习惯学习；
- 不用 UI watchdog 掩盖后台死锁；
- 不用自动复制、自动重试或第二次注入掩盖失败；
- 不把测试中重写的模拟逻辑宣称为生产代码覆盖。

---

## 成功终态

完成所有生产修复、真实门禁、自审文档和提交后，状态改为：

```text
BLOCKED_USER_VALIDATION
```

必须创建：

```text
.ai/ROUND9_3_SELF_REVIEW.md
```

填写所有 checkpoint 完整 SHA 和最终远端 HEAD，commit 并 push。不要写 `DONE`。

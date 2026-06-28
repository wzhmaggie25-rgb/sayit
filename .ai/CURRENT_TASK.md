# Current Task

> 最后一次更新：2026-06-28

## 状态

**ZCODE_READY**

## 结论

Round 9.1 用户实机验收失败，确认存在P0主链路故障：

```text
右Alt停止后长期停在“思考中”
后台仍在识别/处理
悬浮条不消失
文字不注入
结果卡片为空
有输入框可能被误判为无输入目标
```

当前不得继续验收、不得合并main、不得创建release分支。

## 已确认根因

1. Pipeline未捕获异常只写日志，不emit终态，Float永久STOPPING；
2. Streaming ASR `finish()`使用无timeout的阻塞`queue.put(None)`，worker退出/queue满时可永久卡死；
3. Result card首次加载前，`pipeline_done`会清空pending payload，导致空卡片；
4. Editability gate只认Win32 Edit/ValuePattern，Chrome/Obsidian/微信/飞书等真实输入框可能误判`no_editable_target`；
5. `target_is_sayit_window`被硬编码False；
6. 缺少“每个session恰好一个terminal事件”的强制契约；
7. Streaming + batch + AI多层timeout会叠加成很长等待。

## 执行器

```text
ZCode GUI → Claude Code
```

Agent Bridge保持关闭。

## 必须读取

```text
AGENTS.md
.ai/PRODUCT_REQUIREMENTS_BASELINE.md
.ai/ROUND9_2_P0_RUNTIME_BUG_REVIEW.md
.ai/ROUND9_2_P0_FIX_TASK.md
.ai/ROUND9_1_SELF_REVIEW.md
```

其中：

```text
.ai/ROUND9_2_P0_RUNTIME_BUG_REVIEW.md
.ai/ROUND9_2_P0_FIX_TASK.md
```

优先级最高。

## 唯一任务

严格执行：

```text
.ai/ROUND9_2_P0_FIX_TASK.md
```

Phase A 到 Phase I 连续自主完成。

必须：

- 先建立真实失败复现；
- 修Streaming finish无界阻塞；
- 建立session terminal事件；
- 任意Pipeline异常都让前端退出“思考中”；
- 修复result-card show→done→load空文字竞态；
- 修复真实contenteditable输入框误判；
- 只有真正无焦点且零dispatch才弹大卡片；
- 建立ASR总预算；
- 记录脱敏stage/session/hotkey诊断；
- 不重复注入、不自动重试。

## 禁止事项

- 不修改main、backup/*、稳定tag；
- 不force push、reset --hard、git clean；
- 不读取或修改真实用户数据库、历史、词典、录音、正文、API key；
- 不开发安装、更新、微信登录、群聊、订阅、场景写作；
- 不用UI watchdog掩盖后端永久阻塞；
- 不通过自动复制或重复注入掩盖失败；
- 不盲目修改Alt状态机，先用运行时事件计数证明问题。

## 完成门禁

必须原样运行且0 failures：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
node frontend/_test_result_card_race.js
```

必须创建：

```text
.ai/ROUND9_2_SELF_REVIEW.md
```

成功终态：

```text
BLOCKED_USER_VALIDATION
```

不要写DONE。填写所有checkpoint完整SHA和最终远端HEAD，commit并push。

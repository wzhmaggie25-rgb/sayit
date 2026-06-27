# Current Task

> 最后一次更新：2026-06-27（Round 6 完成）

## 状态

**DONE**

## 完成总结

Round 6 Typeless 稳定化全部 12 项交付完成。详见：

- `.ai/CC_SELF_REVIEW.md` — 逐项 P0/P1 自审，全部 PASS。
- `.ai/ZCODE_REPORT.md` — 实施过程、根因、文件、命令、风险。
- `.ai/TEST_RESULTS.md` — 213 passed / 1 skipped / 6 subtests，新增 40 用例。

主要 checkpoint commits（已 push 到 `origin/feature/silent-learning-stabilization`）：

- `b37026e` Phase 1: Native HTML result card
- `1a31cc9` Phase 2: Clipboard snapshot protection
- `e2536ed` Phase 3+4: Real readback + state machine + SilentMonitor gating
- `9876412` Phase 5: Hotword promotion

可交付用户实机验收。

## 历史原始任务（仅作存档）



## 执行方式

本任务只由：

```text
SayIt Agent Bridge v0.2.0 → Claude Code CLI
```

自动执行。

不要由 ZCode、旧 Agent Bridge 实例或其他执行器同时修改本地目录。

## 唯一目标

把当前 `feature/silent-learning-stabilization` 分支推进到：

> Typeless 风格结果卡片、真实注入 readback、完整剪贴板保护、正确的注入状态/历史/SilentMonitor 路由，以及重复纠错提升个人热词全部完成并通过自主代码审查，可以交给用户做最终实机验收。

## 强制任务文件

开始后必须完整执行：

```text
.ai/CLAUDE_LONG_TASK.md
```

并以以下文件作为缺陷和产品事实依据：

```text
.ai/ROUND5_CODE_REVIEW.md
.ai/CURRENT_TASK_OVERRIDE.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
```

## 基线

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 待修复实现提交：`bff31037d6992b421c60f91d41a515e1565a16ce`
- 稳定备份：`0d69a98`
- 稳定 tag：`local-working-2026-06-25`
- 本地目录：`D:\code\sayit_zcode`

## 不得缩减的交付范围

1. 修复结果卡片无法离线运行和首次 payload 丢失；
2. 复制改为可信 Electron IPC；
3. verified 只来自目标控件 readback；
4. 增加 attempted_unverified，禁止不可验证后的盲目二次输入；
5. 空剪贴板恢复为空；
6. 图片、文件、HTML、RTF、多格式剪贴板不得被破坏；
7. 无可编辑目标时不强抢旧输入框，保留原剪贴板并显示大结果卡片；
8. 结果卡片展示两层文字、复制按钮、绿色勾和右上角关闭；
9. no target/unverified/failed 不启动 SilentMonitor；
10. 完成两个不同 history 后的重复纠错安全提升个人热词；
11. 保留 RAltStopWatcher、ABI v3、快速停录和现有 ASR/AI 功能；
12. 完成全量测试、前端静态检查、离线 smoke test和逐项自审。

不得再次把 hotword promotion 推迟到下一轮。

## 自主执行要求

- 不向用户询问普通实现细节；采用最保守、最不丢数据、最不重复输入的方案；
- 按 `.ai/CLAUDE_LONG_TASK.md` 分阶段执行；
- 每阶段测试通过后 checkpoint commit 并 push；
- 任何 P0 或验收项未通过就继续修；
- 不得只凭“测试数量增加”宣布完成；
- 不读取或修改用户真实数据库、词典、历史、录音、日志正文和凭据；
- 不修改 `main`、`backup/*` 或稳定 tag；
- 不 force push、reset --hard、git clean；
- 不删除失败测试。

## 完成条件

必须同时满足：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
result-card 离线 smoke test通过
.ai/CC_SELF_REVIEW.md 所有 P0 = PASS
```

并更新：

```text
.ai/ZCODE_REPORT.md
.ai/TEST_RESULTS.md
.ai/PROJECT_STATE.md
.ai/CC_SELF_REVIEW.md
```

最终：

- 成功：状态改为 `DONE`，commit 并 push；
- 真正外部阻塞：状态改为 `BLOCKED`，保存已通过 checkpoint，commit 并 push；
- 最终输出结构化 JSON 和真实远端 HEAD SHA。

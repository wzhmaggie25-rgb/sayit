# Current Task

> 最后一次更新：2026-06-27

## 状态

**ZCODE_READY**

## 结论

Round 7 长任务有明显进展，但未通过 ChatGPT 代码审查，暂时不得进入用户实机验收。

当前实现 HEAD：

```text
a0e5ae667a23ecd3336c48637d42f7aad8e76254
```

## 执行器

本轮继续使用：

```text
ZCode GUI → Claude Code
```

原因：Bridge v0.2.1 仍未把 `BLOCKED_USER_VALIDATION` 识别为成功终态，且未实际校验 task start 后有新 commit。修复到 v0.2.2 后，后续长任务再恢复优先使用 Bridge。

运行时 Agent Bridge 必须保持关闭，不同时启动其他执行器。

## 唯一目标

完成 Round 8 最终安全收口：

> 完全移除破坏性 SetValue/WM_SETTEXT 通用路径，实现真实 focused control + selection-aware insertion；统一 pre/selection/post readback；修复 clipboard 事实传播、同 history 幂等、promotion sync 语义、IPC sender 校验和 Bridge 成功终态。

## 最高优先级文件

必须依次读取：

```text
.ai/ROUND7_CODE_REVIEW.md
.ai/ROUND8_LONG_TASK.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
.ai/ROUND6_CODE_REVIEW.md
.ai/ROUND7_SELF_REVIEW.md
```

其中 ROUND7_CODE_REVIEW 和 ROUND8_LONG_TASK 覆盖此前自审 PASS 结论。

## 必须修复

1. 删除通用 UIA ValuePattern.SetValue；
2. 删除通用 WM_SETTEXT；
3. Win32 只对真实 focused control 使用 selection-aware insertion；
4. UIA/Win32 verified 都必须有 pre + selection/caret + post 证据；
5. pre 不可读时不得 substring verified；
6. GetGUIThreadInfo + read-only/keyboard-focusable 可编辑判断；
7. unknown/0 hwnd 不得盲目注入；
8. clipboard restore 事实贯穿所有 failure 退出路径；
9. 同 history 重放不得增加 confidence/match_count；
10. promotion 不得绕过 HotwordsManager/ASR sync；
11. result-card IPC 校验 sender；
12. Bridge v0.2.2 支持 DONE 与 BLOCKED_USER_VALIDATION 两个成功终态，并实际验证新 commit。

## 完成条件

- ROUND7_CODE_REVIEW 所有 P0/P1 均真实修复；
- 通用 injector 代码搜索不存在 SetValue、WM_SETTEXT、DocumentRange.Select 和 substring verified；
- 全量 Python 测试、Node check、result-card smoke 全通过；
- 创建 `.ai/ROUND8_SELF_REVIEW.md`；
- 每 Phase checkpoint commit + push；
- 最终真实完整 SHA 写入报告。

成功终态：

```text
BLOCKED_USER_VALIDATION
```

不要直接写 DONE。
# Current Task

> 最后一次更新：2026-06-27

## 状态

**ZCODE_READY**

## 结论

Round 6 未通过 ChatGPT 代码审查，暂时不得进入用户实机验收。

Claude Code 的主要实现提交：

```text
9876412cc97e91ee859abfab8d78d354de21b5a2
```

Bridge 后续因 stdout JSON 解析失败，将原 DONE 机械改成 BLOCKED；这不代表代码没有完成，但 Bridge 完成判定本身也必须在本轮修复。

## 执行器

本轮先使用：

```text
ZCode GUI → Claude Code
```

原因：当前 Bridge v0.2.0 会把真实 DONE 错改为 BLOCKED。本轮 Phase 0 先将 Bridge 修到 v0.2.1；完成后，后续长任务恢复优先使用 Bridge。

运行本轮时：

- Agent Bridge 必须关闭；
- 不同时启动第二个代码执行器；
- 只在当前 feature 分支工作。

## 唯一目标

完成 Round 7：

> 将输入行为改为当前焦点、非破坏性、真实 readback；确保剪贴板恢复状态与事实一致；确保自动个人热词只在两个不同 history 后提升；修复 Bridge 完成判定；通过全量测试后交给用户实机验收。

## 最高优先级文件

开始后必须依次读取：

```text
.ai/ROUND6_CODE_REVIEW.md
.ai/ROUND7_LONG_TASK.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
.ai/CURRENT_TASK_OVERRIDE.md
.ai/ROUND5_CODE_REVIEW.md
```

其中：

```text
.ai/ROUND6_CODE_REVIEW.md
.ai/ROUND7_LONG_TASK.md
```

覆盖此前 `.ai/CC_SELF_REVIEW.md` 中的 PASS 结论。

## 必须修复

1. 不再强制恢复录音开始时的 stale target；
2. 禁止通用 WM_SETTEXT / ValuePattern.SetValue / DocumentRange.Select 覆盖已有内容；
3. UIA 动作可能已生效但不可验证时，不得继续 clipboard paste；
4. verified 必须验证本次插入的 pre/post diff，不能只做 substring；
5. reliable unchanged 必须是 injection_failed；
6. clipboard restore 失败不得宣称 preserved/restored；
7. attempted_unverified 结果卡片必须警告可能已输入，避免重复粘贴；
8. 删除单次 edit 直接加入个人词典的绕行入口；
9. 同一 history 重放不得增加 match_count/confidence；
10. 2 vs 1 冲突不得提升，同 pattern 不得自动提升第二个冲突词；
11. 结构化 injection state 贯穿 Pipeline/EventBus/WebSocket/History；
12. Bridge v0.2.1：兼容 BOM、noisy JSON、不得覆盖真实 DONE。

## 交付状态

全部代码和自动化测试通过后：

```text
BLOCKED_USER_VALIDATION
```

不要直接写 DONE，因为仍需用户在真实 Windows 应用中验证。

## 安全边界

- 不修改 main、backup/*、稳定 tag；
- 不 force push、reset --hard、git clean；
- 不读取/修改真实用户数据库、词典、历史、录音、日志正文或凭据；
- 不删除或弱化测试；
- 每 Phase 测试通过后 checkpoint commit + push；
- 最终报告必须填写真实完整 SHA。
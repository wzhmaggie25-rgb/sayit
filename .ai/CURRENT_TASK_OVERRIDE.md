# Current Task Override

> 日期：2026-06-27
> 状态：**ZCODE_READY**
> 优先级：本文件覆盖 `.ai/CURRENT_TASK.md` 中与 Typeless、剪贴板 fallback、无输入目标 UI 相冲突的描述。

## 最新运行时事实

请先阅读：

```text
.ai/TYPELESS_RUNTIME_VALIDATION.md
```

用户已经完成 Typeless 人工黑盒验证：

- 当当前光标不在可编辑输入框内时，Typeless 弹出大结果悬浮窗；
- 大窗展示最近转录信息和本次语音结果预览；
- 长内容尾部省略；
- 下方有复制按钮，右上角有关闭按钮；
- 大窗出现时不修改原剪贴板；
- 用户点击复制后才写入语音结果；
- 点击后按钮左侧出现绿色勾，随后窗口消失。

## 本轮修订目标

### 1. 新增 `no_editable_target` 状态

当 ASR/AI 已得到非空 final_text，但没有有效可编辑输入控件时：

- 不归类为 recognition_failed；
- 不自动覆盖剪贴板；
- 保存历史；
- 显示大结果卡片。

### 2. 新增大结果卡片

至少包含：

- 最近转录信息；
- final_text 预览；
- 长文本安全省略或滚动；
- 复制按钮；
- 关闭按钮；
- 复制成功绿色勾；
- 复制成功后自动关闭。

不得复用 86×34px 小浮窗硬塞全文。

### 3. 剪贴板规则

`no_editable_target`：

- 打开结果卡片时保持用户原剪贴板；
- 只有用户点击复制才写入 final_text；
- 复制成功后显示绿色勾并关闭卡片。

`verified_success`：

- 保持/恢复用户原剪贴板；
- 不弹结果卡片。

`injection_failed_with_valid_target`：

- 先与 `no_editable_target` 分开建模；
- 本轮可复用结果卡片作为安全兜底，但不得声称这是已验证的 Typeless 行为；
- 避免自动多路径重复注入。

`recognition_failed`：

- 只有没有产出 final_text 时才使用。

### 4. 仍需继续完成的旧任务

在不与上述规则冲突的前提下，继续：

- 删除 clipboard-consumed 假验证；
- 基于目标控件 readback 判断 verified success；
- 完成重复纠错跨不同 history 安全提升为个人热词；
- 保留 RAltStopWatcher 和快速停录修复；
- 修正报告中的真实提交 SHA。

## UI 交互要求

结果卡片：

- 默认不抢焦点；
- 不使用阻塞式模态对话框；
- 可通过右上角关闭；
- 点击复制必须真实调用 clipboard 写入；
- 复制成功后显示绿色勾；
- 短暂反馈后关闭；
- 关闭前后历史都应保留 final_text；
- 不记录用户全文到日志。

## 必须增加的测试

- 无可编辑目标 + final_text 非空 -> result card；
- result card 打开时原剪贴板不变；
- 点击复制后剪贴板变为 final_text；
- 复制成功显示绿色勾并关闭；
- 点击关闭不修改剪贴板；
- no_editable_target 不显示识别失败；
- 历史保存为识别成功但无输入目标；
- verified_success 不弹卡片；
- 长文本预览安全省略/滚动；
- 结果卡片不抢焦点；
- 原有 RAlt、注入、学习测试通过。

## 完成要求

- 修改 SayIt 产品代码；
- 更新相关测试；
- 更新 `.ai/ZCODE_REPORT.md`、`.ai/TEST_RESULTS.md`、`.ai/PROJECT_STATE.md`；
- 使用真实提交 SHA；
- commit 并 push 当前 feature 分支；
- 完成后状态改为 `BLOCKED_USER_VALIDATION`。

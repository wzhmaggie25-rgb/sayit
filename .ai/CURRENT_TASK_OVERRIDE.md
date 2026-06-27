# Current Task Override

> 日期：2026-06-27
> 状态：**ZCODE_READY**
> 优先级：本文件覆盖 `.ai/CURRENT_TASK.md` 中与 Typeless、剪贴板 fallback、无输入目标 UI 相冲突的描述。

## 最高优先级澄清：Typeless 不会在正常语音输入后自动复制

用户进一步明确：

> **Typeless 完成语音输入后，默认不会把识别文字放进系统剪贴板。**

必须准确理解为：

1. 光标位于有效输入框，文字成功输入：
   - 文字进入输入框；
   - 不把 final_text 留在剪贴板；
   - 用户原剪贴板最终保持不变；
   - 不弹大结果卡片。

2. 光标不在有效输入框：
   - 不自动把 final_text 写入剪贴板；
   - 保留用户原剪贴板；
   - 弹出大结果卡片；
   - 只有用户主动点击“复制”，final_text 才进入剪贴板。

3. 因此，以下理解是错误的：

```text
每次识别结束都自动复制
```

以及：

```text
无输入框时先自动复制，再提供复制按钮
```

4. 如果注入实现内部临时借用剪贴板完成 Ctrl+V：
   - 这只是内部瞬时传输通道；
   - 成功后必须恢复用户原剪贴板；
   - 对用户而言不能产生“识别结果被自动复制”的最终效果。

5. `copy_result_to_clipboard` 如保留为可选配置，默认必须为 `false`；本轮不应默认开启，也不能用它模糊上述产品行为。

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
- 点击后按钮左侧出现绿色勾，随后窗口消失；
- 光标在正常输入框并完成输入时，没有自动复制动作。

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

### 3. 全局剪贴板规则

#### `verified_success`

- final_text 成功进入目标输入框；
- 不把 final_text 留在剪贴板；
- 如内部临时写入剪贴板，必须恢复用户原剪贴板；
- 不弹结果卡片。

#### `no_editable_target`

- 打开结果卡片时保持用户原剪贴板；
- 不自动复制 final_text；
- 只有用户点击复制才写入 final_text；
- 复制成功后显示绿色勾并关闭卡片。

#### `injection_failed_with_valid_target`

- 与 `no_editable_target` 分开建模；
- 不得默认自动把 final_text 留在剪贴板；
- 本轮可复用结果卡片作为 SayIt 的安全兜底，让用户主动复制；
- 不得声称这是已验证的 Typeless 行为；
- 避免自动多路径重复注入。

#### `recognition_failed`

- 只有没有产出 final_text 时才使用；
- 不得把旧的 final_text 或错误提示文字写入剪贴板。

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
- 点击关闭不得修改剪贴板；
- 关闭前后历史都应保留 final_text；
- 不记录用户全文到日志。

## 必须增加的测试

### 正常输入

- verified_success 后 final_text 不留在剪贴板；
- 原剪贴板为空时恢复为空；
- 原剪贴板为文本时精确恢复；
- 原剪贴板为支持的非文本/多格式时不被静默覆盖；
- verified_success 不弹结果卡片。

### 无输入目标

- 无可编辑目标 + final_text 非空 -> result card；
- result card 打开时原剪贴板不变；
- 不点击复制时 Ctrl+V 仍得到原剪贴板内容；
- 点击复制后剪贴板才变为 final_text；
- 复制成功显示绿色勾并关闭；
- 点击关闭不修改剪贴板；
- no_editable_target 不显示识别失败；
- 历史保存为识别成功但无输入目标；
- 长文本预览安全省略/滚动；
- 结果卡片不抢焦点。

### 其他回归

- 不存在任何“每次识别后自动复制”的默认路径；
- `copy_result_to_clipboard` 默认 false；
- 原有 RAlt、注入、学习测试通过。

## 完成要求

- 修改 SayIt 产品代码；
- 更新相关测试；
- 更新 `.ai/ZCODE_REPORT.md`、`.ai/TEST_RESULTS.md`、`.ai/PROJECT_STATE.md`；
- 使用真实提交 SHA；
- commit 并 push 当前 feature 分支；
- 完成后状态改为 `BLOCKED_USER_VALIDATION`。

# Typeless 静态审计复核

> 日期：2026-06-27
> 复核对象：`.ai/TYPELESS_AUDIT_REPORT.md`
> 状态：**BLOCKED_USER_RUNTIME_VALIDATION**

## 总结

本次 ZCode 已正确检查本机 Typeless 安装，并将报告提交到 GitHub。报告中的安装结构和静态资源证据有价值，也明显支持用户关于“大结果悬浮窗 + 复制按钮”的记忆。

但是，当前仍然只有**静态分析**，没有完成注入失败场景的运行时黑盒复现。以下内容不能视为已验证事实：

1. `interactive-card` 是否专门由“文本注入失败”触发；
2. 注入失败时它是否一定自动弹出；
3. 卡片展示的是本次听写最终文本，还是更通用的 AI answer；
4. `copy-button` 是否属于该失败卡片的最终文字复制操作；
5. 不点击复制时 Typeless 是否已经自动修改剪贴板；
6. “点击重试”是否为真实可见按钮，还是浮动栏提示区域本身可点击；
7. 卡片是否抢焦点、何时关闭、是否可滚动；
8. 失败结果是否仍保存到历史。

## 已验证的事实

### [安装结构]

- 本机存在 `C:\Users\46136\AppData\Local\Programs\Typeless\Typeless.exe`；
- 文件/产品版本显示为 1.8.0；
- 应用采用 Electron；
- 安装资源中存在 `interactive-card.html` 和 `floating-bar.html` 两个独立渲染页面；
- 存在 `page:open-interactive-card`、`page:close-interactive-card`、`page:get-interactive-card-payload`、`page:update-interactive-card-bounds` 等 IPC 名称；
- 相关资源中存在 `copy-button` 样式和 copy/copied tooltip 字符串；
- 存在“无法完成写作。点击重试继续。”等错误提示字符串。

### [GitHub 交付]

- ZCode 已创建 `.ai/TYPELESS_AUDIT_REPORT.md`；
- 实际提交：`d2766aab5946afae9e631990d701b9bfb49bf020`；
- 该提交仅新增审计报告，没有修改 SayIt 产品代码，也没有提交 Typeless 解包资源。

## 报告中需要降级表述的地方

### 1. “注入失败 UI = 大结果窗口 + 复制按钮”尚未验证

静态证据只能证明：

- 应用存在 interactive-card；
- 应用存在复制 UI；
- 应用存在错误提示。

尚未证明三者属于同一条“注入失败”运行路径。

### 2. “Typeless 让用户手动复制的 philosophy”属于推测

在不知道失败时是否自动写入剪贴板之前，不能断言 Typeless 选择了“手动复制而非自动复制”。

### 3. “重试按钮存在”尚未验证

错误字符串中的“点击重试”不等于已经确认卡片上存在独立按钮。可能是浮动栏整体可点击，也可能触发重新听写，而非重新注入。

### 4. transcription error 不等于 injection failure

`transcription_error` / `transcription_timeout` 更可能描述语音识别或生成阶段失败。不能仅凭这些字符串证明文本已生成但注入目标失败。

### 5. 数字签名表述需谨慎

报告记录了 `CompanyName = GitHub, Inc.` 和“数字签名有效”，但没有列出实际签名证书的 Subject/Issuer。不得把这两项直接合并成“由 GitHub, Inc. 签名”，除非证书字段明确支持。

## 当前产品决策门禁

在用户完成一次真实 Typeless 运行时验证前：

- 不得把 Typeless 的失败行为写成已确认事实；
- 不得基于本报告直接决定“失败时自动复制”或“仅点击复制”；
- 不得按旧 `.ai/CURRENT_TASK.md` 中的 Typeless 假设直接开始注入 UI 开发；
- 可以继续修复与 Typeless 无关的明确缺陷，例如错误的 clipboard-consumed verification 和重复纠错热词提升，但不得把未验证的 Typeless UI 作为验收依据。

## 最短人工验证步骤

不需要安装监控脚本。

1. 打开 Windows 记事本，先在剪贴板放入哨兵文字：

   `TYPELESS_SENTINEL_20260627`

2. 在记事本输入区内启动 Typeless 录音；
3. 说一句无隐私测试语句；
4. **在结束录音之前**关闭记事本，使原目标窗口失效；
5. 再结束录音，让 Typeless 进入识别/注入流程；
6. 观察并记录：
   - 是否出现大结果悬浮窗；
   - 是否展示刚才的完整文字；
   - 有哪些按钮及确切文案；
   - 不点击复制时，按 `Ctrl+V` 是否仍粘贴哨兵；
   - 点击“复制”后，`Ctrl+V` 是否变成本次识别文字；
   - 大窗是否抢焦点、是否自动关闭；
   - 关闭后是否能在 Typeless 历史中找到结果。

注意：原报告中“等待识别完成后再关闭记事本、然后释放热键”的顺序可能不成立。对于按住说话/松开处理的流程，必须在结束录音前先让目标窗口失效。

## 用户反馈后

收到人工验证结果后：

1. 更新 `.ai/TYPELESS_AUDIT_REPORT.md` 的黑盒实测章节；
2. 修正 Typeless vs SayIt 对比表中的未验证结论；
3. 再决定 SayIt 的失败降级模式：
   - 自动复制 + 大结果窗；
   - 保留原剪贴板 + 用户点击复制；
   - 或两者的可配置组合。

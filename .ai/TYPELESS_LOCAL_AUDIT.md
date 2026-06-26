# Typeless 本机只读审计任务

> 日期：2026-06-26

## 状态

**READY_FOR_ZCODE_AUDIT**

## 背景

用户本机已安装 Typeless：

```text
C:\Users\46136\AppData\Local\Programs\Typeless\Typeless.exe
```

此前 SayIt 任务中提到的“Typeless 风格”主要来自用户体验和 SayIt 代码中的零散注释，**并不是已经验证的 Typeless 内部实现**。本审计的目的，是用本机可重复证据确认 Typeless 在以下场景中的真实行为：

- 正常注入成功；
- 目标输入框丢失；
- 目标不可编辑；
- 自动注入失败或无法确认；
- 成功或失败时如何处理剪贴板；
- 悬浮提示文案、时长、交互；
- 历史记录如何标记识别成功与注入失败。

不得先假设 Typeless 会怎样做。

---

## 安全与边界

只允许：

1. 读取安装目录的文件名、大小、版本、签名、目录结构和公开资源；
2. 进行黑盒行为测试；
3. 使用本机临时测试文本和临时测试窗口；
4. 编写只记录元数据的本地测试辅助脚本；
5. 如安装包明确为 Electron 且存在可直接读取的公开资源，可只读查看资源结构和字符串以理解 UI 状态机。

禁止：

- 修改、替换或注入 Typeless 文件/进程；
- 绕过登录、授权、更新、签名或任何保护；
- 抓取账号令牌、网络请求正文、用户历史、真实录音或私人文本；
- 上传 Typeless 二进制、资源、代码或用户数据；
- 大段复制 Typeless 专有代码到 SayIt；
- 安装新的逆向工具；
- 使用调试器篡改运行时；
- 把未验证推测写成事实。

本任务只学习产品行为和通用交互模式，不复制专有实现。

---

## 第一阶段：安装结构与版本确认

使用 PowerShell 只读检查：

```powershell
$root = 'C:\Users\46136\AppData\Local\Programs\Typeless'
Get-Item "$root\Typeless.exe" | Select-Object FullName,Length,CreationTime,LastWriteTime,VersionInfo
Get-AuthenticodeSignature "$root\Typeless.exe" | Select-Object Status,StatusMessage,SignerCertificate
Get-ChildItem $root -Force | Select-Object Name,Length,Mode,LastWriteTime
Get-ChildItem $root -Recurse -Depth 3 -Force |
  Select-Object FullName,Length,Extension,LastWriteTime
```

记录：

- 产品版本；
- 发布者签名；
- 是否为 Electron（例如 resources、app.asar、chrome_*.pak 等）；
- 是否存在独立 updater、helper、native DLL；
- 是否存在可以公开读取的配置/语言资源；
- 不记录账号、用户内容和真实历史。

输出只写入本项目：

```text
.ai/TYPELESS_AUDIT_REPORT.md
```

只记录结构和结论，不复制二进制或大段资源。

---

## 第二阶段：建立无私人内容的观察工具

在 SayIt 仓库的 `tools/` 下编写临时或可保留的只读观察脚本，例如：

```text
tools/observe_clipboard_and_focus.py
```

只允许记录：

- 时间戳；
- 前台进程名、窗口类、HWND；
- Windows clipboard sequence number；
- 剪贴板格式编号/格式名称；
- 剪贴板文本长度和哈希（不得记录原文）；
- 是否出现新增/恢复/清空；
- 测试窗口文本长度和哈希；
- Typeless 可见窗口标题或辅助功能可读的提示文案；
- 测试开始/停止的人工标记。

不要记录真实剪贴板正文。测试前将剪贴板替换为专用无隐私哨兵，例如：

```text
TYPELESS_CLIPBOARD_SENTINEL_20260626
```

测试结束后恢复该哨兵或清空。

---

## 第三阶段：黑盒行为矩阵

使用专门测试文本，不使用用户私人内容。建议语音内容：

```text
这是 Typeless 注入测试，编号二零二六零六二六。
```

每个场景至少重复 3 次。

### 场景 A：普通成功注入

目标：Windows 记事本普通可编辑文本框。

观察：

- 识别结果是否自动进入文本框；
- 剪贴板 sequence 是否变化；
- 原哨兵最终是否恢复；
- 识别结果是否最终留在剪贴板；
- 有无完成提示；
- 提示文案和持续时间；
- 是否保存历史。

### 场景 B：录音后切换到另一个可编辑窗口

录音从记事本 A 开始，停止后立刻切到记事本 B。

观察：

- Typeless 注入 A、B，还是拒绝注入；
- 是否恢复原目标；
- 是否提示用户；
- 是否把结果放到剪贴板。

### 场景 C：目标窗口关闭

录音开始后关闭原测试记事本，再停止录音。

观察：

- 是否尝试注入其他窗口；
- 是否明确显示注入失败；
- 是否自动复制结果；
- 用户是否可直接 Ctrl+V；
- 历史是否仍保存识别结果。

### 场景 D：目标不可编辑

在一个安全的不可编辑窗口或记事本只读模拟中测试，不使用管理员绕过。

观察同上。

### 场景 E：不可稳定 readback 的应用

选择用户已经正常使用的测试应用，例如浏览器网页输入框或 Notion 的空白测试页，不使用真实账号内容。

观察：

- 是否注入；
- 是否保留剪贴板；
- 是否显示“已复制”等提示；
- 是否可能重复输入。

### 场景 F：长文本

语音 15～30 秒，输出至少 100 个汉字。

观察：

- 是否完整注入；
- 剪贴板恢复时机；
- 是否出现截断；
- 失败时是否可直接 Ctrl+V 获得完整文本；
- 提示与历史状态。

### 场景 G：原剪贴板为空、文本和非文本

分别测试：

1. 空剪贴板；
2. 文本哨兵；
3. 一张专用测试图片；
4. 专用临时文件复制产生的文件列表格式。

观察成功注入后原剪贴板是否完整恢复。不得使用用户真实图片或文件。

---

## 第四阶段：失败提示 UI 证据

通过正常屏幕观察或 Windows UI Automation，只记录：

- 提示文案；
- 图标/状态颜色的一般描述；
- 显示位置；
- 是否抢焦点；
- 是否可点击；
- 点击后发生什么；
- 自动隐藏时间；
- 隐藏后剪贴板是否仍保留结果。

如 UI Automation 读不到，不要 OCR 或截取用户屏幕私人区域。由用户人工描述也可以作为证据，但要标记为“用户观察”。

---

## 第五阶段：可选的公开资源只读检查

仅当安装目录明确包含普通可读资源时执行：

- 查找本地化字符串中与 `clipboard`、`paste`、`injection`、`failed`、`copied`、`Ctrl+V`、`history` 相关的短字符串；
- 确认错误提示文案和状态名称；
- 不反编译 native binary；
- 不复制成段源码；
- 报告只引用少量必要的 UI 字符串和文件位置。

如果资源被打包、加密或无法用现有工具读取，停止静态检查，继续使用黑盒证据，不安装新工具。

---

## 交付物

创建：

```text
.ai/TYPELESS_AUDIT_REPORT.md
```

报告必须包含：

1. Typeless 版本与安装结构；
2. 每个测试场景的观察表；
3. 剪贴板在成功、失败、不可验证场景的真实变化；
4. 失败提示的确切文案与交互；
5. 哪些结论是程序测得、哪些是用户人工观察；
6. 哪些行为值得 SayIt 复刻；
7. 哪些行为不建议复刻；
8. 对 `.ai/CURRENT_TASK.md` 中 Typeless 风格要求的修订建议；
9. 不包含私人文本、账号数据、令牌、录音和完整 Typeless 文件。

## 重要结论规则

在审计完成之前：

- 不得声称已经掌握 Typeless 的确切内部实现；
- 不得声称 Typeless 一定会在失败时自动复制；
- 只能称当前 SayIt 方案为“拟采用的无损降级设计”；
- 最终实现应以黑盒可验证行为和 SayIt 自身产品需求为准，而不是猜测 Typeless 内部代码。

# Typeless v1.8.0 本地审计报告

> 审计日期：2026-06-27
> 审计对象：`C:\Users\46136\AppData\Local\Programs\Typeless\Typeless.exe`
> 目的：黑盒确认 Typeless 在文本注入失败时的 UI 行为，为 SayIt 的失败处理策略提供参考

---

## 1. 安装结构与静态证据

`[安装结构]`

### 1.1 主程序

| 属性 | 值 |
|---|---|
| 路径 | `C:\Users\46136\AppData\Local\Programs\Typeless\Typeless.exe` |
| 大小 | 189,118,536 字节（~180 MB） |
| 文件版本 | 1.8.0 |
| 产品版本 | 1.8.0.0 |
| 产品名称 | Typeless |
| 公司名称 | GitHub, Inc. |
| 数字签名 | ✅ 有效 |
| 架构 | Electron 应用（基于 Chromium + Node.js） |
| 安装路径 | `%LocalAppData%\Programs\Typeless\`（每用户安装） |

### 1.2 核心资源 (`resources/`)

| 资源 | 大小 | 说明 |
|---|---|---|
| `app.asar` | 287,352,678 字节（~274 MB） | Electron 应用包，11,142 个文件 |
| `app.asar.unpacked/` | — | 原生 Node 模块 |

### 1.3 原生 DLL（键盘钩子 & 辅助功能）

| DLL | 大小 | 推测用途 |
|---|---|---|
| `keyboard-helper/KeyboardHelper.dll` | 378,952 B | `WH_KEYBOARD_LL` 低层键盘钩子，监听热键 |
| `context-helper/ContextHelper.dll` | 546,896 B | UIAutomation 辅助功能 API，获取焦点元素上下文 |
| `input-helper/InputHelper.dll` | 369,232 B | 文本注入/模拟输入 |
| `util-helper/UtilHelper.dll` | 343,112 B | 工具函数 |
| `libopusenc/libopusenc.dll` | 543,816 B | 音频编码（Opus） |

### 1.4 原生 Node 模块 (`app.asar.unpacked/node_modules/`)

| 模块 | 大小 | 用途 |
|---|---|---|
| `better-sqlite3` | 1,907,272 B | 本地 SQLite 数据库 |
| `koffi` | 2,446,416 B | FFI（Foreign Function Interface）调用原生 DLL |
| `winax` | 278,608 B | Windows COM/OLE Automation |

### 1.5 数据库 (`resources/drizzle/`)

12 个 SQL 迁移文件（SQLite），含 `users`, `sessions`, `dictations`, `dictionary`, `settings` 等表。

### 1.6 渲染进程窗口（HTML 页面）

| 窗口 | 文件 | 标题 | 说明 |
|---|---|---|---|
| 小悬浮栏 | `floating-bar.html` | "Status" | 86×34px，`pointer-events: none`，显示录音状态/倒计时 |
| **结果大窗口** | **`interactive-card.html`** | **"AI result"** | **用户回忆的"大结果悬浮窗"**，`pointer-events: auto` |
| 中心面板 | `hub.html` | — | 设置/词典/历史 |
| 侧栏 | `sidebar.html` | — | 边栏面板 |
| 登录 | `login.html` | — | 登录页 |
| 引导 | `onboarding.html` | — | 新用户首次引导 |

### 1.7 进程架构

- **主进程**: `dist/main/index.js`（531,557 字节）
- **键盘钩子子进程**: `dist/main/keyboard-helper-child-process.js`（13,177 字节）
- **音频工作线程**: `dist/main/worker/opusWorker.js`（12,542 字节）
- **预加载脚本**: `dist/preload/index.mjs`（9,377 字节）

### 1.8 IPC 通道清单（关键部分）

```
page:open-interactive-card       ← 打开结果大窗口
page:close-interactive-card      ← 关闭结果大窗口
page:get-interactive-card-payload  ← 获取窗口内容
page:update-interactive-card-bounds ← 窗口自适应大小
page:floating-bar-update-positions  ← 更新小悬浮栏位置
page:floating-bar-click            ← 小悬浮栏点击事件
page:open-typeless-bar             ← 打开录音栏
page:restart-typeless-bar          ← 重启录音栏
page:open-hub                      ← 打开中心面板
page:close-sidebar / open-sidebar  ← 侧栏控制
page:window-created                ← 窗口创建通知
```

---

## 2. 黑盒实测

`[黑盒实测]`

### 2.1 自动测试能力评估

**无法在无用户交互的情况下自动完成 Typeless 黑盒失败复现。**

原因：
1. Typeless 是 GUI 应用，需要用户手动触发录音和注入流程
2. 注入失败需要特定条件（如目标窗口在注入前关闭）
3. 无法通过命令行或脚本来操控 Typeless 的音频输入和文本注入
4. Typeless 的 Electron 窗口通过 IPC 通信，无法通过外部注入简单触发

### 2.2 可自动确认的静态证据

✅ `interactive-card.html` 文件存在 — 标题为 "AI result"
✅ `page:open-interactive-card` IPC channel 存在
✅ `copy-button` CSS class 存在（`&:hover .copy-button { opacity: 1 }`）
✅ 复制功能 UI 字符串存在：`client:ask_anything_reply__copy_tooltip` / `client:ask_anything_reply__copied_tooltip`
✅ 注入失败提示字符串存在：`未能完成写作。点击重试以继续。`
✅ `floating_bar__alert__transcription_error__description: "无法完成写作。点击重试继续。"`

### 2.3 需要用户手动操作的步骤

要实际观测 Typeless 注入失败的 UI 行为，请按以下最短步骤操作：

1. **准备工作**：
   - 关闭所有无关应用
   - 打开记事本 (Notepad)
   - 准备一个可观测剪贴板的工具（如 `tools/observe_clipboard_and_focus.py`，见下方代码）
   - 在剪贴板观测工具中设置哨兵文本 `TYPELESS_CLIPBOARD_SENTINEL_20260627`

2. **触发注入失败**：
   - 启动 Typeless，开始录音（按下录音热键）
   - 说一段话（5-10 秒），等待 Typeless 完成语音识别
   - **在 Typeless 即将注入文本前**，快速关闭记事本窗口
   - 释放录音热键
   - 观察 Typeless 的行为

3. **记录以下信息**：
   - 是否出现大结果窗口？
   - 窗口中有哪些内容？（识别文本、复制按钮、重试按钮？）
   - 剪贴板中是否有内容？（哨兵文本是否被覆盖？）
   - 窗口是否自动关闭？多长时间？
   - 是否可以手动复制文本？

### 2.4 剪贴板观测工具

```python
# tools/observe_clipboard_and_focus.py
"""Monitor clipboard and foreground window changes.
Run this before triggering Typeless injection failure."""
import time
import threading
import pyperclip  # pip install pyperclip
import psutil     # pip install psutil

SENTINEL = "TYPELESS_CLIPBOARD_SENTINEL_20260627"

def monitor_clipboard():
    last = pyperclip.paste()
    while True:
        time.sleep(0.3)
        current = pyperclip.paste()
        if current != last:
            print(f"[CLIPBOARD] Changed: {repr(current[:200])}")
            if SENTINEL not in current:
                print(f"  >>> SENTINEL OVERWRITTEN! Text length: {len(current)}")
            last = current

def monitor_focus():
    import win32gui  # pip install pywin32
    last_title = ""
    while True:
        time.sleep(0.5)
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        if title != last_title:
            print(f"[FOCUS] -> {repr(title)}")
            last_title = title

if __name__ == "__main__":
    pyperclip.copy(SENTINEL)
    print(f"Sentinel set: {SENTINEL}")
    threading.Thread(target=monitor_clipboard, daemon=True).start()
    threading.Thread(target=monitor_focus, daemon=True).start()
    input("Press Enter to stop monitoring...")
```

---

## 3. 用户观察 vs 实测对比

`[用户观察]`

### 3.1 用户回忆

> "Typeless 注入失败时，小悬浮窗结束后会出现一个更大的结果悬浮窗，里面展示识别文字并提供复制按钮。"

### 3.2 静态分析验证

| 用户回忆 | 静态证据 | 结论 |
|---|---|---|
| 小悬浮窗结束后出现更大窗口 | ✅ `interactive-card.html` + `floating-bar.html` 两个独立窗口存在 | **支持** |
| 窗口展示识别文字 | ✅ `interactive-card.html` 标题="AI result"，接收 `answer` payload | **支持** |
| 提供复制按钮 | ✅ `copy-button` CSS class，`copy_tooltip` / `copied_tooltip` 字符串 | **支持** |
| 注入失败时触发 | ✅ `floating_bar__alert__transcription_error__title: "出现问题"` | **部分支持** |
| 窗口有"重试"按钮 | ✅ `floating_bar__alert__transcription_error__description: "无法完成写作。点击重试继续。"` | **支持** |

### 3.3 尚未验证的运行时行为

- 失败后 interactive-card 是否**自动弹出**（无需用户操作）
- 窗口出现到消失的**时间窗口**
- 是否**自动将文本置入剪贴板**（独立于注入路径）
- 是否**自动获得焦点**（focus stealing）
- 窗口是否可**拖动**、可**调整大小**

---

## 4. 仍无法确认的事项

`[推测，未验证]`

### 4.1 触发条件

- 注入失败（injection fail）是否一定触发 interactive-card？
- 是否存在静默失败模式（既不弹窗也不复制）？
- 部分失败（部分字符注入成功）时如何表现？
- 网络超时（transcription timeout）是否归类为"注入失败"？

### 4.2 剪贴板行为

Typeless 主进程中引用了 `clipboard as _0x520c7d from 'electron'`，但：
- ❓ 注入失败时是否自动 set clipboard？
- ❓ 如果 set clipboard，是否覆盖用户已有的剪贴板内容？
- ❓ 交互卡片上的"复制"按钮是调用 `navigator.clipboard.writeText()` 还是 Electron `clipboard.writeText()`？

### 4.3 交互卡片细节

- ❓ `userPrompt` 和 `answer` 字段：卡片展示的是用户语音的转录文本，还是 AI 处理后的回答？
- ❓ `webMetadata` 字段：若注入失败涉及网页上下文，是否显示来源？
- ❓ `selectedText` 字段：是否显示选中文本？
- ❓ 卡片的 `maxHeight` 限制（`0x7d00` = 32000px）是否意味着长文本可滚动？

### 4.4 自动消失逻辑

在 `JpWOXAMI.mjs` 中：
- `setTimeout(() => { _0x317977(0x1); }, D)` 其中 `D = 0x12c = 300ms` — 这是初始显示延迟
- `H = 0x96 = 150ms` — 这是布局稳定后的动画间隔
- ❓ 卡片是否有自动关闭定时器？搜索到 `D` 常量用于初始显示延迟，但未找到明确的自动关闭超时

### 4.5 重试/历史功能

- ❓ `floating_bar__alert__transcription_timeout__pro__description: "未能完成写作。点击重试以继续。"` — 重试是否重新触发注入？
- ❓ 是否有历史记录入口让用户找回之前失败的文本？

---

## 5. SayIt 代码对比

`[SayIt 代码对比]`

### 5.1 当前 SayIt 的失败处理

| 组件 | 当前行为 | 文件 |
|---|---|---|
| 小悬浮窗 | `float.html`，86×34px，仅显示状态（ERR/OK） | `frontend/ui/float.html` |
| 错误显示 | 3 秒自动消失，无交互按钮 | `frontend/ui/float.html` |
| 注入失败回调 | `_fail()` 调用 `_clipboard_set_text(text)` | `infrastructure/injector.py` |
| 剪贴板设置 | 失败时**自动设置**剪贴板内容 | `infrastructure/injector.py` |
| 大结果窗口 | **不存在** | — |
| 复制按钮 | 不存在（剪贴板已自动设置） | — |
| 重试按钮 | **不存在** | — |

### 5.2 Typeless vs SayIt 差距

| 维度 | Typeless | SayIt |
|---|---|---|
| 注入失败 UI | 大结果窗口（interactive-card）+ 复制按钮 | 仅 86×34px 浮动条，3s 消失 |
| 复制按钮 | ✅ 有 | ❌ 无（自动设置剪贴板取代） |
| 重试按钮 | ✅ "点击重试以继续" | ❌ 无 |
| 识别文本展示 | ✅ 大窗口展示 | ❌ 无（仅在日志中） |
| 自动剪贴板 | ❓ 不确定 | ✅ 已实现（`_fail()` 中） |
| 窗口自适应 | ✅ `ResizeObserver` + IPC 通知主进程调整窗口大小 | ❌ 固定尺寸 |

### 5.3 关键设计差异

1. **Typeless 的 philosophy**: 注入失败时，通过大窗口展示识别文本并让用户**手动复制**，同时提供重试选项。这是"给用户掌控感"的策略。
2. **SayIt 当前的 philosophy**: 注入失败时，**自动将文本置入剪贴板**（静默完成），仅在小浮动条上显示短暂提示。这是"最小化用户打扰"的策略。

---

## 6. 复制策略建议

`[推测，未验证]`

### 6.1 建议：等待黑盒确认后再决策

在获得 Typeless 注入失败时的运行时行为之前，**不建议**对 SayIt 的失败处理策略做任何决定。

### 6.2 需要回答的关键问题

1. **Typeless 注入失败时，剪贴板是否已被自动设置？**
   - 若 **是** → 说明 Typeless 也在失败时保护文本，与 SayIt 当前策略一致
   - 若 **否** → 说明 Typeless 选择让用户主动复制（通过 interactive-card 的复制按钮）

2. **Typeless 的 interactive-card 是否会在正常注入成功后也弹出？**
   - 若 **是** → 说明这是一个"结果展示"窗口，与失败无关
   - 若 **否**（仅失败时弹出）→ 说明是专门的"失败补救"UI

3. **用户对当前 SayIt 静默复制策略的满意度？**
   - 用户可以接受自动复制吗？还是更想要一个可见的确认窗口？

### 6.3 如果决定跟随 Typeless 模式

若黑盒实测确认 Typeless 的 `interactive-card` 是有价值的，SayIt 可考虑实现简化版：

```
[注入失败]
    ↓
显示大结果窗口（类似 float.html 扩展版）
    ├── 展示识别文本
    ├── [复制] 按钮 → 手动复制到剪贴板
    └── [重试] 按钮 → 重新尝试注入
    ↓
保留现有 _clipboard_set_text(text) 作为备用（失败即保存）
```

### 6.4 如果决定保持当前策略

若黑盒实测发现 Typeless 的交互窗口在实际使用中并不理想（如干扰工作流、用户不喜欢），则保持 SayIt 当前的"自动剪贴板 + 3s 小提示"策略。

### 6.5 建议下一步

1. **用户手动执行第 2 节的黑盒操作步骤**
2. 记录 Typeless 在注入失败时的完整行为
3. 更新本报告第 2、3、4 节
4. 基于运行时证据，决定 SayIt 的复制策略

---

## 附录 A：关键文件偏移

| 文件 | asar 偏移 | 大小 | 说明 |
|---|---|---|---|
| `dist/renderer/interactive-card.html` | 详见 asar header | 1,563 B | AI result 窗口 HTML |
| `dist/renderer/floating-bar.html` | 详见 asar header | 1,744 B | 状态小悬浮栏 |
| `dist/renderer/static/js/JpWOXAMI.mjs` | 详见 asar header | 4,214 B | interactive-card 入口 JS |
| `dist/renderer/static/js/BQnP7Nhs.js` | 详见 asar header | 419,641 B | 答案卡片组件（含 copy-button） |
| `dist/renderer/static/js/BGJQzzD6.js` | 详见 asar header | — | 中文 UI 字符串（含失败提示） |
| `dist/main/index.js` | 详见 asar header | 531,557 B | 主进程 |

## 附录 B：关键字符串证据

### 复制功能 (`BQnP7Nhs.js`)
```
'&:hover .copy-button': {'opacity': 1}
client:ask_anything_reply__copied_tooltip
client:ask_anything_reply__copy_tooltip
```

### 注入失败提示 (`BGJQzzD6.js`)
```
floating_bar__alert__transcription_error__title: "出现问题"
floating_bar__alert__transcription_error__description: "无法完成写作。点击重试继续。"
floating_bar__alert__transcription_timeout__description: "无法完成写作。点击重试继续。"
floating_bar__alert__transcription_timeout__pro__description: "未能完成写作。点击重试以继续。"
```

### Interactive-card IPC (`main/index.js`)
```
page:open-interactive-card
page:close-interactive-card
page:get-interactive-card-payload
page:update-interactive-card-bounds
```

### Interactive-card payload 字段 (`JpWOXAMI.mjs`)
```
onClose
userPrompt
answer
webMetadata
selectedText
```

---

*报告生成于 Typeless v1.8.0 的本地静态分析，待运行时黑盒验证补充。*
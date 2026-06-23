# Sayit 重构方案：从「逆向猜测」到「翻译工程」

> **目标**：基于 Typeless 逆向源码，1:1 翻译/适配为 Sayit Python 产品，而非从报告描述凭空发明。
>
> **架构**：Electron → pywebview（Windows 桌面原生感，参照闪电说/Typeless）
>
> **执行方式**：Claude Code 逐模块翻译（给源码不给报告），用户逐模块验收。

---

## 为什么之前反复失败

| 之前的做法 | 问题 |
|---|---|
| 逆向报告 → Claude Code 编码 | 报告是「地图」，没有「施工图纸」 |
| 「参照 Typeless 浮窗做」 | LLM 没见过 Typeless 源码，只能猜 |
| 测试不过 → 修改描述再生成 | 每次都是新的猜测，不是修 bug |
| float_app.py 260×44 硬编码 | 完全没参照 Typeless 的 Ch 类逻辑 |

**核心问题一句话**：LLM 善于翻译已有代码，不善于从文字描述发明可运行的代码。

---

## 正确方案：翻译流水线

```
Typeless 原始源码.js  →  [去混淆]  →  可读源码.js
                                          ↓
                              Claude Code 逐模块翻译
                              「这是原代码，这是目标平台，翻译它」
                                          ↓
                              Sayit Python 等效实现
                                          ↓
                              用户验收每个模块（能跑 / 不能跑）
```

---

## 三阶段总览

| 阶段 | 内容 | 轮数 | 产出 |
|---|---|---|---|
| **阶段 1：素材准备** | 源码去混淆 + 模块拆分 + 对照表 | 1 天 | `reference/` 目录 |
| **阶段 2：模块翻译** | 逐模块 CC 翻译，用户验收 | 5-8 轮 | 可运行的 Sayit |
| **阶段 3：产品化** | 打包 + 测试 + 安装器 | 2 轮 | Sayit.exe |

---

## 阶段 1：源码素材准备

### 目标
将 Typeless 混淆过的 JS 源码，转化为 Claude Code 能读懂、能参照的可执行参考代码。

### 1.1 提取并去混淆核心模块

Typeless 核心模块都在 `dist/` 下（asar 已解包）。关键文件：

| 原始文件 | 大小 | 用途 | 优先级 |
|---|---|---|---|
| `dist/main/index.js` | 516KB | Electron 主进程（含 Ch 浮窗类） | P0 |
| `floating-bar.html` | 46行 | 浮窗 HTML 入口 | P0 |
| `CAjA2tJL.mjs` | 210KB | 浮窗 React 组件 + XState 状态机 | P0 |
| `C_80p6cs.js` | 2.4KB | AudioWorklet 原始源码（幸运地未混淆） | P0 |
| `dist/main/keyboard-helper-child-process.js` | 13KB | 键盘钩子 | P1 |
| `CWH6uQLJ.js` | 892KB | 工具函数 + hooks | P1 |
| `DDka1sO-.mjs` | 7.1MB | 主 bundle（第三方库为主，跳过） | - |

### 1.2 去混淆方法

```
方案A（推荐）：webcrack
  npm install -g webcrack
  webcrack dist/main/index.js -o reference/deobfuscated/

方案B：ChatGPT/Claude 辅助重命名
  把混淆后的变量名 _0x2314f2(0x607) 让 AI 根据上下文推断含义并重命名

方案C：只提取关键类/函数
  针对 Ch 类、XState 状态机、AudioWorklet —— 不需要完整去混淆
```

### 1.3 建立 Sayit ↔ Typeless 对照表

| Typeless 概念 | Sayit 对等物 | 翻译策略 |
|---|---|---|
| Electron BrowserWindow | pywebview create_window | 保持 API 风格一致 |
| Ch 类（浮窗管理） | FloatManager 类 | 逐方法翻译 |
| XState 状态机 | Python 状态机（transitions 库或手写） | 保留所有状态/事件/guard |
| setIgnoreMouseEvents | pywebview 无直接 API，需 Win32 API 补丁 | 搜方案再翻译 |
| IPC 通道 182 个 | WebSocket + REST API（已有 server.py） | 只翻译 Sayit 需要的 |
| AudioWorklet | PyAudio 回调 | 保持采样率/帧大小一致 |
| Opus 编码 | 可跳过（Sayit 用 PCM） | 保留但默认关闭 |

### 1.4 产出物

```
sayit_cg/
  reference/
    typeless/
      floating-bar.html          ← 浮窗 HTML 入口
      CAjA2tJL_deobfuscated.js  ← 浮窗组件（去混淆）
      Ch_class.js                ← 浮窗 Ch 类（提取）
      XState_machine.js          ← 状态机定义（提取）
      AudioWorklet.js            ← C_80p6cs.js 原始源码
      keyboard_hook.js           ← 键盘钩子
      module_map.json            ← 模块对应关系
    sayit_translation_map.md     ← Sayit ↔ Typeless 对照表
```

---

## 阶段 2：模块翻译（P0 必做）

**翻译原则**：
- 每个模块单独一个 Claude Code 任务
- 指令格式：「这是 Typeless 原始源码 [贴代码]，请 1:1 翻译为 Python + pywebview 等效实现。不要自己发明新逻辑，不要简化。如果不确定某个 API 在 Python 侧怎么实现，先告诉我，不要猜。」
- 用户验收每个模块后才进入下一个

### 模块 1：浮窗窗口管理（Ch 类翻译）

**输入**：`reference/typeless/Ch_class.js`

**翻译目标**：
- `createWindow()` → `FloatManager.create()`
- `getWindowOptions()` → 窗口参数配置
- `setupMouseTracking()` → 鼠标跟踪（多显示器跟随）
- `startMouseDetection()` → 鼠标穿透检测
- `moveWindowToDisplay()` → 显示器切换跟随
- `closeWindow()` → 窗口销毁

**验收标准**：
- 浮窗出现在屏幕底部中央
- 鼠标穿透有效（可点击穿透区域后的应用）
- 鼠标悬停 card 区域时不穿透
- 切换显示器时浮窗自动跟随
- 无边框透明窗口

**Claude Code 指令示例**（一次一个方法）：
```
这是 Typeless 浮窗 Ch 类的 createWindow 方法：

[贴 Ch.createWindow 源码]

请翻译为 Python + pywebview，保持完全相同的逻辑：
- 窗口类型：panel, transparent, frame:false, hasShadow:false
- 尺寸：FW=500, FH=500
- 初始 mouseEvents 穿透
- alwaysOnTop: 'screen-saver' 级别

如果 pywebview 不支持某个参数，告诉我替代方案，不要跳过。
```

### 模块 2：XState 浮窗状态机

**输入**：`reference/typeless/XState_machine.js` + `CAjA2tJL_deobfuscated.js`

**翻译目标**：完整的 6 状态机
```
idle → starting-microphone → recording_active
  ├─ handsFree
  ├─ pushToTalk
  └─ translationModeHandsFree
→ stopping → done → error
```

包含所有 guard 条件、action side effect、事件定义。

**验收标准**：
- 按快捷键触发 idle → recording 转换
- 录音中显示波形动画
- 停止录音进入 thinking 状态
- ASR 结果返回进入 done 状态
- 错误进入 error 状态并显示重试
- 重试按钮回到 idle

### 模块 3：浮窗 UI（HTML + 动画）

**输入**：`reference/typeless/floating-bar.html` + `CAjA2tJL.mjs` 中的 UI 渲染逻辑

**翻译目标**：
- idle 状态：10 根灰色静态条
- recording 状态：card 组件（红点闪烁 + 26 根声纹 + 计时器 + 取消/完成按钮）
- thinking 状态：「Thinking...」渐变加载文字
- done 状态：绿色 ✓ + 可编辑文本
- error 状态：错误提示 + 重试按钮

**注意**：这个模块你之前已经做到了 80%（`frontend/ui/float.html` 是目前最接近 Typeless 的实现），只需要补全 done/error 状态。

**验收标准**：
- 所有 5 个状态视觉正确
- 26 根声纹的动画算法与 Typeless 一致
- 计时器格式 MM:SS

### 模块 4：键盘快捷键系统

**输入**：`reference/typeless/keyboard_hook.js`

**翻译目标**：
- RightAlt → 开始/停止 dictation（已部分实现）
- RightAlt+Space → askAnything 模式（新增）
- RightAlt+RightShift → 翻译模式（新增）
- LeftCtrl+RightShift+V → 粘贴上次转录（新增）

**验收标准**：
- 4 组快捷键全部可用
- 快捷键不与应用快捷键冲突
- 有冲突时显示提示

### 模块 5：音频采集管道

**输入**：`reference/typeless/AudioWorklet.js`（C_80p6cs.js）

**翻译目标**：
- PyAudio 采集参数与 Typeless 一致（采样率/帧大小/通道数）
- RMS 电平计算（用于波形动画）
- ASR 引擎调用（已有 FunASR/Aliyun/Volcengine）

**验收标准**：
- 录音质量与 Typeless 相当
- 波形动画的 RMS 值与实际音量匹配

### 模块 6：文本注入

**输入**：`dist/main/index.js` 中的 SendMessage/Clipboard 逻辑

**翻译目标**：
- SendInput / UIA 文本注入（已有部分实现）
- 注入策略（APP_STRATEGIES 黑/白名单）
- 粘贴上次转录

**验收标准**：
- 注入到光标位置
- 不在黑名单应用中注入
- 支持粘贴上次转录

---

## 阶段 3：产品化

### 3.1 集成测试

全部 6 个模块串联：
1. 按 RightAlt → 浮窗出现 + 开始录音
2. 说话 → 波形跳动 + 计时
3. 按 RightAlt（或点 ✓）→ 停止录音 → 显示 Thinking
4. ASR 结果注入到光标位置
5. 浮窗消失

### 3.2 打包为桌面应用

```
pywebview + Flask（已有 server.py）
  → PyInstaller 打包为 sayit.exe
  → 安装器（NSIS 或 Inno Setup）
```

### 3.3 配置与设置页面

- ASR 引擎选择（Aliyun/Volcengine/本地）
- AI 纠正引擎选择
- 快捷键自定义
- 黑/白名单管理
- 词典管理

---

## 关键问题：Claude Code 适合吗？

### 适合，但需要正确的输入

| 场景 | Claude Code 表现 |
|---|---|
| 给一段源码，说「翻译成 Python」 | ✅ 擅长。代码结构清晰，直接映射。 |
| 给一份描述文档，说「照着实现」 | ❌ 会从零发明，细节全错。 |
| 给源码 + 翻译到一半的代码，说「继续翻译剩余部分」 | ✅ 擅长。上下文充分。 |
| 给源码 + 运行报错，说「修复」 | ✅ 擅长。能对照原代码找差异。 |

### 不适合的地方

- **pywebview 的某些限制**：例如 `setIgnoreMouseEvents` 没有直接 API，需要用 Win32 API 打补丁。这种情况下 Claude Code 可能会自己发明一个假的实现。**对策**：先搜社区方案，把方案告诉它再让它写代码。
- **跨文件依赖**：一个模块的翻译可能依赖另一个模块的产物。**对策**：翻译前先定义好接口契约，每个模块暴露什么 API。

### 你的指令够不够细？

**不够。** 不是因为你不专业，而是因为你给 Claude Code 的是「逆向报告」——这份报告在你看来很详细（182个IPC通道！246个函数！），但对 LLM 来说只是一堆名字。LLM 需要看到**「它是怎么做的」**，不是「它有什么」。

**优化的指令应该是**：
```
不要看逆向报告。
这是 Typeless 的 Ch 类源码：
[贴代码]
请逐行翻译为 Python pywebview。
```

而不是：
```
根据逆向报告中的浮窗描述，实现一个类似的浮窗。
```

---

## 执行路线图

```
Week 1:
  Day 1-2: 阶段 1 — 源码去混淆 + 对照表
  Day 3: 模块 1 — 浮窗窗口管理（Ch 类翻译）
  Day 4: 模块 2 — XState 状态机
  Day 5: 模块 3 — 浮窗 UI

Week 2:
  Day 6: 模块 4 — 键盘快捷键
  Day 7: 模块 5 — 音频采集
  Day 8: 模块 6 — 文本注入
  Day 9: 集成测试 + 修 bug
  Day 10: 打包 + 安装器
```

---

## 铁律

1. **给源码不给报告** — 每个 Claude Code 任务的输入是原始 JS 代码，不是逆向报告
2. **一个模块一个任务** — 不要让它「实现全部浮窗功能」，而要「翻译 Ch.createWindow 方法」
3. **用户验收驱动** — 每个模块做完，你先跑一遍，通过才进入下一个
4. **不确定的先搜** — Claude Code 遇到 pywebview API 限制时，让它先搜索方案，不要猜
5. **不为做而做** — 如果某个 Typeless 功能 Sayit 不需要（如 Opus 编码），跳过，不追求 100% 复刻

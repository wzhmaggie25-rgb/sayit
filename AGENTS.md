# Sayit — Codex Project Context

## Architecture (DO NOT DEVIATE)

```
Sayit = Electron frontend + Python backend

frontend/          ← Electron 主进程 + 渲染进程（你在这里工作）
  main.js          ← 唯一入口，Electron 主进程
  preload.js       ← IPC 桥接
  ui/
    recorder.html  ← 主窗口
    float.html     ← 浮窗（翻译目标）
  package.json     ← electron 依赖已安装

../server.py       ← Python FastAPI 后端（不要改它）
  REST API: /api/config, /api/history, /api/start-recording 等
  WebSocket: /ws/events
  端口: 127.0.0.1:17890

reference/         ← Typeless 原始参考源码（只读，不修改）
  Ch_class.js           ← 浮窗 Ch 类
  XState_machine.js     ← 完整 XState 状态机
  AudioWorklet.js       ← 音频处理器
  track_edit.js         ← 静默学习
  focus_context.js      ← 聚焦上下文
  injection_strategy.js ← 注入策略
  floating-bar.html     ← 浮窗 HTML
  float_ui_states.js    ← UI 状态结构
```

**铁律：frontend/ 是 Electron 不是 pywebview。不要引入新的 Python 前端。**

---

## Translation Principles

### 核心原则

```
你是翻译官，不是发明家。
每次写代码前，先问自己：Typeless 源码里对应的逻辑在哪？
如果 reference/ 里有，1:1 翻译。
如果 reference/ 里没有，告诉我需要什么信息，不要自己发明。
```

### 具体规则

1. **给源码不给描述**：设计讨论可以说「参照 Ch 类」，但编码时必须打开 `reference/Ch_class.js`，逐方法翻译
2. **Electron API 完全对应**：Typeless 用 Electron，Sayit 也用 Electron。API 名称大概率一样，直接 copy 参数名
3. **不确定时标注**：如果某段逻辑看不懂，写 `// TODO: verify — Typeless line XXXX`，不要猜着写
4. **保持变量语义**：翻译时保留 Typeless 的变量语义，如 `FW=500, FH=500`、`lastIsMouseInside`、`elementPositions`
5. **Python 后端不要碰**：`server.py` 已经实现 ASR、AI Provider、数据库、REST API，前端只通过 HTTP/WebSocket 调用它

---

## Module Translation Order

按依赖顺序翻译，每次只做一件事，做完验收：

### Module 1: Float Window Manager
- **Reference**: `reference/Ch_class.js`
- **Target**: `frontend/main.js` 中的 float 窗口管理
- **Deliverable**: 浮窗出现/消失/鼠标穿透/多显示器跟随
- **Acceptance**:
  - 按快捷键 → 浮窗出现在屏幕底部中央
  - 鼠标可穿透浮窗空白区域
  - 鼠标悬停 card 时不穿透
  - 切换显示器时浮窗跟随

### Module 2: Float State Machine
- **Reference**: `reference/XState_machine.js`
- **Target**: `frontend/main.js` 中新增状态机 + `frontend/ui/float.html` 状态切换
- **Deliverable**: 6 状态完整流转（idle/recording/thinking/done/error）
- **Acceptance**:
  - idle → 录音开始 → recording（红点+声纹+计时）
  - 录音结束 → thinking（渐变文字）
  - 结果返回 → done（可编辑文本）
  - 错误 → error（重试按钮）

### Module 3: Float UI Polish
- **Reference**: `reference/floating-bar.html` + `reference/float_ui_states.js`
- **Target**: `frontend/ui/float.html` CSS + 动画
- **Deliverable**: 视觉效果与 Typeless 一致
- **Acceptance**:
  - idle：10 根灰色静态条
  - recording：26 根白色声纹、requestAnimationFrame 动画、渐变遮罩
  - thinking：shimmer 动画
  - done/error 状态视觉完整

### Module 4: Audio Pipeline
- **Reference**: `reference/AudioWorklet.js`
- **Target**: Python 端音频参数对齐（不改前端，只验证参数）
- **Deliverable**: RMS 电平值准确，波形与声音匹配
- **Acceptance**: 录音时波形跳动与实际音量成正比

### Module 5: Silent Learning (Track Edit)
- **Reference**: `reference/track_edit.js`
- **Target**: Python 端新增静默学习逻辑（server.py 的 correction_rules 表已有）
- **Deliverable**: 文本注入后监控用户编辑 → 自动提取修正规则
- **Acceptance**: 修改注入文本后，correction_rules 表出现新规则

### Module 6: Focus Context + Injection Strategy
- **Reference**: `reference/focus_context.js` + `reference/injection_strategy.js`
- **Target**: Python 端（已有 app_name 字段，补全策略匹配）
- **Deliverable**: 知道当前在哪个 App，不同 App 不同注入策略
- **Acceptance**: Chrome 和 Word 中使用不同的注入方式

---

## Coding Standards

- 变量命名：camelCase（和 Typeless 保持一致）
- 注释：英文，注明对应 Typeless 源码位置
- 窗口尺寸：FW=500, FH=500（与 Typeless 一致，但 card 实际只占下半部分）
- 颜色：暗色主题 `rgba(38,38,38,.95)` 背景
- 文件组织：浮窗相关逻辑集中在 `frontend/main.js`，不分散到多个文件

---

## Key Typeless API → Electron Equivalents

| Typeless | Electron (Sayit) |
|---|---|
| `new BrowserWindow({transparent:true, frame:false})` | 相同 |
| `win.setIgnoreMouseEvents(true, {forward:false})` | 相同 |
| `win.setAlwaysOnTop(true, 'screen-saver', 1)` | 相同 |
| `screen.getPrimaryDisplay()` | 相同 |
| `screen.getCursorScreenPoint()` | 相同 |
| `win.setBounds({x, y, width, height})` | 相同 |
| `page:open-typeless-bar` IPC | HTTP GET `/api/is-recording` + 状态轮询 |
| `floatWin.webContents.executeJavaScript(js)` | 相同 |

---

## Communication with Python Backend

前端通过 polling 获取录音状态（已在 main.js 中实现）：

```js
// 每 200ms 轮询
const r = await fetch('http://127.0.0.1:17890/api/is-recording').then(r => r.json());
// r.recording: true/false
// r.rms: 音量电平 0.0-1.0
```

事件通过 WebSocket 推送（已在 server.py 中实现）：
- `recording_started`, `recording_stopped`, `tick`, `rms_level`
- `asr_result`, `ai_result`, `pipeline_done`, `error`

控制命令通过 REST API：
- `POST /api/start-recording`
- `POST /api/stop-recording`

---

## Before You Start Any Task

1. 确认你知道 reference/ 中哪份文件是参考源
2. 打开那份文件，找到对应代码段
3. 告诉我你要修改哪些文件
4. 翻译完成后，对照 reference 自查一遍
5. 做一次端到端测试（启动 server.py → 启动 Electron → 按快捷键测试）

# Typeless 全面逆向工程计划

## 源文件清单 (62 文件, 8.6MB)

### 主进程 (Main Process)
| 文件 | 大小 | 状态 | 描述 |
|------|------|------|------|
| `dist/main/index.js` | 516KB | 待分析 | Electron 主进程 (minified) |
| `dist/main/keyboard-helper-child-process.js` | 13KB | 待分析 | 键盘钩子子进程 (koffi FFI) |
| `dist/main/worker/opusWorker.js` | 12KB | 待分析 | Opus 音频编码 Worker |
| `dist/preload/index.mjs` | 9KB | 待分析 | Electron preload 桥接脚本 |

### 渲染进程 HTML (6 页面)
| 文件 | 行数 | 状态 | 描述 |
|------|------|------|------|
| `floating-bar.html` | 46 | 已分析 | 浮窗页面 (React 入口) |
| `hub.html` | 49 | 待分析 | 主控制台/仪表盘 |
| `interactive-card.html` | 39 | 待分析 | 弹出交互卡片 |
| `login.html` | 44 | 待分析 | 登录页面 |
| `onboarding.html` | 51 | 待分析 | 首次引导页面 |
| `sidebar.html` | 36 | 待分析 | 侧边栏面板 |

### 渲染进程 JS 模块 (.mjs — 可读性较高)
| 文件 | 大小 | 状态 | 预计内容 |
|------|------|------|---------|
| `CAjA2tJL.mjs` | 210KB | 待分析 | 浮窗 React 组件 |
| `ClFdSUJP.mjs` | 294KB | 待分析 | 主 UI 组件库 |
| `DDka1sO-.mjs` | 7.1MB | 待跳过 | 巨型 bundle (第三方库) |
| `Cv3zkyxj.mjs` | 15KB | 待分析 | 工具/辅助模块 |
| `zmjEUIIk.mjs` | 4KB | 待分析 | 小工具模块 |
| `BoqB-mU5.mjs` | 1.4KB | 待分析 | 配置/常量 |

### 渲染进程 CSS
| 文件 | 大小 | 状态 | 描述 |
|------|------|------|------|
| `DX4YKr20.css` | 56KB | 已读 | Markdown/Typo 样式 + KaTeX |
| `C18_jUIn.css` | 1KB | 已读 | 字体定义 |
| `BKwdbiav.css` | 37B | 待分析 | - |
| `DsB1kaHT.css` | 59B | 待分析 | - |

---

## 逆向工程阶段

### Phase 1: HTML 页面与路由 ⬜
- [ ] 1.1 分析每个 HTML 页面的结构和加载的模块
- [ ] 1.2 提取页面路由表 (Kt 常量: HUB/LOGIN/FLOATING_BAR/ONBOARDING/SIDEBAR/INTERACTIVE_CARD)
- [ ] 1.3 分析每个页面的用途和用户流程

### Phase 2: 窗口管理系统 ⬜
- [ ] 2.1 提取所有 BrowserWindow 类型和配置
- [ ] 2.2 提取窗口尺寸/位置/flags 参数
- [ ] 2.3 提取窗口生命周期 (create/show/hide/close)
- [ ] 2.4 提取 `class Ch extends Zt` 浮窗类完整代码
- [ ] 2.5 提取 `class Zt` 基窗口类

### Phase 3: 浮窗组件 (CAjA2tJL.mjs) ⬜
- [ ] 3.1 提取 React 组件树结构
- [ ] 3.2 提取浮窗状态机 (idle/recording/thinking/done/error)
- [ ] 3.3 提取波形动画算法
- [ ] 3.4 提取 UI 布局和样式

### Phase 4: 键盘与快捷键 ⬜
- [ ] 4.1 分析 keyboard-helper-child-process.js 的 koffi FFI 调用
- [ ] 4.2 提取快捷键注册和监听逻辑
- [ ] 4.3 提取键盘事件到主进程的 IPC 通道
- [ ] 4.4 分析快捷键配置界面

### Phase 5: 音频与 ASR 管道 ⬜
- [ ] 5.1 分析 opusWorker.js 的音频编码
- [ ] 5.2 提取音频采集参数 (采样率/通道/格式)
- [ ] 5.3 提取 ASR 引擎选择和级联逻辑
- [ ] 5.4 分析 AI 纠错/润色流程

### Phase 6: 注入与静默学习 ⬜
- [ ] 6.1 提取文本注入策略 (UIA/Clipboard/SendInput)
- [ ] 6.2 提取静默学习监控逻辑
- [ ] 6.3 提取个人词典管理

### Phase 7: 整合报告 ⬜
- [ ] 7.1 输出架构全景图
- [ ] 7.2 输出可复刻的规格表
- [ ] 7.3 输出 Sayit 改造方案

---

## 当前进度
- [x] Phase 0: 文件扫描完成
- [ ] Phase 1-7: 待执行

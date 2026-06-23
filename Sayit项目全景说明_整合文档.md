# Sayit 唯一真相来源 (Single Source of Truth)

> 2026-06-15 | v1.10.0 | fix/p0-core-interaction
>
> **铁律 1：只要影响「说出话 → 准确转文字 → 自动纠错润色 → 输出正确结果」这个闭环质量的，就是环内必做。**
>
> **铁律 2：对标抄袭 = 只抄接口（输入→输出），不抄全貌（动画/设置项/边缘场景）。**

---

## 零、对标拆解：从 Typeless / 闪电说 我们抄什么

每个对标模块只问三个问题：输入什么？输出什么？用户触发动作是什么？

### 从 Typeless 抄的

| 模块 | 输入 | 输出 | 触发动作 | 我们只抄 |
|------|------|------|----------|----------|
| **浮窗状态机** | `recording_started / stopped / pipeline_done / error` 事件 | 声纹动画 / shimmer / Done / 错误提示 | 热键按下/松开 | ✅ 5 态流转 + 事件驱动。❌ 渐变动画、毛玻璃、圆角打磨 |
| **音频柱可视化** | RMS 音量值 (0.0-1.0, 200ms 间隔) | 14 根高度变化的色条 | 自动（录音期间） | ✅ 中心加权 profile + requestAnimationFrame。❌ 粒子效果、颜色主题 |
| **vkE8 Mask Key** | RAlt key-down 事件 | 注入 vkE8 虚拟键 → Windows 不触发 SC_KEYMENU | 自动（RAlt 按下时） | ✅ `keybd_event(vkE8)` 时序。❌ 无 |
| **鼠标穿透** | float 元素坐标 + 光标位置 (100ms 轮询) | `setIgnoreMouseEvents(bool)` | 自动（鼠标移动） | ✅ elementPositions 白名单。❌ 动画过渡 |

### 从闪电说抄的

| 模块 | 输入 | 输出 | 触发动作 | 我们只抄 |
|------|------|------|----------|----------|
| **System Prompt 控制** | 原始 ASR 文本 (string) | 纠错后文本（不改意、不排版、不回答提问） | 自动（ASR 之后） | ✅ 零交互策略 + 非交互式引擎身份。❌ 多任务模式（摘要/邮件） |
| **热词保镖** | 用户词典词汇列表 + 待纠错文本 | 词汇原样保留的纠错文本 | 自动（纠错阶段） | ✅ Prompt 末尾硬性追加保护规则。❌ 词典 UI 动画 |
| **Temperature 锁定** | — | — | — | ✅ T=0.0。❌ 无 |

### 我们不抄的

| 模块 | 为什么不抄 |
|------|-----------|
| 闪电说 VAD 流式分段 | 架构级改动，当前同步模式能跑，后续大版本再做 |
| 闪电说多语种 | 产品方向未定 |
| 闪电说 4 种 AI 任务 | 产品方向未定 |
| Typeless 渐变/毛玻璃/动画曲线 | 不影响文字质量 |
| Typeless 主题系统 | 不影响文字质量 |

---

## 一、闭环定义

```
  说出话              准确转文字              自动纠错润色              输出正确结果
  ──────             ──────────             ────────────             ────────────
  热键触发    →    音频采集     →       ASR 三级级联      →       AI 纠错        →      文本注入
  修饰键释放        麦克风选择            热词保护(3层)           闪电说Prompt         修饰键释放
  vkE8守卫          增益/限幅             超时降级可见            温度锁定              4级注入瀑布
  UIPI管理员窗口    降噪(如有)            模型选择                自定义Prompt          App策略匹配
  互斥防并发                              API Key配置             AI Provider选择       注入结果反馈
                                                                  纠错开关
```

**环上所有节点的质量缺陷，都是 P0/P1。环外的 Bug，修都不要修。**

---

## 二、环内节点完整清单（按链路顺序）

### 🔴 节点 1：热键触发 ——「说出话」的入口

| 子节点 | 状态 | 影响质量？ | 说明 |
|--------|------|-----------|------|
| WH_KEYBOARD_LL 原生钩子 (ctypes) | ✅ | 🎯 入口失效=闭环中断 | `hotkey.py` |
| vkE8 Mask Key 阻断 SC_KEYMENU | ✅ | 🎯 无此 Alt 激活菜单栏、破坏焦点 | `hotkey.py:126-137` |
| Toggle 模式 (按下开始/再按停止) | ✅ | 🎯 基本交互 | `hotkey.py:346-380` |
| 修饰键释放 (注入前 release) | ✅ | 🎯 残留修饰键→注入乱码 | `injector.py:237-257`。GetAsyncKeyState 守卫已修 |
| Pipeline 线程互斥锁 | ✅ 已修 | 🎯 并发竞争→键盘劫持乱码 | `orchestrator.py` `_pipeline_lock` |
| **管理员窗口热键失效 (UIPI)** | 🔌 隐患 | 🎯 用户切换到管理员窗口时闭环直接中断 | 低权限进程的 WH_KEYBOARD_LL 被 UIPI 阻断。无任何处理 |

### 🔴 节点 2：音频采集 ——「说出话」的信号

| 子节点 | 状态 | 影响质量？ | 说明 |
|--------|------|-----------|------|
| PyAudio 16kHz 录音 | ✅ | 🎯 | `audio_capture.py` |
| 增益控制 + soft limiter | ✅ | 🎯 削波失真直接影响 ASR 准确率 | 自动减半 + 持久化 |
| **麦克风设备选择 → 持久化到后端** | ⬜ 待修 | 🎯 用户选对麦克风→转写准确率直接提升 | 当前写 localStorage 但 `doSave()` 不读。**环内待修** |
| 降噪开关 (toggleNoiseSuppress) | 👻 假按钮 | 🎯 环境噪音直接影响 ASR 质量 | 目前是假控件。需要决定：真做降噪，还是从 UI 隐藏 |
| 采样率选择 | 👻 假按钮 | 🟡 边际影响 | 16kHz 对中文 ASR 足够，低优先级 |

### 🔴 节点 3：ASR 转写 ——「准确转文字」

| 子节点 | 状态 | 影响质量？ | 说明 |
|--------|------|-----------|------|
| DashScope ASR (阿里云 fun-asr-realtime) | ⚠️ 15s 超时已加 | 🎯 主引擎 | 同步 REST → 长语音慢。**下一步应换 WebSocket 流式** |
| Volcengine ASR v3 (火山引擎) | ✅ | 🎯 降级引擎 | 已是 WebSocket 流式 |
| ONNX SenseVoice 本地 | ✅ | 🎯 兜底引擎 | 准确率低于云端，但保证离线可用 |
| **ASR 级联编排 + 降级 UI 可见** | ⬜ 待修 | 🎯 用户不知道在用低准确率模型→误以为产品烂 | 降级时无 WS 事件/浮窗提示 → **环内待修** |
| ASR API Key 配置 | ✅ | 🎯 | settings.html ASR 面板 |
| ASR 模型选择 | ✅ | 🎯 | settings.html 下拉动态化 ✅ |
| **ASR 语言/标点配置** | 👻 langSelect 假控件 | 🎯 语言和标点直接影响识别结果 | `toggleAutoPunct` 已接到后端但 `langSelect` 是假控件。**环内待修** |
| 语气词过滤 (toggleDisfluency) | 👻 假按钮 | 🟡 影响输出干净度 | 待决定是后端实现还是从 UI 隐藏 |

### 🔴 节点 4：热词保护 ——「转准」的关键增强

| 子节点 | 状态 | 影响质量？ | 说明 |
|--------|------|-----------|------|
| Layer1: ASR Context 注入 | ✅ | 🎯 告诉 ASR 引擎优先匹配词典词汇 | `hotwords_manager.py` `_sync_to_asr()` |
| Layer2: Fuzzy Match 后修正 | ✅ | 🎯 对 ASR 输出做模糊匹配修正 | `apply_layer2_correction()` |
| Layer3: Prompt Guard (闪电说) | ✅ 新加 | 🎯 防止 AI 改掉专有名词 | `corrector.py` `_build_hotword_guard()` |
| **词典管理 (添加/删除/编辑)** | ✅ 打通 | 🎯 用户不加词→热词保护形同虚设 | dictionary.html 已打通后端。**环内**，当前可用 |
| 词典 → ASR 自动同步 | ✅ | 🎯 | `add_word()` 自动调 `_sync_to_asr()` |

### 🔴 节点 5：AI 纠错润色 ——「自动纠错润色」

| 子节点 | 状态 | 影响质量？ | 说明 |
|--------|------|-----------|------|
| 闪电说 System Prompt (零交互/不改意/不排版) | ✅ 重写 | 🎯 Prompt 质量=纠错质量 | `corrector.py:29-63` |
| Temperature = 0.0 | ✅ 锁定 | 🎯 消除随机性→输出稳定可预测 | `ai_providers.py:208` |
| AI Provider 开关 + Key + 模型选择 | ✅ | 🎯 | settings.html AI 面板全部打通 |
| **自定义 Prompt (structuring_prompt/correction_prompt)** | ✅ | 🎯 高级用户定制纠错行为 | settings.html 偏好面板 ✅ 打通 |
| **AI_ERROR 事件前端可见** | 🔌 未接 WS | 🎯 纠错失败用户不知道→以为卡死 | pipeline 发射但 WS 不转发。**环内待修** |
| AI 纠错总开关 | ✅ | 🎯 | enable_correction/enable_structuring |
| 4 种 AI 任务模式（润色/摘要/邮件/关键词） | 👻 假控件 | 🔮 后续 | 产品方向未定。当前只做纠错 |

### 🔴 节点 6：文本注入 ——「输出正确结果」

| 子节点 | 状态 | 影响质量？ | 说明 |
|--------|------|-----------|------|
| 4 级注入瀑布 (UIA → Clipboard → SendInput) | ✅ | 🎯 | `injector.py` |
| 修饰键释放 (注入前清残留) | ✅ 已修 | 🎯 | GetAsyncKeyState 守卫 |
| **App 策略匹配 (Focus Context)** | 🧠 部分实现 | 🎯 在错的 App 用错策略→注入失败或乱码 | `APP_STRATEGIES` 表有 ~30 个 App。`reference/focus_context.js` 有完整版未翻译完。**环内待补** |
| 注入结果反馈 (INJECTION_DONE) | ✅ | 🎯 用户知道注入成功/失败 | WS 事件已接线 |

### 🔴 节点 7：浮窗 UI —— 整个闭环的状态反馈

| 子节点 | 状态 | 影响质量？ | 说明 |
|--------|------|-----------|------|
| 录音中状态 (声纹动画 + 计时) | ✅ | 🎯 用户知道在录音 | `float.html` |
| 思考中状态 (shimmer) | ✅ | 🎯 用户等待时有反馈 | |
| 完成状态 | ✅ | 🎯 | |
| 错误状态 | ✅ 已修 | 🎯 STOPPING 卡死→用户困惑 | float.html:22 ERROR action 增加 STOPPING 分支 |
| **降级警告** (用本地模型时浮窗提示) | ⬜ 待做 | 🎯 用户不知道在用低准确率模型 | **环内待做** |
| **AI_ERROR 提示** | 🔌 未接 | 🎯 纠错失败用户不知道 | 同上，**环内待修** |
| AI Provider/Model 显示 | ✅ | 🟡 调试价值 | `ai_result` 事件 text 已到 float |
| playBeep 提示音 | ✅ 可用 | 🟡 听觉反馈 | 音色可打磨但当前能用 |

---

## 三、环外（不影响闭环质量，修都不要修）

| # | 环外项 | 理由 |
|---|--------|------|
| H1 | 历史记录页浏览/编辑/删除 | 闭环不需要查看历史 |
| H2 | 个人统计页 | 闭环不需要统计数据 |
| H3 | 自动更新 | 闭环不依赖版本更新 |
| H4 | 开机自启 | 闭环不依赖自启 |
| H5 | 静默学习 (Silent Monitor) | 闭环不需要自动学习，手动加词够用 |
| H6 | 主题系统 (light/dark) | 不影响文字质量 |
| H7 | 设置页非环内假控件 (9个) | taskPolish/taskSummarize/taskStyle/taskKeywords/toggleAutoSave/toggleVuMeter/persona/paragraphStyle/punctStyle/retentionSelect |
| H8 | 主窗口统计面板 Bug | 跟闭环无关 |
| H9 | 主窗口 Mic 按钮 Bug | 跟闭环无关 |
| H10 | sayitSetTheme() Bug | 跟闭环无关 |
| H11 | 4 个 /api/debug/* 端点 | 开发工具 |
| H12 | CONFIG_CHANGED / HOTKEY_CHANGED WS 事件 | 不影响闭环功能 |

---

## 四、后续（对标软件中眼馋的、架构升级的，现在不做）

| # | 后续项 | 类型 |
|---|--------|------|
| F1 | DashScope 换 WebSocket 流式 ASR (真实时 <1s 首字) | 架构升级 |
| F2 | VAD 自动断句 + 分段处理 | 架构升级 |
| F3 | WebSocket 断点续传 | 架构升级 |
| F4 | Typeless 极简浮窗动画打磨 | 交互细节 |
| F5 | playBeep 音色打磨 | 交互细节 |
| F6 | 4 种 AI 任务模式 | 产品方向未定 |
| F7 | 多语种切换 | 产品方向未定 |
| F8 | 数据导出/备份 | 附加功能 |
| F9 | 批量词典导入 | 附加功能 |
| F10 | ONNX 模型 → 导出 .onnx 加速本地推理 | 性能优化 |

---

---

## 六、环内待修任务（按输入→输出→触发 拆解，逐项划掉）

### 任务 1：ASR 降级时浮窗可见警告

> **对标**：无直接对标（Sayit 原创需求，因为三级级联是自创架构）
> **抄的定义**：ASR 引擎切换事件 → 浮窗短暂显示引擎名称标签

| 维度 | 规格 |
|------|------|
| **输入** | `AsrCascade.transcribe()` 返回的 `(text, engine_name)` 中 `engine_name` 从 `"aliyun"` 变为 `"volcengine"` 或 `"onnx"` |
| **输出** | 浮窗在「完成」状态下，短暂显示实际使用的引擎名（如 "本地模型"），2s 后消失 |
| **触发** | 自动（Pipeline TRANSCRIBING 完成后 `ASR_RESULT` 事件附加 `engine` 字段，float 已接收但仅用于顶部标签） |
| **改动点** | `asr.py:540` — 降级路径加 WARNING 日志（已有）。`pipeline.py:117` — ASR_RESULT 事件已带 engine 参数。`float.html:89` — `sayitOnAsrResult` 已存 `asrEngine` state 但未渲染降级警告。**只需在 DONE 状态加一行引擎名标签** |
| **不抄** | 不抄弹窗、不抄音效、不抄颜色分级 |

### 任务 2：AI_ERROR 接 WS → 浮窗可见

> **对标**：无直接对标（闪电说在 UI 上展示"AI 处理失败，使用原始文本"）
> **抄的定义**：AI 调用失败事件 → 浮窗短暂显示"AI 未修正"

| 维度 | 规格 |
|------|------|
| **输入** | `Corrector.process()` 抛出异常 → Pipeline 发射 `AI_ERROR` 事件 |
| **输出** | 浮窗显示 "AI 未修正"（区别于"识别失败"），2s 后自动消失 |
| **触发** | 自动（Pipeline CORRECTING 阶段 LLM 调用失败时） |
| **改动点** | ① `server.py` 的 `wire_events()` 注册 `AI_ERROR` → WS 转发。② `frontend/main.js` 增加 `ai_error` case → `sayitOnError` 或新 callback。③ `float.html` 增加对应状态处理 |
| **不抄** | 不抄重试按钮、不抄降级策略选择 |

### 任务 3：麦克风选择持久化到后端

> **对标**：Typeless 的设备记忆
> **抄的定义**：用户在设置页选麦克风 → 下次启动自动用该设备

| 维度 | 规格 |
|------|------|
| **输入** | 设置页 Mic 下拉 `change` 事件 → 设备名称字符串 |
| **输出** | `config.json` 中 `audio.device_name` 字段更新 |
| **触发** | 用户切换下拉选项时（自动保存，无需手动点保存按钮） |
| **改动点** | `settings.html` `autoSave()` 或 `doSave()` 增加 mic 选择 key。`audio_capture.py` 启动时读取 `config.json` 中 `audio.device_name` 并通过 PyAudio 按名称查找设备索引 |
| **不抄** | 不抄 Typeless 的设备热插拔检测、不抄多设备并发 |

### 任务 4：语言选择 → 后端 (langSelect)

> **对标**：闪电说的 language 配置
> **抄的定义**：用户选择中文/英文/粤语等 → ASR 和 AI 使用对应语言

| 维度 | 规格 |
|------|------|
| **输入** | 设置页 `langSelect` 下拉值（`zh` / `en` / `yue` / `ja` / `ko`） |
| **输出** | `config.json` 中 `local.language` 字段更新 → ONNX 模型和 DashScope 使用对应语言 |
| **触发** | 用户切换下拉选项时 |
| **改动点** | `settings.html` — `langSelect` 加入 `autoSave` key 集合 + `doSave()` 读值。`asr.py:505` — ONNX 初始化已读 `config.local.language`，只需确保 key 路径一致 |
| **不抄** | 不抄自动语言检测 |

### 任务 5：App 策略表补全 (Focus Context)

> **对标**：Typeless `reference/focus_context.js`
> **抄的定义**：知道用户在哪个 App 的哪个控件 → 选择对应的注入策略

| 维度 | 规格 |
|------|------|
| **输入** | `GetForegroundWindow()` → 窗口 class + 进程名 |
| **输出** | 策略字符串（`"uia"` / `"clipboard"` / `"send_input"`）→ 决定注入走哪条路径 |
| **触发** | 自动（Pipeline INJECTING 阶段调用 `_foreground_info()`） |
| **改动点** | `injector.py` `APP_STRATEGIES` 表 — 对照 `reference/focus_context.js` 补全遗漏的 App（如新版 Teams/Discord/Notion/飞书/企业微信等 Electron 壳应用）。`reference/focus_context.js` 中有 ~60 个 App 的完整策略，当前只翻译了 ~30 个 |
| **不抄** | 不抄 UI Automation 细节遍历、不抄自定义控件模式匹配 |

### 任务 6：管理员窗口热键失效 (UIPI)

> **对标**：Typeless 的 UIPI 处理（`reference/injection_strategy.js`）
> **抄的定义**：用户切换到管理员窗口 → 热键仍然能触发录音

| 维度 | 规格 |
|------|------|
| **输入** | 当前前台窗口的权限级别（通过 `GetWindowThreadProcessId` + `OpenProcessToken` 判断） |
| **输出** | 如果前台窗口为管理员权限且当前进程非管理员 → 显示提示/自动提权/降级处理 |
| **触发** | 每次热键按下时检查 |
| **改动点** | `hotkey.py` `_do_toggle_sync()` — 在调用 `on_start()` 前检查前台窗口权限。如果 UIPI 会阻断，至少 log warning + 可选：通过 EventBus 通知 UI |
| **不抄** | 不抄 Typeless 的完整 UIPI 旁路（涉及 Windows 安全模型，大工程）。现阶段做到「检测 + 警告」即可 |

### 任务 7：降噪开关 — 决定做还是从 UI 隐藏

> **对标**：闪电说的降噪（基于 RNNoise 等模型）
> **抄的定义**：环境噪音过滤 → 提升 ASR 准确率

| 维度 | 规格 |
|------|------|
| **输入** | PCM 音频流 |
| **输出** | 降噪后 PCM 音频流 |
| **触发** | 自动（录音期间，如果开关开启） |
| **决策点** | 如果做：引入 RNNoise / WebRTC 降噪模块到 `audio_capture.py`。如果不做：从 `settings.html` 移除 `toggleNoiseSuppress` 控件。**依赖产品决策** |
| **不抄** | 不抄闪电说的 AI 降噪模型（云端处理） |

### 任务 8：语气词过滤 — 决定做还是从 UI 隐藏

> **对标**：闪电说的口语废词清理（在 Prompt 的 Critical Rule 4 中已实现）
> **抄的定义**：删除"那个""呃""然后呢"等无意义填充词

| 维度 | 规格 |
|------|------|
| **输入** | 原始 ASR 文本 |
| **输出** | 移除口语废词后的文本 |
| **触发** | 自动（AI 纠错阶段，已在 Prompt 规则中声明） |
| **决策点** | 闪电说 System Prompt 的 Critical Rule 4 已要求模型删除口语废词。如果 AI 足够听话，不需要额外规则引擎。如果发现 AI 不删口语词，再加规则引擎。**建议：先验证 AI 效果，效果不够再补** |
| **不抄** | 不抄独立的口语词过滤规则引擎（先用 Prompt 解决） |

---

## 七、执行优先级

```
现在就可以动手（改动明确、无依赖）:
  ✅ 任务 1 — 浮窗降级警告（1 行标签）
  ✅ 任务 2 — AI_ERROR 接线（3 处小改动）
  ✅ 任务 3 — 麦克风持久化（2 处小改动）
  ✅ 任务 4 — 语言选择（2 处小改动）

需要读懂 reference/ 后再动手:
  ⬜ 任务 5 — App 策略表补全（需对照 reference/focus_context.js）

需要产品决策:
  ⏸️ 任务 7 — 降噪做不做
  ⏸️ 任务 8 — 语气词要不要独立规则

需要架构评估:
  ⬜ 任务 6 — UIPI 管理员窗口（可能涉及 Windows 安全模型）

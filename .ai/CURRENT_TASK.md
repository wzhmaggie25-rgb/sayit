# Current Task

> 最后一次更新：2026-06-26

## 状态

**DONE** — 自动化已完成；实机最终验收（用户连按 3 次 RAlt + 观察 `/api/diagnostics/hotkey`）仍需用户手动确认。

**最终提交 SHA：** `5084f7d1ecca6cda2f858b1006fb15ae059007f6`

**待用户真实物理 RAlt 三次验收。** 验收流程见 `.ai/ZCODE_REPORT.md` 的"人工实机验收指引"。

## 任务名称

修复实机第二次 RAlt 仍无响应，以及静默学习把错误内容或整句自动加入个人词典的问题。

## 基线与分支

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 本任务基线 HEAD：`d6fd8544730a66e90dd0ad16a6a12a613d889053`
- 稳定备份：commit `0d69a98`，tag `local-working-2026-06-25`

开始前必须确认：

1. 当前分支严格为 `feature/silent-learning-stabilization`；
2. 已拉取本任务提交；
3. 工作目录除桥梁运行文件外干净；
4. 不修改 `main`、`backup/*` 或稳定 tag；
5. 不 force push，不执行 `reset --hard` 或 `git clean`；
6. 先阅读 `AGENTS.md`、`.ai/PROJECT_STATE.md`、本文件、上一轮 `.ai/ZCODE_REPORT.md` 和 `.ai/TEST_RESULTS.md`；
7. 不读取、复制、上传或修改用户真实数据库、真实词典、录音、完整日志或个人文本。

本任务允许自主完成诊断、实现、测试、返工和复测。不要在中间步骤等待用户选择。只有涉及删除用户数据、修改 ASR/AI 供应商、发布正式版本或合并 main 时才可标记 BLOCKED 等待人工决策。

## 用户最新实机反馈

### A. 静默学习/个人词典异常

用户在个人词典中看到数个自己没有主动添加的新条目，已手工删除。

已知现象：

1. 新条目中既有词，也有完整句子；
2. 至少有一句用户可以明确确认并不是自己想加入词典的内容；
3. 用户怀疑实际过程是：语音输入本身有错误，用户修改后，系统却把错误内容或错误方向的内容加入了词典；
4. 不得假设用户记错，也不得只解释为“正常自动学习”。必须按产品缺陷处理。

### B. RAlt 实机故障仍存在

用户实际操作仍是：

1. 第一次完整按下并松开右 Alt：开始录音；
2. 第二次完整按下并松开右 Alt：没有可见反应，录音继续；
3. 第三次完整按下并松开右 Alt：才停止；
4. 这与上一轮声称修复的问题一致，说明上一轮自动化测试没有覆盖真实故障链路，或者用户实际运行的二进制不是上一轮构建产物。

## 已确认的代码审计风险

### 1. 词典提取策略明确偏向误加

`domain/correction.py::extract_dictionary_terms()` 的注释和实现当前采用“false positives are far less harmful than missed words”的宽松策略。

风险包括：

- multi-token replacement 会把多个新 token 分别加入词典；
- character-level diff 会把任意长度不少于 3 的 replacement 加入；
- character-level 分支没有可靠的“词而不是句子”边界判断；
- 没有中文句子标点、空格、语法片段、长度和 token 数量的严格门禁；
- `SilentMonitor._auto_add_dictionary_terms()` 会直接持久化这些候选；
- 个人词典 UI 不显示来源，用户无法区分手工词和静默学习词。

这足以解释“整句进入词典”，必须修复，不能仅增加测试说明。

### 2. 上一轮 1000 toggle 压力测试绕过了物理按键解析

`tests/test_keyboard_helper_stress.py` 使用 `__test_trigger_toggle()`，它直接调用 `EmitToggle()`，没有覆盖：

- 真实 `HookProc` 的 RAlt down/up 状态机；
- `VK_RMENU` 与 `VK_MENU + LLKHF_EXTENDED` 的实际组合；
- AltGr/Ctrl+Alt 相关序列；
- 自动重复 keydown；
- `ForceReleaseAlt()` 产生的 injected keyup 与物理 keyup 的交互；
- 第二次完整按键是否真的产生第二个 emit；
- 运行时是否加载了正确路径、正确版本的 DLL。

因此上一轮“1000 次零丢失”不能证明真实 RAlt 第二次按键链路正确。

### 3. Python 分发仍可能延迟或乱序

当前链路为：

`HookProc -> atomic/event -> C++ worker -> ctypes callback -> 每次 toggle 新建 daemon Python thread -> orchestrator.toggle_recording()`

必须审计：

- C++ worker 进入 Python 时等待 GIL 的实际延迟；
- 每次新建一个 `hotkey-dispatch` 线程是否可能乱序或竞态；
- 第二次 stop callback 是否延迟到第三次按键附近才执行；
- pipeline 状态读取时是否仍处于预期 `CAPTURING`；
- UI 没反应究竟是 native 未 emit、Python 未收到、orchestrator 忽略，还是 stop 已请求但 UI 未及时更新。

### 4. 可能存在运行二进制陈旧或路径不一致

必须核实用户通常启动的 SayIt 实例实际加载哪个：

- Python/server 源码目录；
- `sayit_keyboard_helper.dll` 的绝对路径；
- DLL ABI/构建版本；
- 是否仍有旧进程占用旧 DLL；
- 桌面或 Electron 启动入口是否指向另一套安装目录/产物。

不能只看仓库文件存在就认定用户运行的是新版本。

## 总体目标

必须同时完成：

1. 静默学习不得再把完整句子、普通表达、错误方向内容或不明确候选自动加入个人词典；
2. 自动加入词典时，只允许非常明确的“用户把错误 token 改成正确专有词/术语”的 replacement 侧候选；
3. 原始错误片段绝不能作为词典词写入；
4. 真实 RAlt down/up 解析链路必须有自动化覆盖；
5. 第二次 RAlt 必须可靠、低延迟地发出 stop 请求；
6. 必须能证明运行时加载的是本轮构建的 DLL，而不是旧产物；
7. 自动化测试与实机待验证项必须明确区分，不得再次用绕过 HookProc 的测试宣称物理按键已验证。

## 必须实施：A. 收紧静默学习与词典写入

### A1. 分离“纠错规则学习”和“个人词典自动添加”

纠错规则可以继续从局部编辑中学习，但个人词典必须使用更严格的独立门禁。

禁止再使用“宁可误加也不要漏掉”的策略。个人词典是 ASR 热词和 AI 保留词来源，误加整句会持续污染后续识别和纠错，false positive 属于高风险。

### A2. 词典候选硬性要求

自动写入个人词典的候选必须全部满足：

1. 候选只能来自 `edited_text` 的 replacement 侧；
2. 必须是局部、单一、可解释的替换，不允许整个输入段落或大范围 diff；
3. 必须能证明原 token 被用户替换成候选 token，方向不可反转；
4. 单次编辑最多自动添加 1 个词；
5. 禁止包含句号、问号、感叹号、逗号、分号、冒号、换行、制表符或明显句子标点；
6. 禁止包含多个中文语义片段或超过合理 token 数；
7. 禁止以整句、从句、普通短语、命令、路径、URL、代码片段、纯数字或空白拼接内容入库；
8. 长度必须保守：英文/混合专名和中文术语分别设计合理上限，并写测试证明完整句子一定被拒绝；
9. 候选必须明显像专有名词、品牌、人名、产品名、技术术语或用户明确修正出的词，而不是普通句子；
10. 如果无法高置信判断，宁可不加入词典；纠错规则仍可按其自己的安全规则处理。

不要仅靠固定长度一个条件。需要结合 token 数、标点、空白、替换范围和词形判断。

### A3. 防止方向反转和基准错误

增加断言/测试，覆盖：

- `错误词 -> 正确词`：只允许正确词成为词典候选；
- `正确词 -> 错误词`：不能把原正确词误当成新候选；
- 原输入错误、用户修正后，原错误整句绝不能入词典；
- 输入框前后已有文本时，只比较本次注入区域，不得把周围文本拼进候选；
- 用户追加新句子、继续写作、删除整段、移动光标或切换输入框时，不得自动加词；
- AI 整理后的 `final_text` 是跟踪基线，但用户未实际编辑时不得学习；
- context 读取短暂失败、anchor 丢失或字段快照错位时必须跳过，不得猜测。

### A4. 默认安全措施

如果无法在本轮可靠证明个人词典候选提取安全，则应临时停止“静默学习自动写入个人词典”，但保留：

- 用户手工添加词典；
- 静默学习纠错规则；
- 历史编辑状态。

这种情况下必须在报告中明确说明，不得偷偷改变。不要删除用户已有词典，不做任何数据库清洗。

### A5. 词典来源可追踪

优先使用不破坏现有数据库的方式，让运行时和测试能区分：

- 手工添加；
- 内置 core hotword；
- 静默学习自动添加。

如确需 schema 迁移，必须向后兼容、可回滚、不触碰现有用户数据内容，并添加迁移测试。若非必要，本轮不要扩大到 UI 大改。

## 必须实施：B. 真实 RAlt 链路诊断与修复

### B1. 运行时二进制身份

为 keyboard helper 增加稳定的版本/ABI 查询，例如导出版本号或 build identifier，并在 Python 启动日志中记录：

- DLL 绝对加载路径；
- helper ABI/version；
- 构建架构；
- 当前进程 PID；
- hook 安装结果。

不得记录用户语音或输入文本。

如果存在 build/Release、bin、安装目录多份 DLL，必须查清实际启动入口和优先级，防止加载陈旧产物。必要时修复构建/复制流程，使用户正常启动的实例确定加载本轮 DLL。

### B2. 覆盖 HookProc 的按键状态机

重构出可测试但与生产共用的 RAlt 事件解析函数，或增加只在测试使用的原生入口，让测试能够输入真实等价的键盘事件字段：

- vkCode；
- WM_KEYDOWN / WM_SYSKEYDOWN / WM_KEYUP / WM_SYSKEYUP；
- LLKHF_EXTENDED；
- LLKHF_INJECTED；
- 自动重复序列。

测试必须覆盖：

1. `VK_RMENU down -> up` 产生且只产生 1 个 toggle；
2. 连续三次完整 down/up 产生 3 个 toggle，不得出现 1、0、1；
3. `VK_MENU + LLKHF_EXTENDED` 等价序列同样正确；
4. auto-repeat down 不重复；
5. injected ForceReleaseAlt 事件不改变物理按键状态机；
6. stray up 不产生 toggle；
7. AltGr/Ctrl+Alt 相关序列不会吞掉下一次 RAlt；
8. 安装/卸载后状态复位。

测试入口不得只是直接调用 `EmitToggle()`。

### B3. 全链路时序证据

增加脱敏的环形诊断计数/时间戳，至少能关联：

- native physical down sequence；
- native physical up sequence；
- native emitted toggle sequence；
- Python callback received sequence；
- orchestrator action：start / stop_requested / ignored；
- 当时 pipeline state；
- 从 native emit 到 orchestrator action 的延迟。

只记录序号、状态、单调时钟和线程信息，不记录用户文本。正常日志不可无限增长。

测试应断言第二个 sequence 必须映射到 `stop_requested`，不能等到第三个 sequence。

### B4. 串行、有序、低延迟的 Python 消费

审计并修复“每个 toggle 创建一个独立 daemon thread”的竞态。要求：

- toggle 按 native sequence 串行消费；
- 不乱序；
- 不重复；
- stop 请求不能被后来的 start/ignore 抢先；
- callback/consumer 异常不能永久停掉后续热键；
- 在可控 GIL 压力下测量并限制 event-to-action 延迟；
- 不允许通过 sleep 或 debounce 吞掉合法的第二次按键。

可采用单一 Python consumer、sequence drain、原生队列/轮询等架构，但必须给出为何真实第二次按键不会延迟到第三次的证据。

### B5. stop 请求立即可见

当第二次 RAlt 被接受时：

- 立即设置 stop flag；
- 立即发出 UI “停止/处理中”状态；
- 不得等待 `audio_capture.stop()`、ASR finish 或 AI 后处理后才给可见反馈；
- 重复 stop 只能幂等处理；
- 处理阶段的后续 RAlt 仍不得启动并发 pipeline。

### B6. 启动入口核查

在本机检查用户常用启动方式对应的实际进程和路径，包括但不限于 Electron 主进程、Python 后端和 DLL。报告中必须写明：

- 实际检查到的启动命令/路径；
- 本轮构建产物路径；
- 二者是否一致；
- 如果不一致，如何修复；
- 如何让用户下一次启动时确定运行新版本。

不得提交本地绝对用户名路径、Token 或隐私信息；报告可使用仓库相对路径和脱敏描述。

## 必须增加的测试

### 1. 静默学习词典安全测试

至少覆盖：

- `wrld -> world` 可按策略成为候选；
- 中文专有词局部替换可成为候选；
- 完整中文句子 replacement 被拒绝；
- 含 `，。！？；：` 的内容被拒绝；
- 多 token 普通短语被拒绝；
- 用户在注入文本后继续追加一句话，不入词典；
- 用户删除或改写超过安全范围，不入词典；
- 周围已有文本不被拼入；
- 原错误词/原错误句永远不会作为候选写入；
- 单次最多加入一个；
- 不确定 diff 返回空候选；
- 纠错规则与词典候选分别测试，避免一个放宽另一个。

### 2. HookProc 真实等价事件序列测试

必须直接覆盖生产按键解析逻辑，不得调用 `EmitToggle()` 代替。

连续至少 1000 轮完整 RAlt down/up，并混入：

- repeat down；
- injected keyup；
- stray up；
- VK_RMENU 与 extended VK_MENU 两种表示；
- AltGr 相关 Ctrl 事件。

每轮产生 exactly one toggle，顺序一致。

### 3. Native -> Python -> Orchestrator 顺序测试

至少验证：

- seq 1 -> start；
- seq 2 -> stop_requested；
- seq 3 在处理中 -> ignored；
- seq 2 不得在 seq 3 之后执行；
- GIL 压力下无丢失、无乱序；
- consumer 异常后能继续处理后续事件；
- 不创建无界 daemon 线程。

### 4. 运行时版本/路径测试

- Python 能读取 helper version；
- 旧 ABI 明确报错而不是静默继续；
- 加载日志包含脱敏绝对路径和版本；
- 优先级测试防止错误加载旧 DLL；
- 构建后实际加载文件的版本与预期一致。

### 5. 现有回归

运行所有与以下模块有关的测试：

- keyboard helper；
- orchestrator；
- pipeline；
- audio lifecycle；
- silent monitor；
- correction；
- dictionary/hotwords；
- injector；
- context helper；
- Agent Bridge。

不得删除、跳过或放宽现有失败测试来制造通过。

## 人工实机验证支持

自动化完成后，提供一个简单、可关闭、脱敏的诊断方式，让用户下一轮只需做三次 RAlt 操作，就能得到类似以下证据：

- `seq=1 native_emit -> python_receive -> start`
- `seq=2 native_emit -> python_receive -> stop_requested`
- `seq=3 ... -> ignored(processing)`

不得要求用户上传完整日志；应能只复制这几行脱敏诊断。正常模式默认不要持续输出高频调试。

本任务可以在自动测试完成后标记 DONE，但报告必须明确写：

- 自动化验证完成；
- 真实物理键盘最终验收仍需要用户按三次 RAlt 验证；
- 不得把测试入口模拟结果描述成“实机已验证”。

## 允许修改

- `native/context_helper/src/keyboard_helper.cpp`
- `native/context_helper/CMakeLists.txt`（仅 helper 构建/版本/测试所必需）
- `infrastructure/keyboard_helper_dll.py`
- `application/orchestrator.py`
- `application/pipeline.py`（仅 stop 状态/事件所必需）
- `application/eventbus.py`（仅状态事件所必需）
- `domain/correction.py`
- `infrastructure/silent_monitor.py`
- `infrastructure/hotwords_manager.py`
- `infrastructure/database.py`（仅确需来源追踪且向后兼容时）
- 启动/构建脚本（仅修复实际加载旧 DLL 所必需）
- 与本任务直接相关的测试文件/测试夹具
- `.ai/CURRENT_TASK.md`
- `.ai/ZCODE_REPORT.md`
- `.ai/TEST_RESULTS.md`
- `.ai/PROJECT_STATE.md`（架构或已知问题确有变化时）
- `CHANGELOG.md`

## 禁止修改

- ASR 供应商、识别模型、AI 纠错供应商；
- 音频算法、增益、采样率；
- 用户真实数据库、真实词典、历史数据；
- Electron 页面视觉重做；
- Agent Bridge 代码、权限配置和启动脚本；
- `main`、`backup/*`、稳定 tag；
- 凭据、个人配置、数据库、录音或完整日志；
- 禁止安装/升级 Claude Code；
- 禁止 force push、reset --hard、git clean。

## 验收标准

只有同时满足以下条件才能标记 DONE：

1. 代码审查证明完整句子和普通多词短语不能被静默加入个人词典；
2. 原错误内容不能以反向 diff 或基准错位方式入词典；
3. 单次编辑最多自动加入一个高置信词；
4. 不确定编辑安全跳过，不猜测；
5. HookProc 生产按键解析逻辑有真实等价事件测试，不再只测 `EmitToggle()`；
6. 连续三次完整 RAlt 等价序列产生 3 个有序 sequence；
7. seq 2 在全链路测试中执行 `stop_requested`，不能等到 seq 3；
8. Python 消费有序且不创建无界线程；
9. 第二次 stop 被接受时立即发出可见状态；
10. 能查询并记录实际加载 DLL 的路径和版本；
11. 查明用户常用启动入口是否加载本轮 DLL；
12. 相关新增测试和现有回归全部通过；
13. 不读取或修改用户真实数据；
14. 只修改允许范围内文件；
15. 更新报告，写明根因、实现、关键命令、退出码、测试数量、自动验证边界、真实限制和风险；
16. 提交并推送当前 feature 分支。

建议最终提交信息：

```text
fix: make RAlt delivery observable and silent learning conservative
```

完成后：

- 将本文件状态改为 `DONE`；
- 写明最终完整提交 SHA；
- 明确标记“待用户真实物理 RAlt 三次验收”；
- 停止，不继续开发其他功能。

如果无法完成任一核心断言：

- 将状态改为 `BLOCKED`；
- 写明具体、脱敏的阻塞原因和已经取得的证据；
- 不得用绕过 HookProc 的测试、仅字典列表可刷新或口头说明代替核心验收。

# Current Task
> 最后一次更新：2026-06-26

## 状态

**DONE**

完成 SHA：`d6fd8544730a66e90dd0ad16a6a12a613d889053`

68 个用例通过，1 个允许跳过（COM/UIA 在无交互 CI 中 skip）。新增核心断言（hook 传输、状态机、注入兜底、Win32 集成）均未通过 skip 规避。

## 任务名称

彻底修复长时间语音输入时第二次 RAlt 无响应、第三次才停止，以及识别结果只进入历史记录却没有注入原输入框的问题。

## 基线与分支

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 本任务基线 HEAD：`99bec879484a1fc225d3a6e6413d4fc3fa095a58`
- 稳定备份：commit `0d69a98`，tag `local-working-2026-06-25`

开始前必须确认：

1. 当前分支严格为 `feature/silent-learning-stabilization`；
2. 已拉取本任务提交；
3. 工作目录除桥梁运行文件外干净；
4. 不修改 `main`、`backup/*` 或稳定 tag；
5. 不 force push，不执行 `reset --hard` 或 `git clean`；
6. 先阅读 `AGENTS.md`、`.ai/PROJECT_STATE.md`、本文件以及相关历史报告。

本任务允许自主完成诊断、实现、测试、返工和复测，不要在中间步骤等待用户选择。只有涉及删除用户数据、修改产品核心交互、替换 ASR/AI 供应商、发布正式版本或合并 main 时才可标记 BLOCKED 等待人工决策。

## 用户可见故障

1. 第一次按 RAlt：正常开始录音；
2. 长时间输入后第二次按 RAlt：没有响应，录音没有立即停止；
3. 第三次按 RAlt：才开始停止或进入识别；
4. 最终识别文字可在历史记录中看到，但没有进入原输入框，需要手工复制粘贴；
5. 这是曾经修复过但仍会复现的老问题。

## 已确认的代码审计结论

### A. Hook 线程仍会直接进入 Python

`native/context_helper/src/keyboard_helper.cpp` 当前在 `WH_KEYBOARD_LL` 的 `HookProc` 中直接调用：

```cpp
if (g_callback) {
    g_callback();
}
```

`infrastructure/keyboard_helper_dll.py` 虽然把业务 callback 包装为 `_dispatch()` 并新建 daemon 线程，但 ctypes 必须先从 C++ Hook 线程进入 Python、等待 GIL、执行 `_dispatch()` 后才能返回。

因此长录音、音频处理或其他 Python 工作造成 GIL 竞争时，Hook 线程仍可能超过 Windows `LowLevelHooksTimeout`，被系统静默卸载，导致第二次 RAlt 丢失。

### B. Pipeline 在后处理完成前被过早解除互斥

`application/orchestrator.py::_on_hotkey_stop()` 当前在音频停止后把：

```python
self._pipeline_active = False
self._pipeline = None
self._pipeline_thread = None
```

但旧 pipeline 线程仍继续执行 ASR、AI 整理、注入和历史保存。此时第三次 RAlt 可能启动新 pipeline，造成共享音频、注入器和窗口焦点竞争。

### C. 注入失败存在提前返回路径

`infrastructure/injector.py::inject()` 在恢复目标窗口后，如果前台窗口仍与目标 HWND 不一致，会直接返回 `False`。该路径可能绕过最终剪贴板兜底，导致结果只写入历史记录而没有进入输入框，也没有可靠保留到剪贴板。

## 总体目标

必须同时解决：

1. RAlt 事件可靠性；
2. 录音/处理状态互斥；
3. 原目标输入框恢复与注入可靠性；
4. 注入失败时的可靠剪贴板兜底与明确状态；
5. 自动化回归测试，防止再次出现“看似修好、长输入又复现”。

## 必须实施

### A. HookProc 不得再调用 Python

重构键盘事件传递，使 `HookProc` 中只做常数时间、无阻塞、无需 Python GIL 的原生操作，然后立即返回。

可采用但不限于：

- 原子递增的 toggle sequence + Python 独立轮询线程；
- 原生无锁/轻量事件队列 + Python 消费线程；
- 原生 worker 线程转发，但必须证明 HookProc 本身不调用 ctypes/Python callback、不等待 GIL。

硬性要求：

1. `HookProc` 不得直接或间接执行 Python callback；
2. 不得在 HookProc 中创建 Python线程、等待锁、等待事件、执行窗口查询、录音操作或日志 I/O；
3. 每次完整 RAlt 按下/松开只产生一个 toggle；
4. 自动重复 keydown 不得产生重复 toggle；
5. 安装、卸载和进程退出必须无悬空 callback、无 detached 线程竞态、无 UAF；
6. 保持注入事件过滤，程序自己的 `SendInput` 不得再次触发热键；
7. 不改成依赖 Electron N-API addon，不恢复已经废弃的双 Hook 架构。

### B. 建立明确的运行状态门禁

至少区分：

- 空闲；
- 开始中/录音中；
- 已请求停止；
- 识别/整理处理中；
- 注入中；
- 完成或错误。

行为要求：

1. 空闲时按 RAlt：开始录音；
2. 录音中按 RAlt：只请求停止一次，并立即向 UI 发出停止/处理中状态；
3. 已请求停止、识别、整理或注入期间再次按 RAlt：不得启动第二条 pipeline，不得重新占用音频设备；应安全忽略或发出“正在处理”状态；
4. 只有旧 pipeline 完成注入、历史保存并进入 DONE/ERROR 后，才能释放 `_pipeline_active` 并允许下一次录音；
5. 不得通过过早把 `_pipeline=None` 来实现“快速开始下一次”；
6. 任何异常路径都必须最终释放状态，不能永久卡死。

### C. 修复目标窗口恢复与注入兜底

1. 继续以录音开始时捕获的 `InjectionTarget` 为主要目标；
2. 注入前释放可能残留的 Alt/Ctrl/Shift 状态；
3. 目标窗口恢复失败时，进行有限、明确的重试，不得无限循环；
4. 对可直接定位的 Win32 子编辑控件优先使用安全的控件级注入；
5. 任何返回 `False` 的路径都必须确保最终文字仍保留在剪贴板；
6. 不得把“成功发送 Ctrl+V”直接等同于“目标输入框已收到文字”；在可验证的控件中应读取回验证；
7. 历史记录继续保存最终文字，并准确记录 `pasted/status/error_msg`；
8. 注入失败应通过现有事件系统明确提示“文本已保存到历史和剪贴板，但未注入目标输入框”。

### D. 保留 COM 修复并做回归

不得撤销提交 `99bec879...` 中的 COM apartment 修复。

运行现有：

- DLL/EXE 构建；
- EXE `ping` / `get_full_context`；
- `tests/test_context_helper_dll_com.py`。

现有 UIA 测试允许在无交互 CI 中 skip，但本任务新增的热键传输、状态机和注入兜底核心测试不得通过 skip 规避。

## 必须增加的测试

### 1. 原生 Hook 事件传输压力测试

建立不依赖用户手工连续按键的可重复测试夹具，验证原生事件生产到 Python消费的通路。

至少验证：

- 在 Python 主线程/其他线程持续制造高 GIL 压力时，连续生产不少于 1000 个测试 toggle；
- 消费数量与生产数量完全一致；
- 顺序一致；
- 每个事件仅消费一次；
- Hook 事件生产函数本身不进入 Python callback；
- 安装/卸载循环至少 20 次无崩溃、无残留线程。

测试夹具不得削弱生产路径；可以增加专用测试导出或测试模式，但必须隔离、说明并确保不会被普通物理按键误触发。

### 2. Orchestrator 状态机测试

至少覆盖：

- 第一次 toggle 开始；
- 第二次 toggle 请求停止；
- 处理中第三次 toggle 不会启动新 pipeline；
- 旧 pipeline 完成后才允许下一次开始；
- ASR异常、注入异常后状态仍释放；
- 快速双击/重复 keydown 不产生并发 pipeline。

### 3. 注入失败兜底测试

至少覆盖：

- 目标窗口恢复失败；
- 前台 HWND 与目标不一致；
- UIA失败；
- Clipboard快捷键失败；
- SendInput失败；
- 所有失败路径最终剪贴板包含 final_text；
- 历史状态与事件提示正确。

### 4. Windows 编辑控件集成测试

优先创建一个由测试自身启动和清理的本地 Win32 `Edit`/等价输入控件夹具，不依赖新版 Notepad 的多进程/窗口结构。

验证完整链路：

- 捕获目标；
- 开始/停止模拟 pipeline；
- 处理期间不能启动第二条；
- 将唯一 sentinel 注入原编辑控件；
- 从控件读取回 sentinel；
- 清理进程/窗口。

### 5. 现有回归

运行所有与以下模块有关的现有测试：

- keyboard helper；
- orchestrator；
- pipeline；
- injector；
- audio lifecycle；
- context helper；
- silent monitor。

不得删除、跳过或放宽已有失败测试来制造通过。

## 允许修改

- `native/context_helper/src/keyboard_helper.cpp`
- `native/context_helper/CMakeLists.txt`（仅键盘 helper 导出/测试所必需）
- `infrastructure/keyboard_helper_dll.py`
- `application/orchestrator.py`
- `application/pipeline.py`（仅状态/事件所必需）
- `infrastructure/injector.py`
- `application/eventbus.py`（仅确有必要的现有事件扩展）
- 与本任务直接相关的测试文件/测试夹具
- `.ai/CURRENT_TASK.md`
- `.ai/ZCODE_REPORT.md`
- `.ai/TEST_RESULTS.md`
- `CHANGELOG.md`（简要记录）

## 禁止修改

- ASR供应商、识别模型、AI纠错供应商；
- 音频算法、增益、采样率；
- 数据库 schema 和用户历史数据；
- 静默学习规则算法；
- Electron 主架构和页面设计；
- Agent Bridge 代码、权限配置和启动脚本；
- `main`、`backup/*`、稳定 tag；
- 凭据、个人配置、数据库、录音或日志；
- 禁止安装/升级 Claude Code；
- 禁止 force push、reset --hard、git clean。

## 验收标准

只有同时满足以下条件才能标记 DONE：

1. 代码审查证明 `HookProc` 不再调用 Python/ctypes callback，也不等待 GIL；
2. 1000 次高负载 toggle 压力测试零丢失、零重复；
3. 20 次安装/卸载循环无崩溃、无残留；
4. 处理中第三次 RAlt 不会启动第二条 pipeline；
5. pipeline 在注入和历史保存结束前保持互斥；
6. Windows 本地编辑控件集成测试能够把 sentinel 注入原目标并读取回；
7. 所有注入失败路径保证 final_text 留在剪贴板；
8. 历史记录和 UI 事件准确反映注入成功/失败；
9. COM DLL/EXE 回归未被破坏；
10. 相关现有测试全部通过；
11. 只修改允许范围内文件；
12. 更新报告，写明根因、实现、命令、退出码、测试数量、真实限制和风险；
13. 提交并推送当前 feature 分支。

建议最终提交信息：

```text
fix: make Alt stop and text injection reliable
```

完成后：

- 将本文件状态改为 `DONE`；
- 写明最终完整提交 SHA；
- 停止，不继续开发其他功能。

如果无法完成任一核心断言：

- 将状态改为 `BLOCKED`；
- 写明具体、脱敏的阻塞原因和已经取得的证据；
- 不得用 skip、仅 JSON 可解析、仅历史记录有文本或手工口头说明代替核心验收。
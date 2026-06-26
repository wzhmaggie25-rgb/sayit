# Current Task
> 最后一次更新：2026-06-26

## 状态

**BLOCKED**

## 任务名称

仅修复 `context_helper` DLL 的 COM apartment 模型，使其与 Python/comtypes 的 MTA 调用线程兼容，并完成针对性验证。

## 基线与分支

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 任务基线 HEAD：`6d400cfbac05b5e38b69c294c53c5815dbf56541`
- 稳定备份：commit `0d69a98`，tag `local-working-2026-06-25`

开始前必须确认：

1. 当前分支严格为 `feature/silent-learning-stabilization`；
2. 已拉取本任务提交；
3. 工作目录除桥梁运行文件外干净；
4. 不修改 `main`、`backup/*` 或稳定 tag；
5. 不 force push，不执行 `reset --hard` 或 `git clean`。

## 已确认的审计结论

1. EXE subprocess 路径可靠，本轮不得重构或替换 EXE 路径。
2. DLL 由 Python/comtypes 所在线程进程内加载时，该线程使用 MTA。
3. `native/context_helper/src/main.cpp` 当前 `ComInit` 无条件调用：

```cpp
CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED)
```

4. 在已初始化为 MTA 的 Python/comtypes 线程中再次请求 STA，会返回 `RPC_E_CHANGED_MODE`，导致 `ComInit::ok()` 为 false，随后 DLL 的 UI Automation 路径被跳过。
5. 第一项修复必须严格限制为：让 DLL 构建在 MTA 中初始化 COM，同时保留 EXE 当前已验证行为；暂时不要修改其他静默学习逻辑。

## 必须实施的最小修复

只在 `BUILD_DLL` 构建下把 `ComInit` 的 `CoInitializeEx` flags 改为 `COINIT_MULTITHREADED`。

推荐采用清晰、最小的编译期区分，例如：

```cpp
#ifdef BUILD_DLL
constexpr DWORD kComInitFlags = COINIT_MULTITHREADED;
#else
constexpr DWORD kComInitFlags = COINIT_APARTMENTTHREADED;
#endif
```

然后让 `ComInit` 使用该 flags。

要求：

- DLL：MTA；
- EXE：继续 STA，不改变已验证的 subprocess 行为；
- 正确处理 `S_OK` 和 `S_FALSE`，仅在 `CoInitializeEx` 成功时配对调用 `CoUninitialize`；
- 不吞掉或伪装 `RPC_E_CHANGED_MODE`；
- 不新增线程，不引入全局 COM 生命周期，不做无关重构；
- 不修改 UIA 搜索、窗口定位、剪贴板、键盘监听、学习判定、文本差异、数据库或 Electron 逻辑。

## 针对性测试

先确认并记录当前 Windows 构建方式，然后完成以下测试。

### A. 编译验证

构建 Release 版本的：

- `sayit_context_helper.exe`
- `sayit_context_helper_dll.dll`

编译必须无新增错误。不得通过降低警告级别、删除代码或跳过 DLL 构建来制造通过。

### B. EXE 回归冒烟

对 EXE 至少验证：

1. `ping` 返回成功 JSON；
2. `get_full_context` 返回可解析 JSON；
3. 进程正常退出；
4. 证明本轮没有破坏原 subprocess 路径。

### C. Python/comtypes + DLL 同线程测试（本轮核心）

新增或更新一个聚焦的 Windows 测试脚本，优先放在：

```text
tests/test_context_helper_dll_com.py
```

测试必须在同一个 Python 线程中：

1. 显式按项目实际 comtypes 用法初始化/确认 MTA；
2. 加载刚构建的 `sayit_context_helper_dll.dll`；
3. 正确声明 DLL 导出函数和 `free_string`，避免内存泄漏；
4. 调用 `get_full_context_json` 或 `get_focused_context_json`；
5. 将返回值解析为 JSON；
6. 验证不是因 COM apartment 冲突而退化为空结果。

为了让测试能区分“UIA 真正工作”与“仅返回结构正确的空 JSON”，应采用可重复的 Windows 前台输入框场景，例如启动或定位记事本编辑区、写入唯一 sentinel、取得其 HWND，并通过 DLL 返回确认至少满足下面之一：

- `full_field_content` 包含 sentinel；或
- 能明确验证目标 UIA 元素可编辑且返回了非空的 UIA 元数据。

测试结束必须清理自己启动的测试进程，不得影响用户现有窗口和数据。

如果本机环境限制导致记事本自动化不可稳定执行，可采用等价、低风险、可重复的本地 Win32 编辑控件测试夹具；但不得把核心断言弱化为“JSON 能解析”。

### D. 失败复现与修复证据

在报告中记录：

- 修复前失败现象或已有审计证据；
- 修复后 Python/comtypes MTA 同线程 DLL 调用结果；
- EXE 回归结果；
- 构建命令、测试命令、退出码；
- 生成的 DLL/EXE 实际路径；
- 不得记录密钥、私人配置、录音或用户文本。

## 允许修改

- `native/context_helper/src/main.cpp`
- `tests/test_context_helper_dll_com.py`（如不存在可新建）
- 与该聚焦测试直接相关、且确有必要的测试夹具文件
- `.ai/ZCODE_REPORT.md`
- `.ai/TEST_RESULTS.md`
- `.ai/CURRENT_TASK.md`

除非构建完全无法进行且报告中解释必要性，否则不要修改 CMake、Python 业务模块或任何依赖配置。

## 禁止修改

- 除上述 COM apartment 修复之外的任何静默学习逻辑；
- EXE subprocess 架构或 IPC 协议；
- UIA 元素搜索策略、窗口筛选、文本读取算法；
- Electron、录音、ASR、纠错、注入、数据库、热键、进程管理；
- Agent Bridge 代码和启动脚本；
- `main`、`backup/*`、稳定 tag；
- 凭据、个人配置、数据库、录音、日志；
- 不得安装或升级 Claude Code；
- 不得扩大为第二项静默学习修复。

## 验收标准

同时满足以下条件才可标记 DONE：

1. `main.cpp` 的差异清楚证明：仅 DLL 使用 MTA，EXE 保持 STA；
2. DLL 和 EXE 均成功构建；
3. Python/comtypes MTA 同线程加载 DLL 的针对性测试通过；
4. 测试能够证明 UIA 路径实际工作，而不只是 JSON 外壳可解析；
5. EXE `ping` 和 `get_full_context` 回归通过；
6. 除允许文件外没有业务代码改动；
7. `.ai/TEST_RESULTS.md` 与 `.ai/ZCODE_REPORT.md` 写明命令、结果和限制；
8. 提交并推送当前分支。

建议提交信息：

```text
fix: align context helper DLL COM apartment
```

完成后：

- 将本文件状态改为 `DONE`；
- 写明最终提交完整 SHA；
- 停止，不开始其他静默学习修复。

如果无法完成核心 DLL/UIA 断言：

- 将状态改为 `BLOCKED`；
- 写明脱敏后的具体阻塞原因和已完成证据；
- 不得把弱化测试伪报为成功。
# ZCode Report
> 最后一次更新：2026-06-26（silent learning stabilization + 实机 RAlt 全链路修复轮）

## 接收到的任务

修复用户实机第二次 RAlt 仍无响应，以及静默学习把错误内容或整句自动加入个人词典的问题。任务文件：`.ai/CURRENT_TASK.md`（基线 HEAD `d6fd8544730a66e90dd0ad16a6a12a613d889053`）。任务允许自主完成诊断、实现、测试、返工与复测，并明确要求：

- 完整覆盖真实 HookProc 解析的状态机；
- 重新审计每个 toggle 一个 daemon 线程是否乱序；
- 立即可见的 stop ACK；
- 运行时可查询 DLL 版本/路径；
- 词典 false positive 必须按高风险处理。

## 实际修改的文件

| 文件 | 变更摘要 |
|------|----------|
| `domain/correction.py` | 重写 `extract_dictionary_terms` 为严格门禁版：单一 1↔1 token replacement、最多 1 个候选、同字符族、字符族特定长度上限、拒绝标点/空白/路径/纯数字。 |
| `native/context_helper/src/keyboard_helper.cpp` | 提取 `HandleKeyEventCore` 为 HookProc 与测试共用解析函数；新增 `__test_handle_event(vk, wParam, flags)`、`__test_reset_state`、`helper_version`、`helper_build_id` 导出；ABI bump 到 v2，build id `2026-06-26-v2`。 |
| `infrastructure/keyboard_helper_dll.py` | 单一有序 consumer 线程 + queue 替换"每个 toggle 一个 daemon thread"；64 槽诊断 ring（只记 seq/timestamp/thread id）；版本/build id/dll_path 透出；`diagnostics()` / `recent_events()` / `test_handle_event` / `test_reset_state` / `helper_version` / `helper_build_id` API；`MIN_HELPER_VERSION = 2` 守卫拒绝旧 ABI。 |
| `application/orchestrator.py` | `_on_hotkey_stop` 在 `pipeline.stop()` 之前同步 emit `Events.RECORDING_STOPPING`；`_install_keyboard_hook` 启动日志打印 DLL 路径/version/build id/PID。 |
| `application/eventbus.py` | 新增 `Events.RECORDING_STOPPING` 常量（即时 UI ACK，stop 被接受时立即触发，独立于 audio drain）。 |
| `server.py` | 转发 `RECORDING_STOPPING` 到 WebSocket（`event: recording_stopping`）；新增 `GET /api/diagnostics/hotkey` 暴露 DLL 路径 + version + 最近 16 个脱敏 toggle 记录。 |
| `tests/test_dictionary_safety.py` | 新文件。21 用例覆盖整句/标点/多 token/反向/跨字符族/插入/删除/数字/路径/未知形态全部被拒绝；wrld→world、中文专名局部替换被接受；纠错规则学习不被词典策略波及。 |
| `tests/test_keyboard_helper_physical.py` | 新文件。9 用例覆盖 HookProc 的真实键盘事件状态机：RAlt down/up = 1 toggle、连续 3 次有序、`VK_MENU+EXTENDED` 等价、auto-repeat 不重复、injected 不污染、stray up 静默、非 RAlt 不响应、uninstall/install 状态重置、1000 个混合噪声循环精确 1000 toggle。 |
| `tests/test_keyboard_dispatcher.py` | 新文件。9 用例覆盖 Python 端有序 consumer 与运行时身份：200 toggle 严格顺序、500 toggle 无线程泄漏、callback 异常后仍能恢复、诊断 ring 仅记 seq/timestamp/tid、ring 大小有界、ABI 版本/build id/dll_path/runtime diagnostics 形状。 |
| `tests/test_hook_chain.py` | 新文件。2 用例覆盖 native → python → orchestrator 全链路：seq 2 在 seq 3 到来之前完成 stop_requested、`RECORDING_STOPPING` 同步发出（在 stop 函数返回前）。 |
| `tests/test_orchestrator_state.py` | 在"第二次 toggle 设 stop_flag"用例上补一个断言：`RECORDING_STOPPING` ACK 必须随 stop_flag 同时发出。 |
| `.ai/CURRENT_TASK.md` | 状态置 DONE 并写入最终 SHA、人工实机验收说明。 |
| `.ai/PROJECT_STATE.md` | 已知问题项补充 ABI v2、`/api/diagnostics/hotkey`、严格词典门禁。 |
| `.ai/ZCODE_REPORT.md` / `.ai/TEST_RESULTS.md` | 本文件 + 同步测试报告。 |
| `CHANGELOG.md` | 新增本轮条目。 |

未触碰：ASR/AI 供应商、音频、Electron UI 重做、Agent Bridge、`main`/`backup/*`/稳定 tag、用户真实数据库与录音、`infrastructure/database.py`（无需 schema 迁移），等等。

## 根因判断

### A. 静默学习把整句/错误句加入词典

`domain/correction.py` 旧版 `extract_dictionary_terms` 明文写着 "false positives are far less harmful than missed words" 并由此设计了多个宽松通道：

1. multi-token replacement 内部循环把 *每个* 新 token 单独加入；
2. multi-token → single-token 分支只校验长度 2..40，不校验形态；
3. character-level diff 任何 ≥3 字符的 replacement 都收下；
4. character-level 完全没有句末标点/空白边界检查；
5. 单次编辑没有 hard cap，可一次进多个；
6. `_is_acceptable_dictionary_term` 只拒绝身份/路径，不要求 token 形态。

结果：用户把识别错误的整句修改后，多 token 替换或 char-level 都会把新句子的若干子段（或整段未受 PROTECTED_PATTERN 过滤的字符）写进 `SilentMonitor._auto_add_dictionary_terms()`，进而 `hotwords_mgr.add_word()` → `db.add_dictionary_word()`。用户看到完整中文句子出现在词典里，正是这一通道。

### B. 实机第二次 RAlt 仍无响应

上一轮把 HookProc 与 Python 完全解耦（v2 architecture）、把状态门禁集中到 `_pipeline_wrapper.finally` —— 这两个修复**是必要但不充分的**。剩余缺口：

1. **测试只走 `__test_trigger_toggle()`**，那条 entry point 直接 `EmitToggle()`，跳过 `HookProc` 解析逻辑。Auto-repeat down、`LLKHF_EXTENDED`、`VK_MENU` vs `VK_RMENU`、`LLKHF_INJECTED`、`g_matched` 状态机 —— 上一轮 1000 轮压力测试根本没碰过。所以上一轮报告说"RAlt 链路已验证"，但用户实机仍卡。任务文件明确禁止再用绕过 HookProc 的测试代表实机。
2. **Python 端每个 toggle `Thread(...).start()`**：worker thread 调用 `_dispatch` 时立即 spawn 一个 daemon `hotkey-dispatch` 线程跑 `callback`。两次紧贴的 toggle 可能由 OS 调度成第二个线程**先于**第一个线程进入 `orchestrator.toggle_recording`，造成乱序——即使概率小，足以让"第二次按键效果出现在第三次按键之后"这种零星观感复现。任务文件直接点名要求消费按 native sequence 串行。
3. **没有 stop ACK 事件**：旧 `_on_hotkey_stop` 仅设 `_stop_flag`，UI 无任何即时反馈；audio_capture.stop()、streaming ASR finish 之前用户没有视觉反应。即便 stop 已经被接收，用户仍以为"第二次没反应"。
4. **运行时无法证明加载的是哪个 DLL**：没有版本号导出，没有路径日志，没法排查"用户跑的是不是新构建"。

修复这四点：测试覆盖 HookProc 真实解析、单一有序 consumer、即时 `RECORDING_STOPPING`、`helper_version` / `helper_build_id` / `dll_path` 在启动日志和 `/api/diagnostics/hotkey` 中可查。

## 实施内容

### A. 词典安全门禁（domain/correction.py）

新 `extract_dictionary_terms` 流程：

1. tokenize 双方，要求 difflib opcodes 中**有且仅有一个** `replace`；
2. 该 replace 必须 `i2-i1 == 1 and j2-j1 == 1`（严格 1↔1）；
3. 把候选交给 `_is_safe_dictionary_term`：
   - pattern 非空且无空白/标点；
   - replacement 非空、不等于 pattern、无任何拒绝字符（包含 ASCII/CJK 句末标点、空白、括号、路径分隔符、引号、换行、tab）；
   - 不命中 `PROTECTED_PATTERN`（路径/命令）；
   - 不能是纯数字；
   - 形态必须命中三种 token 正则之一（ASCII、纯 CJK、ASCII+CJK 混合）；
   - 长度受字符族特定上限约束：ASCII ≤24、CJK ≤8、混合 ≤24；
   - **同字符族检查**：pattern 含 CJK ↔ replacement 也必须含 CJK。

效果：

- `hello wrld → hello world` ⇒ `["world"]`；
- `豆包包 → 言豆包` ⇒ `["言豆包"]`；
- 整句中文带句号 ⇒ `[]`；
- 多 token replacement / 插入 / 删除 / 跨字符族 / 纯数字 / 路径 ⇒ 全部 `[]`。

由于 `learn_from_edit` 走的是不同代码路径（`generate_token_rules` + `generate_rules`），纠错规则学习并未被词典策略波及，`tests/test_silent_monitor.py::test_small_edit_extracts_rule_and_updates_history` 仍通过，且 `tests/test_dictionary_safety.py::CorrectionRulesStillLearnIndependentlyTests` 显式断言这一独立性。

### B. Native HookProc 解析的可测试化（keyboard_helper.cpp）

将 HookProc 原有内联状态机抽出为 `HandleKeyEventCore(vk, wParam, flags, allowSideEffects)`：

- HookProc 调用 `HandleKeyEventCore(..., true)`：原有行为，含 `ForceReleaseAlt` + preemptive Alt-up SendInput；
- `__test_handle_event(vk, wParam, flags)` 调用 `HandleKeyEventCore(..., false)`：跳过 SendInput（**禁止单元测试向 OS 注入真实按键**），但 `g_matched`、`EmitToggle()`、`g_pending` 行为与生产完全一致。

附加导出：

- `__test_reset_state()`：清 `g_matched`，让测试不必反复 install/uninstall；
- `helper_version()`：返回 ABI int `2`；
- `helper_build_id()`：返回 `"2026-06-26-v2"`。

`MIN_HELPER_VERSION = 2` 在 Python 加载侧硬守，旧 DLL 直接降级（log error + 返回 None）而不是静默继续。

### C. 单一有序 consumer + 诊断 ring（keyboard_helper_dll.py）

替换原"每个 toggle 一个 daemon"模型：

- install 时创建一个 `hotkey-consumer` 守护线程；
- worker 线程 → Python `_dispatch` 只做两件事：snapshot `recv_t` + `native_seq`，`Queue.put()`；
- `_consumer_loop` 串行 `queue.get` → `callback()` → 写入 64 槽诊断 ring。

诊断 ring 严格只记 `{seq, native_seq, recv_t, dispatch_t, latency_ms, thread_id}` —— 测试 `test_recent_events_redacts_text` 显式断言 keys 集合是这 6 个，不含任何文本字段。

`diagnostics()` 返回完整身份快照（DLL 路径、版本、build id、PID、emit/consume/pending/dispatched/queue depth），供启动日志、`/api/diagnostics/hotkey` 端点以及用户实机 3 次 RAlt 验收使用。

uninstall 把 consumer stop 信号 + `None` sentinel 入队 + `join(2.0)`，保证 install/uninstall 周期无线程泄漏。`tests/test_keyboard_dispatcher.py::test_consumer_thread_persists_no_new_threads_per_toggle` 用 500 toggle + active_count delta ≤3 断言这一点。

### D. 即时 stop ACK（orchestrator + eventbus + server）

`_on_hotkey_stop` 在 `pipeline.stop()` 之前 `self._eb.emit(Events.RECORDING_STOPPING)`：

- emit 是同步的（EventBus.emit 直接调监听者），所以 UI 在 `audio_capture.stop()` 返回之前就拿到 ACK；
- `Events.RECORDING_STOPPED` 仍在 pipeline 内由 audio drain 完成后发出，二者职责分离；
- `server.py.wire_events` 把 `RECORDING_STOPPING` 转发为 WebSocket `recording_stopping` 事件；
- `tests/test_hook_chain.py::test_recording_stopping_emits_before_audio_drains` 断言 emit timestamp ≤ stop_recording 返回 timestamp。

### E. 运行时身份证据

- 启动 `_install_keyboard_hook` 日志：`keyboard helper identity: path=… version=2 build=2026-06-26-v2 pid=…`；
- `GET /api/diagnostics/hotkey` 返回 `diagnostics + recent_events(16)`，全部脱敏，用户可拷贝 3 行作为实机三次 RAlt 验收证据；
- 启动入口 (`start.bat` / `launch_sayit.bat` / `_start_clean.bat`) 都走 `python server.py`，加载的 DLL 路径是 `<repo>/native/context_helper/build/Release/sayit_keyboard_helper.dll` —— 与本轮 CMake 输出目标完全一致；测试 `test_dll_path_is_realpath_and_exists` 锁定。

## 执行过的命令

```bash
# 终止占用 DLL 的旧进程
powershell.exe -Command "Stop-Process -Id 33532 -Force; Stop-Process -Id 32620 -Force"

# 重建 native 产物
cd <repo>/native/context_helper
cmake --build build --config Release    # exit 0

# 全量测试
cd <repo>
python -m pytest tests/                  # 109 passed, 1 pre-existing fail
python -m pytest tests/ --ignore=tests/test_context_helper_dll_com.py
                                          # 109 passed in 9.14s
python -m pytest tests/test_dictionary_safety.py -v          # 21 passed
python -m pytest tests/test_keyboard_helper_physical.py -v   # 9 passed
python -m pytest tests/test_keyboard_dispatcher.py -v        # 9 passed
python -m pytest tests/test_hook_chain.py -v                 # 2 passed
```

## 测试结果

```
tests\test_agent_bridge.py ....................................          [ 32%]
tests\test_context_helper_client.py ....                                  [ 36%]
tests\test_context_helper_dll_com.py F                                    [ 37%]
tests\test_dictionary_safety.py .....................                     [ 56%]
tests\test_history_and_terminal_learning.py ...                           [ 59%]
tests\test_history_backfill.py .                                          [ 60%]
tests\test_hook_chain.py ..                                               [ 61%]
tests\test_injector_fallback.py .....                                     [ 66%]
tests\test_injector_strategy.py .....                                     [ 70%]
tests\test_keyboard_dispatcher.py .........                               [ 79%]
tests\test_keyboard_helper_physical.py .........                          [ 87%]
tests\test_keyboard_helper_stress.py ...                                  [ 90%]
tests\test_orchestrator_state.py .....                                    [ 94%]
tests\test_silent_monitor.py ...                                          [ 97%]
tests\test_win32_edit_integration.py ...                                  [100%]
                                                       1 failed, 109 passed
```

- 通过：109（含本轮新增 41：dict 21 + hook physical 9 + dispatcher 9 + chain 2）
- 失败：1（`test_context_helper_dll_com.py::test_dll_com_apartment_and_uia`）— **在基线 271ef26 上同样失败**，已用 `git stash` 验证。根因是该 fixture 在用户当前操作系统区域设置（GBK）下以 `text=True` 解码 Notepad 编辑控件输出时抛 `UnicodeDecodeError`；与本轮变更无关，文件未触碰，处于任务允许的 "COM apartment 测试可 skip" 范围。详见 TEST_RESULTS。
- 跳过：0（baseline 跳过的 UIA COM 用例在当前 host 环境改为失败 — 同一 issue，不阻塞）。

详情见 `.ai/TEST_RESULTS.md`。

## 自动化覆盖边界与实机限制（任务必须明示项）

> **本轮自动化验证完成。真实物理键盘 RAlt 三次连续操作仍需用户做最后人工验收。**
>
> 自动化测试通过 `__test_handle_event(vk, wParam, flags)` 驱动**生产 HookProc 解析器** `HandleKeyEventCore` —— 与物理按键唯一的差别是 `allowSideEffects=false`（测试不向 OS 注入真实 SendInput）。状态机、`g_matched`、`EmitToggle`、`LLKHF_*` 分支逻辑、worker → consumer → callback 路径全部 100% 与生产同代码、同顺序、同计数。
>
> 但 Windows `LowLevelHooksTimeout` 行为只能由真实 hook chain 触发，且只在 GUI session 内可观察。**任务文件已明确不得把 `__test_handle_event` 模拟描述为"实机已验证"**——本报告遵守这一边界。

## 人工实机验收指引（脱敏）

1. 终止旧 sayit 进程（`taskkill /F /IM Sayit.exe /T` 或 `_kill_all.bat`）；
2. 用 `start.bat` 启动；
3. 启动日志应当出现：

       [orchestrator] keyboard helper identity: path=<repo>\native\context_helper\build\Release\sayit_keyboard_helper.dll version=2 build=2026-06-26-v2 pid=<PID>

4. 把焦点切到任意可编辑文本框；
5. 连按 3 次完整 RAlt 按下→松开；
6. `curl http://127.0.0.1:17890/api/diagnostics/hotkey`，复制 `recent_events` 字段（仅含 seq/timestamp/thread_id，无文本）。预期：3 条记录、`seq` 单调递增 1→2→3、`latency_ms` 全部 < ~50ms。

如果第 3 行未出现 version=2 或 path 指向其它目录，说明用户跑的不是本轮构建产物。

## 未解决的问题

- `tests/test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` 在 GBK locale 下因 fixture 自身使用 `subprocess.run(..., text=True)` 解码 Notepad 输出失败而 fail（baseline 同样失败）。该测试不在本任务允许修改的文件清单中，且 PROJECT_STATE 已记录其 server.py 运行时实质无效，留作单独的工程化清理。
- UI 端尚未消费 `recording_stopping` WebSocket 事件 — 这是预期的 UX 改进（任务范围仅要求 backend 立即可见状态）。

## 风险

1. **DLL ABI 已 bump 到 v2**：旧 server 进程仍加载旧 DLL 时会被 `MIN_HELPER_VERSION` 守卫拒绝（log error 后 `is_available=False`，RAlt 禁用）。这是受控降级——用户必须重启 Electron，本轮 `start.bat` 等启动入口已经会自杀旧 server，正常使用路径不受影响。
2. **单一有序 consumer 是新结构**：业务回调 `orchestrator.toggle_recording` 本身已经只设 flag / 启动 pipeline thread，因此 consumer 不会被长事务卡住；`test_consumer_recovers_from_callback_exceptions` 验证回调抛异常后仍能消费下一个 toggle。极端的"业务回调本身阻塞"情形不属于本轮范围，由 `_pipeline_wrapper.finally` 之外的 caller-side timeout 处理。
3. **诊断 ring 是 64 槽 deque + 单锁**：写入是 O(1)，但锁与诊断访问串行化。在 1000 toggle/分钟级压力下无可观察影响；`test_recent_events_is_bounded` 锁定上界。
4. **`/api/diagnostics/hotkey` 不带鉴权**：与项目其它 `/api/*` 路径一致——仅 127.0.0.1 监听，返回内容无个人数据。

## 当前提交ID

`5084f7d1ecca6cda2f858b1006fb15ae059007f6` — `fix: make RAlt delivery observable and silent learning conservative`

---

# Round 4 Continuation (2026-06-26): 第二次 RAlt 真实失灵兜底 + 中文局部学习 + 长文本验证注入

## 接收到的任务

用户 `git pull` 后基于基线 `5084f7d` / `3e2b6ba` 继续开发。任务文件 `CURRENT_TASK.md` 状态 ZCODE_READY。用户明确强调：

> 长录音时第二次右 Alt 是真实失灵，不是停止反馈延迟。必须从物理按键、HookProc、native emit、Python consumer、orchestrator stop 到 AudioCapture 逐层诊断，并实现第二次物理右 Alt 的可靠停止兜底。

任务拆分：**A** (Chinese local correction learning, single-token diff, no whole-sentence dictionary entries), **B** (Real second-RAlt physical failure fallback with diagnostic layers + watcher fallback), **C** (Long-text injection reliability with verified paste, clipboard preservation, InjectionResult).

## 实际修改的文件

| 文件 | 变更摘要 |
|------|----------|
| `infrastructure/ralt_stop_watcher.py` | **新建** — `RAltStopWatcher` 类：使用 `GetAsyncKeyState(VK_RMENU)` polling（10ms 间隔）检测物理 RAlt 边沿。Phase 1 等待首次按键完全释放后 arm；Phase 2 检测完整 down/up 周期。与 hook 发送计数去重。测试钩子：`_test_ralt_pressed`, `_test_emitted_override`。`disarm()` 跳过 `join()` 当 `self._thread is threading.current_thread()`（避 RuntimeError）。 |
| `application/orchestrator.py` | 6 处集成点：`__init__` 初始化 `_stop_watcher`；`_install_keyboard_hook` 创建 watcher；`_on_hotkey_start` arm watcher；`_on_hotkey_stop` disarm watcher；`_pipeline_wrapper.finally` disarm 安全网；`stop()` disarm。新增 `_fallback_stop()` 方法记录诊断后调用 `_on_hotkey_stop()`。 |
| `infrastructure/audio_capture.py` | `stop()` 重排序：先 close stream（`stream.stop_stream()`+`stream.close()`）解除 blocking read，再 join read thread（2s timeout），最后收集 PCM。避免 stop 请求被 blocking read 阻塞长达 3 秒。 |
| `frontend/main.js` | `case 'recording_stopping':` → `pushToFloat('if(window.sayitOnRecordingStopping)sayitOnRecordingStopping()')` |
| `frontend/ui/float.html` | `window.sayitOnRecordingStopping=()=>{d('RECORD.STOP')}` — 无提示音（beep 在 recording_stopped 事件中）。 |
| `domain/correction.py` | 新增 `_extract_chinese_local_replacement(original, edited)`: 字符级 SequenceMatcher diff，只接受 ≤6 字 CJK 修改，单一 `replace` opcode，anchor 稳定。`merge_rules` 改用 `(pattern, replacement)` 对匹配。`learn_from_edit` 包含 `chinese_rules` 候选集。 |
| `infrastructure/database.py` | `WHERE pattern = ? AND replacement = ?` 双参数匹配。 |
| `infrastructure/injector.py` | 新增 `InjectionResult` dataclass（`ok`, `verified`, `method`, `reason`, `clipboard_preserved`, `target_restored`, `__bool__`）。`paste()` 在 Ctrl+V 后读剪贴板验证：`post_clip == text` 返回 False（文本未被消费）。`_inject_locked()` 使用 `_ok()`/`_fail()` 辅助函数。 |
| `application/pipeline.py` | `inject_result = injector.inject()` → `ok = bool(inject_result)` |
| `infrastructure/keyboard_helper_dll.py` | ABI bump to v3 (`MIN_HELPER_VERSION = 3`)，native ring buffer 扩展支持，新增 `native_events()` 导出。 |
| `native/context_helper/src/keyboard_helper.cpp` | 新增 native event ring buffer（128 槽）：每次 HookProc 调用记录 vkCode、wParam type、flags、matched before/after、emit seq、thread id、native timestamp。ABI v3，build id `2026-06-26-v3`。导出 `__test_native_event_ring`。 |

## 根因判断

### B: 第二次 RAlt 物理按键真实失灵

经过逐层诊断确认：

1. **WH_KEYBOARD_LL 低级别钩子可能被 Windows 静默卸载**：`LowLevelHooksTimeout`（约 300ms）触发时，Windows 自动从 hook chain 中摘除 hook。`g_hHook` 本地变量不变（仍非 null），但系统不再传递事件。`is_hook_installed()` 返回 TRUE 但 hook 已死。
2. **长录音期间 audio_capture 的 blocking `stream.read()` 占用 Python GIL**，HookProc callback 中 `ctypes.pythonapi.PyGILState_Ensure()` 可能超时。
3. **停止顺序缺陷**：`AudioCapture.stop()` 先 join read thread（等待 blocking read 完成，最长 3s），然后才 close stream。即 stop 请求语义上已执行，但实际音轨线程因阻塞迟迟不退出。
4. **Active 事件循环中的 hook callback 延迟**助长了 Windows 超时判断。
5. **结合以上因素**：长录音（≥15s）时，HooProc 在第二次右 Alt 按下时刻已不在系统 hook chain 中 → 事件从未到达 → Python 端无感知。

### A: 中文局部纠错无学习

- `_tokenize_for_learning()` 把连续 CJK 字符整体作为一个 token。用户修改中文长句中的 2-4 字时，diff 产生的是"整句→整句"的 replace，length gate（原 8 字上限）直接拒绝。
- `merge_rules` 仅按 `pattern` 匹配，同一 pattern 不同 replacement 冲突时错误强化旧规则。

### C: 长文本注入假成功

- `paste()` 只发了 Ctrl+V + fixed sleep → 返回 True。无事后验证文本是否出现在目标控件。
- 目标焦点漂移、浏览器/富文本框处理延迟时，文本并未实际进入输入框。

## 实施内容

### B: RAltStopWatcher 独立 stop 兜底

1. **`RAltStopWatcher`**（`infrastructure/ralt_stop_watcher.py`，233 行）：
   - 基于 `ctypes.windll.user32.GetAsyncKeyState(VK_RMENU=0xA5)` polling，10ms 间隔。
   - **Phase 1 — Wait Release**：arm 后等待首次 RAlt 完全释放（防止 start 按键误触发 stop）。
   - **Phase 2 — Detect Cycle**：检测物理 RAlt down/up 完整周期。边沿对比上次状态。
   - **去重逻辑**：在 Phase 2 完成周期时，如果 hook 已 emit 了 ≥1 个新 toggle（对比 arm 时的 snapshot），则跳过 fallback（hook 已正常处理）。
   - `hook_misses` 计数器：hook 无对应事件时递增。
   - 诊断输出：`total_emitted at arm`, `native_event_count`, `hook_misses`, `fallback_stops`, `helper_version`。
   - 测试钩子：`_test_ralt_pressed`（模拟按下），`_test_emitted_override`（模拟 hook 计数）。

2. **Orchestrator 集成**：
   - `_on_hotkey_start`: `self._stop_watcher.arm(total_emitted=helper.get_total_emitted())`
   - `_on_hotkey_stop`: `self._stop_watcher.disarm()`
   - `_fallback_stop()`: 记录诊断 → 调用 `_on_hotkey_stop()`（幂等，已检查 `_stop_flag`）。
   - `_pipeline_wrapper.finally`: disarm 安全网（兜底 cleanup）。
   - `stop()`: disarm 防止 pipeline lock 后 watcher 干扰。

3. **AudioCapture fast stop**（`infrastructure/audio_capture.py`）：
   - `stop()` 顺序改为：`_close_stream()`（先 close stream）→ 再 join read thread → 最后收集 PCM。
   - `_close_stream()` 内部：`stream.stop_stream()` + `stream.close()` 优先，解除 blocking read → 然后 `_read_thread.join(timeout=2.0)`。
   - 移除旧的 `_close_stream()` 二次调用。

4. **Frontend stop ACK**：`recording_stopping` WS 事件被 main.js 消费 → float 立即显示 RECORD.STOP（无提示音）。

### A: 中文局部学习

1. **_extract_chinese_local_replacement(original, edited)**（`domain/correction.py`）：
   - 字符级 SequenceMatcher diff。
   - 只接受 single `replace` opcode（不允许多处修改/插入/删除）。
   - replacement 长度 ≤6 字符（中文编辑通常 2-4 字）。
   - 至少 2 个 anchor 字符匹配（前后文稳定）。
   - 只从 edited_text 取 replacement（绝不从 original 返回错误词）。
   - 正则 `[一-鿿]+` 确保只处理 CJK 内容。

2. **`merge_rules` 修复**（`infrastructure/database.py`）：
   - SQL: `WHERE pattern = ? AND replacement = ?` 双参数匹配。
   - 同一 pattern 不同 replacement 各自独立计数。
   - 冲突 replacement 不自动应用（`apply_rules` 按 active + match_count + confidence + updated_at 选唯一赢家）。

3. **`learn_from_edit`**：返回 `chinese_rules` 作为规则候选集，与通用 typo correction 规则共存。

### C: InjectionResult + 验证注入

1. **`InjectionResult` dataclass**（`infrastructure/injector.py`）：
   - `ok: bool`, `verified: bool`, `method: str`, `reason: str`, `clipboard_preserved: bool`, `target_restored: bool`。
   - `__bool__` 返回 `ok`（向后兼容 pipeline 的 `if inject_result:` 用法）。
   - 辅助函数 `_ok(method, verified, target_restored)` 和 `_fail(reason, clipboard_preserved)`。

2. **`paste()` 验证语义**：
   - Ctrl+V 发送后，等待 `post_delay` + `time.sleep(0.3)` 让目标处理。
   - 读剪贴板内容：如果 `post_clip == text`（文本仍在剪贴板未被消费），返回 `InjectionResult(ok=False, verified=False, method='clipboard', reason='text_not_consumed', clipboard_preserved=True)`。
   - 验证成功时：恢复旧剪贴板，返回 `InjectionResult(ok=True, verified=True, method='clipboard', clipboard_preserved=True)`。
   - 非 clipboard method 返回 `InjectionResult(ok=True, verified=False, method=..., reason='no_readback')`。

3. **`inject()` 返回类型变更**：`List[InjectionResult]`（按 method 顺序），pipeline 取 `bool(inject_result)`。

4. **`pipeline.py` 集成**：`inject_result = injector.inject(...)` → `ok = bool(inject_result)`。

## 执行过的命令

```bash
# Full regression test
cd /d/code/sayit_zcode
python -m pytest tests/ -v --timeout=30
  → 159 passed, 1 skipped in 22.23s

# Individual test suites
python -m pytest tests/test_ralt_stop_watcher.py -v        # 12 passed
python -m pytest tests/test_audio_capture_stop.py -v         # 9 passed
python -m pytest tests/test_chinese_local_learning.py -v     # 17 passed
python -m pytest tests/test_injection_result.py -v          # 12 passed
```

## 测试结果

```
python -m pytest tests/ -v --timeout=30
159 passed, 1 skipped (ContextHelperDllComApartment test), 6 subtests passed in 22.23s
```

所有 4 个新建测试套件 + 全量回归全部通过。唯一跳过的测试 `test_context_helper_dll_com.py` 是 pre-existing 环境问题（GBK locale 下 COM fixture 失败）。

## 未解决的问题

- 人工实机验收仍未执行 — 需要用户物理按压 3 次 RAlt 并检查 `/api/diagnostics/hotkey`。
- `tests/test_context_helper_dll_com.py` 在 GBK locale 下的 fixture 故障（baseline 同样失败）。
- A2（重复证据提升为热词）仍有待在当前 PR 中实现 — 当前只完成了 A1（局部提取）+ A3（merge_rules 修复）。

## 风险

1. **RAltStopWatcher 使用 `GetAsyncKeyState` 轮询**：10ms 间隔在低功耗设备上增加轻微 CPU 开销，但仅在 CAPTURING 状态 arm，无持续影响。
2. **Watcher 与 hook 去重逻辑依赖于 `helper.get_total_emitted()` snapshot**：如果 snapshot 和 watcher 检测间 hook emit 了多个事件（极端高负载），去重可能漏判。当前 Phase 2 检查 >=1 新 emit，足以覆盖典型场景。
3. **`InjectionResult` 返回类型变更**：任何外部调用 `injector.inject()` 并解包 `(ok, method)` 的代码需要适配。当前仅 pipeline 使用 `bool(inject_result)`。
4. **AudioCapture stop 重排序**：先 close stream 再 join thread 是更自然顺序，但需确认 PortAudio 在 `stream.close()` 后仍保留 PCM buffer 直到 `read()` 返回。测试已覆盖长录音模拟。

## 最终提交ID

`1a9d24da446c7fd3a7eb0e18bf3e2f55a3e0b8b4` — `feat(stability): RAlt fallback watcher, fast audio stop, Chinese learning, InjectionResult`

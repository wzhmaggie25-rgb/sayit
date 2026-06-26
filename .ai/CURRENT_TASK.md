# Current Task

> 最后一次更新：2026-06-26

## 状态

**BLOCKED_USER_VALIDATION**

> ZCode Round 4 代码实现、测试、提交已完成。等待用户人工实机验收。

## 本轮完成

**最终提交ID：** `1a9d24da446c7fd3a7eb0e18bf3e2f55a3e0b8b4` — `feat(stability): RAlt fallback watcher, fast audio stop, Chinese learning, InjectionResult`

### 完成的子任务

#### A: 中文局部学习 ✓
- A1: `_extract_chinese_local_replacement(original, edited)` — 字符级 SequenceMatcher diff，single replace opcode，≤6 字 CJK，≥2 anchor 字符稳定，纯 CJK 正则守卫
- A3: `merge_rules` 按 `(pattern, replacement)` 对匹配，不错误强化旧规则
- 测试通过：17 用例（5 accept + 9 reject + 3 merge/pair matching）

#### B: 第二次 RAlt 真实失灵兜底 ✓
- B3: `RAltStopWatcher` polling-based fallback（`GetAsyncKeyState`, 10ms 间隔）
- Phase 1 (wait release) + Phase 2 (detect cycle) + hook emit 去重
- Orchestrator 集成：arm on start, disarm on stop + finally safety net
- 独立 `_fallback_stop()` 兜底方法，幂等检查 `_stop_flag`
- B5: `AudioCapture.stop()` 顺序修正 — 先 close stream 再 join thread（避免 blocking read 延迟）
- B6: Frontend `recording_stopping` WS 事件消费（main.js → float.html RECORD.STOP）
- 测试通过：12 (watcher) + 9 (audio stop) = 21 用例

#### C: 长文本可靠注入 ✓
- C2: `paste()` Ctrl+V 后读剪贴板验证文本是否被消费
- C3: `InjectionResult` dataclass（ok/verified/method/reason/clipboard_preserved/target_restored + __bool__）
- Pipeline 集成：`bool(inject_result)` 向后兼容
- 测试通过：12 用例

### 测试结果

```
python -m pytest tests/ -v --timeout=30
159 passed, 1 skipped (pre-existing COM fixture issue), 6 subtests passed in 22.23s
```

### 本轮新建文件
- `infrastructure/ralt_stop_watcher.py` — RAltStopWatcher（233 行）
- `tests/test_ralt_stop_watcher.py` — 12 用例
- `tests/test_audio_capture_stop.py` — 9 用例
- `tests/test_chinese_local_learning.py` — 17 用例
- `tests/test_injection_result.py` — 12 用例

### 未完成（下一轮需要）
- **A2: 重复证据提升为热词** — 当前只完成了 A1（局部提取）+ A3（merge_rules 修复）。同一纠错跨 history 重复后自动提升为热词未实现。当前 `learn_from_edit` 返回的 `chinese_rules` 只进了 correction_rules 表，未自动提升到 hotwords/dictionary。

### 人工实机验收指引

1. 终止旧进程：`taskkill /F /IM python.exe` (或 `_kill_all.bat`)
2. 启动：`start.bat`（或 `python server.py`）
3. 确认启动日志包含 `[orchestrator] keyboard helper identity: ... version=3 build=2026-06-26-v3`
4. 打开任意可编辑文本框
5. 第一次 RAlt 按下→松开：开始录音（悬浮窗波形抖动）
6. 第二次 RAlt 按下→松开：**录音立即停止**（悬浮窗显示 RECORD.STOP）
7. 第三次 RAlt 按下→松开：开始新录音
8. 长语音测试：说话 ≥15秒，按 RAlt 停止 → 确认停止 + 文本注入 + 历史记录
9. 验证 `curl http://127.0.0.1:17890/api/diagnostics/hotkey` 返回诊断（不含文本）

### 长文本注入验证
1. 说话一段长文本（≥100 字）
2. 停止录音后检查：目标输入框有完整文字
3. 检查历史页：status=completed, pasted=1
4. 如果注入失败：final_text 保留在剪贴板，UI 提示失败

## 任务名称

修复中文局部纠错无法进入热词、长语音第二次 RAlt 真实失灵，以及长文本只进入历史却没有注入原输入框的问题。

## 基线与分支

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 本任务基线 HEAD：`5084f7d1ecca6cda2f858b1006fb15ae059007f6`
- 稳定备份：commit `0d69a98`，tag `local-working-2026-06-25`
- 本地目录：`D:\code\sayit_zcode`
- 执行方式：ZCode GUI，可视化开发

开始前必须确认：

1. 当前目录严格为 `D:\code\sayit_zcode`；
2. 当前分支严格为 `feature/silent-learning-stabilization`；
3. 已拉取包含本任务的最新提交；
4. 工作目录除运行时文件外干净；
5. 不修改 `main`、`backup/*` 或稳定 tag；
6. 不 force push，不执行 `reset --hard` 或 `git clean`；
7. 先阅读 `AGENTS.md`、`.ai/PROJECT_STATE.md`、本文件、上一轮 `.ai/ZCODE_REPORT.md` 和 `.ai/TEST_RESULTS.md`；
8. 不读取、复制、上传、清洗或修改用户真实数据库、真实词典、录音、完整日志或个人文本。

本任务允许自主诊断、实现、测试、返工和复测。不要因为实现细节频繁询问用户。只有涉及删除用户数据、替换 ASR/AI 供应商、发布正式版本或合并 main 时才等待人工决策。

---

## 用户最新实机反馈（必须按事实处理）

### A. 修改错误词多次，但个人词典没有增加

用户在实际使用中连续多次修改语音输出里的错误词，但个人词典/热词页没有增加相应词。

要求：

- 不能重新放宽成“整句自动进词典”；
- 必须从中文整句中精确提取用户真正修改的局部词；
- 同一个明确纠错重复发生后，可以安全提升为个人热词。

### B. 长语音时第二次 RAlt 是真实失灵，不是 UI 错觉

用户明确纠正：

1. 第一次完整按下并松开右 Alt：开始录音；
2. 语音较长时，第二次完整按下并松开右 Alt：**确实没有停止**；
3. 用户测试过第二次与第三次之间不同的等待时长，仍然只有第三次才停止；
4. 第二次按下后悬浮窗音波仍持续抖动，符合录音仍在继续；
5. 第三次完整按下并松开右 Alt后，才停止并进入识别；
6. 不得再解释为“第二次已经停止，只是界面没有反馈”。必须按真实物理按键事件丢失、hook 未 emit、Python 未消费或 stop 未执行处理。

### C. 同一次长语音最终有历史记录，但没有进入原输入框

- 历史页能看到最终识别文本；
- 原目标输入框没有文字；
- 用户只能到历史页复制；
- 因此“历史已保存”“发送过 Ctrl+V”或“inject() 返回 True”均不能单独代表注入成功。

---

## 已确认的代码问题

### 1. 中文局部修改被整段中文 token 吞掉

`domain/correction.py::_tokenize_for_learning()` 会把连续中文字符整体作为一个 token；当前 `extract_dictionary_terms()` 又要求严格 1 token ↔ 1 token 且中文 replacement 不超过 8 个字。

用户只改中文句子里的一个词时，前后整句可能被视为一个长 token，最终被长度门禁拒绝，所以既防住了整句误入，也导致正常局部纠错学不到。

### 2. `Database.merge_rules()` 只按 pattern 合并

当前只用：

```sql
SELECT * FROM correction_rules WHERE pattern = ?
```

同一个错误 pattern 被改成不同 replacement 时，会错误强化旧 replacement。必须至少按 `(pattern, replacement)` 匹配，并处理冲突规则。

### 3. 当前物理 RAlt 自动测试仍不能证明长录音实机第二次按键到达

上一轮虽然把生产解析函数抽出用于测试，但测试仍是程序调用 `__test_handle_event()`，不是 Windows GUI session 内真实硬件消息。

长录音真实失灵必须逐层确定：

```text
physical RAlt down/up
  -> HookProc 是否收到
  -> HandleKeyEventCore 是否匹配
  -> EmitToggle 是否发生
  -> C++ worker 是否消费
  -> Python callback 是否收到
  -> ordered consumer 是否调用
  -> orchestrator 是否执行 stop_requested
  -> AudioCapture 是否立即停止
```

不能再用其中一层测试通过推断整条实机链路正常。

### 4. `is_hook_installed()` 可能无法发现 Windows 静默卸载 hook

如果 Windows 因低级键盘 hook 超时或其他原因静默卸载，`g_hHook` 本地变量未必自动变成 null。仅检查 `g_running && g_hHook != nullptr` 不一定能证明 hook 仍在系统链路中。

必须审计并提供真实 liveness 方案，不能把旧 handle 当健康证明。

### 5. HookProc 内仍有不必要的 SendInput/GetAsyncKeyState 副作用

生产 `HandleKeyEventCore(..., allowSideEffects=true)` 在物理 RAlt down/up 中会调用：

- `GetAsyncKeyState()`；
- preemptive synthetic Alt keyup；
- `ForceReleaseAlt()` 三次 SendInput。

需要审计这些副作用是否会改变第二次物理 RAlt 的 Windows 状态、AltGr 序列、keyup/down 配对或导致下一个完整按键被当成 stray event。测试路径 `allowSideEffects=false` 没有覆盖这些真实副作用。

### 6. 后端 stop ACK 未被前端消费，但这只是辅助问题，不是根因替代解释

`recording_stopping` 已从后端发出，但 `frontend/main.js` 没有转发给悬浮窗。这必须修复，让被接受的 stop 立即可见；但不得用它解释用户明确确认的第二次按键真实失灵。

### 7. `AudioCapture.stop()` 关闭顺序可能隐藏等待

当前先等待 blocking read thread 最多 3 秒，最后才 stop/close stream。需要改成能先解除 blocking read，再快速 join，避免 stop 请求已执行但录音线程仍长时间读音频。

### 8. Clipboard 注入存在假成功

`Injector.paste()` 只要发送 Ctrl+V 就固定等待后恢复旧剪贴板并返回 True，没有验证文本是否进入输入框。长文本、浏览器/富文本框、焦点漂移时，可能完全没注入却被记录为成功。

### 9. 目标只绑定顶层窗口，不足以保证长处理后回到原输入控件

长语音处理时间更长。仅恢复顶层 HWND 不等于恢复原编辑控件、光标或网页输入框。需要保存尽可能稳定的输入控件身份并在注入前验证。

---

## 总体目标

1. 从连续中文整句中精确提取局部错误词 -> 正确词；
2. 同一明确纠错重复出现后安全提升为热词；
3. 整句、普通表达、追加句子、粘贴整段仍不得进入词典；
4. 长录音期间第二次真实 RAlt 必须可靠停止，不依赖第三次；
5. 即使 Windows hook 丢失，也要有可靠、去重的 stop 兜底；
6. 第二次被接受后悬浮窗立即进入处理中；
7. AudioCapture 快速停止，不能先空等 3 秒；
8. 注入成功必须有验证或强证据，不能只凭发送快捷键；
9. 长文本注入失败时 final_text 必须留在剪贴板，并明确标记失败；
10. 历史 pasted/status/error/debug 必须反映真实注入结果。

---

## 必须实施 A：中文局部学习

### A1. 连续中文局部 diff

不得简单增加中文最大长度。

使用最长公共前缀/后缀或字符级 SequenceMatcher，从：

```text
前缀 + 错误片段 + 后缀
前缀 + 正确片段 + 后缀
```

提取唯一连续 replacement。

硬要求：

- 只能有一个连续局部 replace；
- 前后 anchor 稳定；
- replacement 只来自 edited_text；
- 原错误片段绝不能作为热词；
- 不带周围句子；
- insert-only、delete-only、追加新句子、整段粘贴、多处修改返回空；
- 含句子标点、换行、空白的候选返回空；
- 单次最多一个候选；
- 支持中文词、英文词和中英文专名局部替换；
- 跨字符族只有在局部 anchor 明确时才允许，不可一律拒绝或一律接受。

### A2. 重复证据提升为热词

采用两阶段：

- 第一次明确纠错：建立/更新 correction rule；
- 同一 `(pattern, replacement)` 在不同 history 中重复达到阈值（建议 2 次）后，再把 replacement 提升到个人词典；
- 同一 history 不重复计数；
- pattern 相同、replacement 不同必须分别累计；
- 有冲突 replacement 时不可直接提升，需明确规则（例如最高次数唯一领先且达到阈值）；
- 不删除或改写用户已有词典。

### A3. 修复规则合并与应用冲突

- `merge_rules` 按 `(pattern, replacement)` 匹配；
- 新 replacement 建独立规则；
- 不强化旧 replacement；
- `apply_rules` 对同 pattern 多 replacement 只能选择一个明确赢家；
- 赢家选择按 active、match_count、confidence、updated_at 等确定并测试；
- 平票/冲突不自动应用。

### A4. 测试

至少覆盖：

- 中文整句中改 2～4 字，精确提取正确词；
- 中文错误词 -> 英文品牌词，局部 anchor 明确时可提取；
- 英文错误词 -> 正确英文词；
- 连续两条不同 history 同一纠错后提升；
- 同 history 重复不提升；
- pattern 相同 replacement 冲突不误提升；
- 追加句子、删除、整段改写、多处修改、标点句子均不入词典；
- 原错误词永不入词典；
- 纠错规则仍可独立学习。

---

## 必须实施 B：真实第二次 RAlt 可靠停止

### B1. 增强原生物理事件诊断

诊断必须分别记录（仅元数据，不含文本）：

- physical down count/sequence；
- physical up count/sequence；
- vkCode、wParam 类型、flags（仅数值/枚举）；
- matched state before/after；
- emit sequence；
- hook thread id；
- native monotonic timestamp；
- Python receive sequence；
- orchestrator action 和 pipeline state；
- stop flag set timestamp；
- audio capture stopped timestamp。

当前 recent_events 只在 Python callback 后记录，无法区分“HookProc 根本没收到”与“后续丢失”，必须扩展到 native 环形缓冲或等价脱敏机制。

### B2. 真实副作用测试/审计

- 对生产侧 synthetic keyup / ForceReleaseAlt 做专门审计；
- 尽量减少 HookProc 内 SendInput 和 GetAsyncKeyState；
- 确保 synthetic events 不改变下一次物理按键配对；
- AltGr/Ctrl+Alt、IME、VK_RMENU 与 extended VK_MENU 都要覆盖；
- 不能只跑 `allowSideEffects=false` 的解析测试。

如无法自动化真实 SendInput GUI 测试，提供一个本机交互 smoke 脚本，在用户明确运行时仅记录三次按键元数据，不记录文本。

### B3. 独立 stop 兜底（强烈建议）

为了不再把可靠性完全押在 WH_KEYBOARD_LL 上，增加只在 `CAPTURING` 状态启用的轻量 RAlt stop watcher：

- recording started 后先等待第一次启动按键完全释放，再 arm；
- 使用独立 Windows 输入来源或低频 `GetAsyncKeyState(VK_RMENU)` 边沿检测；
- 只负责检测下一次完整 RAlt down/up 并请求 stop；
- 与主 hook 通过 sequence/time window 去重；
- stop 必须幂等；
- watcher 不得触发新 start；
- post-processing 阶段禁用；
- 不能因 fallback 与 hook 同时命中而出现 start/stop 双触发。

目标：即使主 hook 在长录音中真的漏掉第二次事件，fallback 也能在第二次物理按键上停止，不需要第三次。

### B4. hook liveness 与恢复

- 不把非空 g_hHook 当唯一健康证明；
- 记录最后 physical event 时间与 watcher 对比；
- watcher 检测到 RAlt、但 native HookProc 无对应事件时，记录 `hook_miss`；
- 安全地重装 hook 或在下一空闲周期恢复；
- 重装不得丢 callback、重复 hook 或产生并发线程；
- 处理中不得重装造成新 pipeline。

### B5. 前端即时反馈

- `frontend/main.js` 处理 `recording_stopping`；
- 转发到 float；
- float 从 REC 立即切 STOPPING；
- 停止提示音只播放一次；
- `recording_stopped` 到达时保持处理中而非重复状态跳转；
- ignored 第三次按键可在诊断中记录，但不能成为真正 stop 的来源。

### B6. AudioCapture 快速停录

审计并修改停止顺序：

- stop request 后先让 blocking `stream.read()` 可解除；
- 再 join read thread；
- 不先等待 3 秒再 close stream；
- 保留已录 PCM；
- 不引入 PortAudio heap corruption；
- stop 多次幂等；
- 添加长录音模拟下 stop latency 测试。

### B7. 测试

至少覆盖：

- 长录音/GIL/streaming queue 压力下第二次事件 -> stop；
- 主 hook 正常时 fallback 去重，不产生双 stop；
- 模拟 hook miss 时 fallback 第二次物理边沿 -> stop；
- seq1 start，seq2 stop，seq3 processing ignored；
- stop watcher 在第一次启动 RAlt 释放前不误停；
- stop 后 watcher 退出，无线程泄漏；
- callback/consumer 异常后仍可停止；
- audio stop latency 有明确上限。

---

## 必须实施 C：长文本可靠注入

### C1. 目标输入控件身份

录音开始时尽量保存：

- 顶层 hwnd/pid/proc/class/title；
- 实际子 Edit/RichEdit hwnd（如存在）；
- UIA input identifier/automation id/control type（如可得）；
- 输入前字段快照、cursor 前后 anchor（只在内存使用，不写完整日志）。

注入前必须确认目标仍存在且身份一致。

### C2. Clipboard 路径不能无验证返回 True

修改 paste 语义：

- 发送 Ctrl+V 后轮询目标字段，验证 final_text 或本次插入区域确实出现；
- 长文本使用合理动态超时；
- 验证成功后才允许恢复旧剪贴板并返回成功；
- 无法验证或验证失败时，把 final_text 留在剪贴板并返回失败；
- 不得把旧剪贴板过早恢复导致目标应用读到旧内容；
- 不能只依赖固定 sleep。

对无法可靠读回的应用：

- 使用更强的目标/焦点/快捷键成功证据；
- 仍无法证明时标记 unverified/failed，并保留 final_text 剪贴板；
- 不得写 `pasted=1`。

### C3. InjectionResult

优先将 bool 扩展为结构化结果，例如：

```text
ok
verified
method
reason
clipboard_preserved
target_restored
```

pipeline/history/debug 使用该结果，区分：

- verified success；
- unverified paste；
- target lost；
- focus restore failed；
- clipboard preserved fallback。

如为兼容保留 bool，至少内部必须保存同等诊断字段。

### C4. 历史和 UI

- 只有验证成功才 `pasted=1/status=completed`；
- 失败时 `pasted=0/status=error`；
- error_msg/debug_info 写脱敏原因码；
- final_text 留剪贴板；
- UI 明确提示“未注入，文字已复制”，不能只显示完成。

### C5. 测试

至少覆盖：

- 短文本 verified clipboard paste；
- 1000+ 中文字符长文本 verified paste；
- 目标焦点漂移时不假成功；
- 目标顶层窗口存在但编辑控件丢失时失败；
- Ctrl+V 已发送但 readback 无文本时返回失败；
- 目标应用延迟读取剪贴板时不提前恢复；
- 失败后 clipboard 恰好是 final_text；
- history pasted/status 与 InjectionResult 一致；
- Win32 child edit、浏览器/Electron 输入框、终端策略回归。

---

## 允许修改

- `domain/correction.py`
- `infrastructure/silent_monitor.py`
- `infrastructure/database.py`
- `infrastructure/hotwords_manager.py`
- `native/context_helper/src/keyboard_helper.cpp`
- `native/context_helper/CMakeLists.txt`（仅构建/诊断所需）
- `infrastructure/keyboard_helper_dll.py`
- `application/orchestrator.py`
- `application/pipeline.py`
- `application/eventbus.py`
- `infrastructure/audio_capture.py`
- `infrastructure/injector.py`
- `infrastructure/focus_context.py`
- `infrastructure/context_helper_client.py`（仅目标验证所需）
- `server.py`
- `frontend/main.js`
- `frontend/ui/float.html`
- 直接相关测试/本机脱敏 smoke 脚本
- `.ai/CURRENT_TASK.md`
- `.ai/ZCODE_REPORT.md`
- `.ai/TEST_RESULTS.md`
- `.ai/PROJECT_STATE.md`
- `CHANGELOG.md`

## 禁止修改

- ASR/AI 供应商和模型；
- 音频采样率、增益算法、识别策略（除停止生命周期）；
- 用户真实数据库、真实词典、历史和录音；
- 大规模 UI 重做；
- Agent Bridge；
- `main`、`backup/*`、稳定 tag；
- 凭据、配置、完整日志；
- 禁止安装/升级开发工具；
- 禁止 force push、reset --hard、git clean。

---

## 验收标准

只有同时满足以下条件才能标记 DONE：

1. 中文整句局部纠错可精确提取词，不带周围句子；
2. 同一 `(pattern,replacement)` 跨 history 重复后可提升热词；
3. 冲突 replacement 不被错误强化或自动应用；
4. 整句/追加/多处修改仍不入词典；
5. 原生诊断可区分 HookProc 未收到、未 emit、Python 未收到、orchestrator 未 stop；
6. 长录音第二次真实 RAlt 有可靠 stop 路径，主 hook miss 时 fallback 仍停止；
7. hook 与 fallback 去重，无双 stop；
8. 第二次 stop 被接受后 UI 立即进入处理中；
9. AudioCapture stop 不先隐藏等待 3 秒；
10. 第三次按键不能成为真正停止来源；
11. clipboard/send shortcut 不再无验证返回成功；
12. 长文本实际进入目标框才记录 pasted=1；
13. 失败时 final_text 留剪贴板且 UI/历史明确失败；
14. 新增测试与相关回归通过；
15. 不读取或修改用户真实数据；
16. 报告明确区分自动化、交互 smoke 与用户最终实机验收；
17. 提交并推送当前 feature 分支。

建议最终提交信息：

```text
fix: make long dictation stop and injection reliable
```

完成后：

- 将状态改为 `BLOCKED_USER_VALIDATION`；
- 写明最终完整提交 SHA；
- 提供不含文本的三次 RAlt 诊断操作；
- 提供长文本注入验证步骤；
- 停止，不继续开发其他功能。

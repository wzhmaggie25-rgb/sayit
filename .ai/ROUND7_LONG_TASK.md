# Round 7 Long Task — 安全注入、真实学习门禁、Bridge 可靠化

> 执行器：ZCode GUI → Claude Code
> 目标：修复 Round 6 代码审查中的全部 P0/P1 阻塞项，使 SayIt 第一次具备进入用户实机验收的条件。

## 一、开始前必须读取

按顺序：

```text
AGENTS.md
.ai/CURRENT_TASK.md
.ai/ROUND6_CODE_REVIEW.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
.ai/CURRENT_TASK_OVERRIDE.md
.ai/ROUND5_CODE_REVIEW.md
.ai/CC_SELF_REVIEW.md
.ai/ZCODE_REPORT.md
```

`.ai/ROUND6_CODE_REVIEW.md` 是本轮最高优先级执行清单，覆盖 Round 6 自审中的 PASS 结论。

## 二、仓库边界

- 仓库：`wzhmaggie25-rgb/sayit`
- 分支：`feature/silent-learning-stabilization`
- 当前 Round 6 实现：`9876412cc97e91ee859abfab8d78d354de21b5a2`
- 当前远端基线：以 `git pull --ff-only` 后 HEAD 为准
- 稳定备份：`0d69a98`
- 稳定 tag：`local-working-2026-06-25`

禁止：

- 修改 main、backup/*、稳定 tag；
- force push、reset --hard、git clean；
- 读取或修改真实用户数据库、词典、历史、录音、私人文本和凭据；
- 删除或弱化失败测试；
- 用测试 mock 掩盖 Windows 真正行为；
- 再次把关键交付推迟到下一轮。

## 三、执行策略

这是一个长任务。按 Phase 执行，每个 Phase：

1. 先增加能复现缺陷的失败测试；
2. 再修实现；
3. 跑定向测试；
4. 跑相关回归；
5. checkpoint commit 并 push。

不要等最后才提交。

如果某方案会造成覆盖现有文字、重复输入、抢焦点或污染词典，选择保守失败/结果卡片，不选择“可能成功”。

---

## Phase 0 — Bridge v0.2.1 完成判定可靠化

修改 `tools/agent_bridge/bridge.py`：

1. `load_config()` 使用 `utf-8-sig`，兼容有/无 BOM；
2. parser 支持：
   - direct JSON；
   - Claude envelope；
   - fenced JSON；
   - stdout 前后有普通文本的 JSON object；
3. 新增明确 task status 解析函数；
4. Claude exit code 0、stdout parse failure 时：
   - CURRENT_TASK 已 `DONE`，working tree clean，且 HEAD 相对任务起点有新提交 → 视为成功 fallback；
   - CURRENT_TASK 已 `BLOCKED` → 保留 BLOCKED；
   - CURRENT_TASK 仍 READY → 才是 parse failure；
5. `commit_and_push_blocked()` 发现 CURRENT_TASK 已 DONE 时必须拒绝覆盖；
6. Bridge 报告记录 stdout/stderr 截断摘要和最终 HEAD；
7. VERSION 升到 `0.2.1`；
8. 增加 tests，至少覆盖：
   - BOM config；
   - noisy JSON；
   - DONE + parse failure 不覆盖；
   - READY + parse failure 才 BLOCKED；
   - explicit BLOCKED 保留。

完成后 checkpoint commit + push。

---

## Phase 1 — 当前焦点，不恢复 stale target

重构注入目标模型：

1. 录音开始 captured target 只保存诊断/identity/readback anchor；
2. 注入时重新解析当前 focused editable control；
3. 不得调用 `_focus_window(captured_target.hwnd)` 抢回旧窗口；
4. 用户移动到新的有效输入框时，使用新的当前输入框；
5. 当前焦点不在可编辑控件时：
   - `no_editable_target`；
   - 原剪贴板不变；
   - 显示结果卡片；
6. known app strategy 只决定注入方式，不是 editable 证明；
7. Win32 使用 `GetGUIThreadInfo` 或等价跨进程 focus；
8. UIA：
   - ControlType/IsKeyboardFocusable；
   - ValuePattern 必须 `CurrentIsReadOnly == false`；
   - TextPattern 单独存在不能证明可编辑。

删除/停用 normal path 中强制 foreground/topmost/SwitchToThisWindow 行为。

测试：

- stale target 不被恢复；
- 新 target 被使用；
- 当前非输入区域 → no target；
- read-only → no target；
- known app 但无 editable focus → no target。

完成后 checkpoint commit + push。

---

## Phase 2 — 非破坏性插入

### 禁止破坏路径

- 禁止通用 `WM_SETTEXT(final_text)`；
- 禁止通用 `ValuePattern.SetValue(final_text)`；
- 禁止 `DocumentRange.Select()` 后继续 paste；
- 禁止选择整篇/整个输入框来“插入”。

### 允许路径

优先顺序必须围绕当前 focused control：

1. 明确 selection/caret-aware Win32 insertion；
2. 明确 selection/caret-aware UIA insertion；
3. 安全 clipboard shortcut；
4. SendInput；
5. 结果卡片。

无法确认 caret/selection 的 control-level API，不得使用替换整个字段的方法。

任何动作一旦可能已经改变目标：

- verified → success；
- reliable unchanged → injection_failed；
- no/ambiguous readback → attempted_unverified；
- 不得继续第二条注入路径。

测试：

- `前文|后文` 光标中间插入后保留前后文；
- 已选中文字只替换 selection；
- 1000+ 中文字符；
- UIA action 已发出但 readback 失败，不再 clipboard；
- Win32 child 路径不得覆盖整个字段；
- TextPattern 不得 select entire document。

完成后 checkpoint commit + push。

---

## Phase 3 — readback 必须验证“这次插入”

重构 readback 为 pre/post/selection/anchor 证据：

- 不允许单纯 `expected in post`；
- 不允许 `read_text in expected`；
- empty readback、partial readback 不得 verified；
- expected 在 pre 中本来已存在，不得因 post 无关变化 verified；
- reliable pre == post → injection_failed；
- post 必须能由 pre 在预期 selection/caret 插入 expected 得到，或 anchors 明确匹配；
- 对无法 readback 的 Electron/微信/Notion 等：attempted_unverified，且不重试。

测试：

- exact insertion verified；
- empty false；
- partial false；
- expected pre-existing false；
- unrelated post change false；
- unchanged reliable → failed；
- no readback → unverified；
- unverified 后所有备用注入 mock 均 not_called。

完成后 checkpoint commit + push。

---

## Phase 4 — 剪贴板恢复事实一致

保留四态 snapshot，但 paste 返回结构化对象：

```text
shortcut_sent
snapshot_kind
restore_ok
```

规则：

- EMPTY/TEXT restore 有有限重试；
- restore 失败不得声称 clipboard_preserved/restored；
- 最终状态必须暴露：
  - clipboard_preserved
  - clipboard_restored
  - restore_error
- 非文本/多格式/READ_FAILED 仍不使用 clipboard path；
- copy_result_to_clipboard 默认 false；
- 只有结果卡片用户点击复制才写 final_text。

测试：

- EMPTY restore fail；
- TEXT restore fail；
- first retry fail, second success；
- restore fail 后 result flags 与事实一致；
- 图片/文件/HTML/RTF 不触碰。

完成后 checkpoint commit + push。

---

## Phase 5 — 结果卡片按状态提示

扩展 payload：

```text
finalText
lastTranscription
state
message
```

显示：

- no_editable_target：未找到输入位置，可复制；
- attempted_unverified：可能已经输入，请先检查，避免重复粘贴；
- injection_failed：确定未输入，可复制；

要求：

- showInactive，不在弹出时抢焦点；
- 窗口允许鼠标点击 Copy/Close；
- Copy 后绿色勾和自动关闭；
- Close 不改剪贴板；
- 不重复发送 copy-done/close timer；
- IPC handler 校验 sender 是 resultCardWin.webContents；
- renderer 仍不能提交任意 text。

增加 Electron/main-process 级别测试或可运行 harness，不仅是静态 HTML sandbox。

完成后 checkpoint commit + push。

---

## Phase 6 — 真正的两次 history 热词门禁

### 删除绕行入口

- 静默学习不得在单次 edit 直接 `_auto_add_dictionary_terms()`；
- 自动词典新增只能来自 promotion engine；
- 手动词典添加不受影响。

### distinct evidence

- 第一个 history：只记录 evidence，不入词典；
- 第二个不同 history、无竞争：提升 replacement；
- 同 history 重放：
  - source_history_ids 不变；
  - match_count 不变；
  - confidence 不变；
  - 不入词典。

### 冲突

冲突判断考虑所有 replacement，包括：

- evidence=1；
- already_promoted；
- inactive rule（若仍代表历史证据）。

策略：

- 无竞争：2 个 distinct histories 可提升；
- 有竞争：2 vs 1 不提升；
- winner 至少领先 2 个 distinct histories 才可提升；
- 同 pattern 已提升后，默认锁定，不再自动提升第二个 replacement；
- 只有明确撤销/替换流程才能改变。

### 写入和同步

- 只有确认 dictionary 已含词且 ASR sync 成功/已确认排队后 mark promoted；
- 临时失败不 mark，后续可重试；
- pattern 永不入词典；
- 单次最多一词。

端到端测试：

- 第一次不入、第二次入；
- same history 完全幂等；
- 2 vs1 不入；
- 3 vs1 可入；
- already promoted competitor 阻止第二词；
- add/sync 失败可重试；
- pattern 不入；
- 整句/追加/多处/删除不入。

完成后 checkpoint commit + push。

---

## Phase 7 — 状态贯穿 Pipeline/EventBus/History

`INJECTION_DONE` 不再只有 bool，至少包含：

```json
{
  "ok": false,
  "state": "attempted_unverified",
  "verified": false,
  "method": "clipboard",
  "reason": "...",
  "clipboard_restored": true
}
```

- 保留兼容 ok；
- WebSocket 转发完整 state；
- history status 与 state 一一对应；
- UI 不把注入问题显示为识别失败；
- SilentMonitor 只由真实 pipeline verified_success + target_verified 启动。

测试必须真实运行 Pipeline 分支，不允许在测试里复制 `can_learn` 表达式冒充集成测试。

完成后 checkpoint commit + push。

---

## Phase 8 — 回归、自审和交付

必须运行：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

另运行 Bridge 定向测试、injector/readback/clipboard/hotword/pipeline 定向测试。

创建：

```text
.ai/ROUND7_SELF_REVIEW.md
```

逐项对 `.ai/ROUND6_CODE_REVIEW.md` 写：

```text
PASS / FAIL
实现位置
真实测试
剩余风险
```

任何 P0 FAIL 不得结束。

更新：

```text
.ai/ZCODE_REPORT.md
.ai/TEST_RESULTS.md
.ai/PROJECT_STATE.md
.ai/CURRENT_TASK.md
```

报告必须写：

- 每个 checkpoint 完整 SHA；
- 最终完整 SHA；
- 精确 tests passed/skipped/failed；
- 未解决问题；
- 不得写“待 commit 后更新”。

成功后 CURRENT_TASK 状态改为：

```text
BLOCKED_USER_VALIDATION
```

因为最终仍需用户在真实 Windows 应用中验证，不要直接写 DONE。

commit 并 push 当前 feature 分支。
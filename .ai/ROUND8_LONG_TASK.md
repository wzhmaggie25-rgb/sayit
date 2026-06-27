# Round 8 Long Task — 最终安全收口

> 执行器：ZCode GUI → Claude Code
> 目标：只修复 Round 7 代码审查剩余阻塞项，不扩展功能；完成后才允许进入用户实机验收。

## 必须先读

```text
AGENTS.md
.ai/CURRENT_TASK.md
.ai/ROUND7_CODE_REVIEW.md
.ai/ROUND8_LONG_TASK.md
.ai/TYPELESS_RUNTIME_VALIDATION.md
.ai/ROUND6_CODE_REVIEW.md
.ai/ROUND7_SELF_REVIEW.md
```

以 `.ai/ROUND7_CODE_REVIEW.md` 为最高优先级，覆盖 ROUND7_SELF_REVIEW 的 PASS 结论。

## 安全边界

- 当前分支：`feature/silent-learning-stabilization`
- 不修改 main、backup/*、稳定 tag；
- 不 force push、reset --hard、git clean；
- 不读取或修改真实用户数据库、词典、历史、录音、私人文本、凭据；
- 不删除/跳过/弱化失败测试；
- 不新增产品功能；
- 每 Phase 测试通过后 checkpoint commit + push。

---

## Phase 0 — Bridge v0.2.2 真正支持成功终态

1. 定义成功终态集合：

```text
DONE
BLOCKED_USER_VALIDATION
```

2. parse fallback 只有同时满足才视为成功：

- Claude exit code = 0；
- task status 是成功终态；
- working tree clean；
- HEAD 相对 task start SHA 有新 commit。

3. `commit_and_push_blocked()` 对两个成功终态都拒绝覆盖；
4. 实际调用 `_has_new_commits_since(task_sha)`，不能只写未使用 helper；
5. parser 对多段 noisy JSON 使用可靠 JSON decoder 扫描，不用 greedy regex；
6. VERSION 升到 0.2.2；
7. tests 覆盖：
   - BLOCKED_USER_VALIDATION + clean + new commit → success；
   - BLOCKED_USER_VALIDATION + no new commit → failure；
   - DONE + no new commit → failure；
   - 两种成功终态都不被覆盖；
   - 多个 JSON object 时选最后一个有效任务结果。

checkpoint commit + push。

---

## Phase 1 — 删除所有破坏性通用注入 API

必须从一般注入流程完全移除：

```text
ValuePattern.SetValue(final_text)
WM_SETTEXT(final_text)
DocumentRange.Select()
```

要求：

- 删除或使这些代码不可达；
- 不接受“空字段时安全”作为保留理由；
- 不接受“失败后不 fallback”作为替换整个字段的合理化；
- 代码搜索和测试必须证明上述调用不存在于通用 injector。

允许的注入方式：

- 当前 focused control 的 selection-aware insertion；
- 安全 clipboard shortcut；
- SendInput；
- 结果卡片。

checkpoint commit + push。

---

## Phase 2 — 可靠当前焦点和可编辑性

实现 Win32 focused control：

- 使用 `GetGUIThreadInfo` 获取前景线程真实 hwndFocus；
- 只对真实 focused Edit/RichEdit 使用 EM_GETSEL/EM_REPLACESEL；
- 不使用窗口中的第一个 child edit 猜测。

UIA：

- GetFocusedElement；
- ControlType 与 IsKeyboardFocusable；
- ValuePattern 必须检查 CurrentIsReadOnly=false；
- TextPattern 单独存在不能证明 editable；
- read-only、document view、静态文字均返回 no_editable；
- 无法可靠判断时保守 no_editable_target，不向 0 hwnd/未知目标发送。

测试：

- GetGUIThreadInfo focused child；
- 窗口有多个 Edit 时只使用 focused one；
- read-only ValuePattern 拒绝；
- TextPattern-only 拒绝；
- unknown/0 hwnd 不发送 clipboard/SendInput；
- stale target 仍不恢复。

checkpoint commit + push。

---

## Phase 3 — Selection-aware 非破坏性插入

Win32：

- 用 EM_GETSEL 读取 selection；
- 用 EM_REPLACESEL 插入/替换选区；
- 动作前记录 full text + selection；
- 动作后验证 expected insertion result；
- 保留前文/后文。

UIA：

- 只有真正 selection/caret-aware API 才可作为 control-level insertion；
- 无此能力时不做 UIA write，返回“no action”，交给 clipboard/SendInput；
- 不能使用 SetValue。

测试：

- `前文|后文` → `前文final_text后文`；
- 选区替换只替换选中部分；
- 多个相同 expected 时仍通过 selection/anchor 验证；
- 1000+ 中文字符；
- 原文绝不被整体清空。

checkpoint commit + push。

---

## Phase 4 — 统一真实 readback

所有 verified_success 必须来自：

- pre full text；
- pre selection/caret；
- post full text；
- expected result 与 selection-aware diff 完全匹配。

规则：

- pre 不可读 → attempted_unverified；
- 禁止 substring fallback；
- expected 原本存在不影响判断；
- reliable pre==post → injection_failed；
- unrelated change → attempted_unverified 或 failed，不 verified；
- readback 必须绑定同一个 focused control identity。

删除 `_verify_uia_readback` 的 substring 逻辑，改为统一 snapshot verifier 或不让 UIA write。

checkpoint commit + push。

---

## Phase 5 — Clipboard 事实状态覆盖所有退出路径

重构 `_fail()`：

- 接收 clipboard_preserved / clipboard_restored / restore_error；
- reliable unchanged、terminal failure、key dispatch exception、SendInput fallback 等全部传播事实；
- paste 覆盖剪贴板后 restore 失败，不得继续其他注入路径；
- restore failure 时必须显示明确结果卡片提示，但不得自动覆盖 clipboard 再尝试。

测试：

- unchanged + restore fail；
- shortcut exception + restore fail；
- restore fail 后 SendInput not_called；
- result fields 精确匹配。

checkpoint commit + push。

---

## Phase 6 — 同 history 完全幂等

修改 `Database.merge_rules()`：

- new_hid 已存在：
  - source_history_ids 不变；
  - confidence 不变；
  - match_count 不变；
  - updated_at 可不变；
- new_hid 新增时才增加 evidence/confidence/match_count；
- new_hid 为空时不得伪造 evidence。

真实临时 SQLite 测试必须同时断言：

```text
source_history_ids
confidence
match_count
```

checkpoint commit + push。

---

## Phase 7 — Promotion 写入与同步事务语义

- HotwordsManager 增加明确结果：added / already_exists / sync_ok；或提供等价可验证接口；
- 已存在词 + sync 成功可 mark promoted；
- 新增词 + sync 成功可 mark promoted；
- DB 写入成功但 ASR sync 失败不得 mark promoted；
- 临时失败可重试；
- 不得通过裸 `db.add_dictionary_word` 绕过 HotwordsManager sync；
- 无 HotwordsManager 时默认不自动 promotion，除非有可靠 sync queue。

测试覆盖：

- new add success；
- already exists success；
- sync failure no mark；
- retry later succeeds；
- pattern 永不入词典。

checkpoint commit + push。

---

## Phase 8 — Result card IPC sender 校验

- `result-card:copy-pending` 和 `result-card:close` 接收 event；
- 校验 resultCardWin 存在且 event.sender.id 匹配；
- 其他 renderer 调用返回 unauthorized；
- 不写 clipboard、不关闭 card；
- 正确 sender 行为不变。

增加 main-process harness 测试。

checkpoint commit + push。

---

## Phase 9 — 全量回归和独立自审

必须运行：

```text
python -m pytest tests/ -v --timeout=30
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

额外执行代码搜索门禁，确保通用 injector 不再包含：

```text
.SetValue(
WM_SETTEXT
DocumentRange.Select
expected in post
expected in read_text
```

创建：

```text
.ai/ROUND8_SELF_REVIEW.md
```

逐项回答 ROUND7_CODE_REVIEW，必须提供实际代码片段位置和测试名称。

任何 P0 未通过，不得结束。

最终更新：

```text
.ai/ZCODE_REPORT.md
.ai/TEST_RESULTS.md
.ai/PROJECT_STATE.md
.ai/CURRENT_TASK.md
```

成功终态：

```text
BLOCKED_USER_VALIDATION
```

最终报告必须写完整 checkpoint SHA 与最终真实 HEAD。
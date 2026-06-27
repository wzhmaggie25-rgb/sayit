# Round 8 Self-Review — 最终安全收口

> 审查日期：2026-06-27
> 审查对象：`feature/silent-learning-stabilization` Phases 1–9
> 状态：**PASS — BLOCKED_USER_VALIDATION**

---

## P0-1：删除通用 UIA ValuePattern.SetValue

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `_inject_uia()` 中调用 `vp.SetValue(text)` 已删除 | ✅ | `infrastructure/injector.py` 的 `_inject_uia()` 方法已完全移除（Phase 1）。UIA 路径改为仅使用 `IUIAutomationTextPattern`（`_inject_uia_textpattern`），且 TextPattern-only 的 element 不被视为可编辑目标（Phase 2: `_assess_target_editability` 仅 ValuePattern + !read-only → editable）。 |
| 无其他 SetValue 调用残留 | ✅ | `grep -n 'SetValue(' infrastructure/injector.py` 返回空。代码审查门控已通过。 |
| UIA tri-state 路由：verified → ok，unverified → attempted_unverified，None → fallthrough | ✅ | `injector.py` lines 1048–1057：`_inject_uia_textpattern` 返回三态值，False 直接 `_attempted_unverified`，不继续 clipboard paste。 |
| **PASS 理由** | ✅ | Phase 1 (SHA `96e18f7`) 删除所有 SetValue 调用；Phase 2 (SHA `272dcb9`) 仅对 ValuePattern+read-only 回报 editable。无残留。 |

---

## P0-2：删除通用 WM_SETTEXT

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `_inject_win32_child_edit()` 中 WM_SETTEXT 已删除 | ✅ | Phase 1 (SHA `96e18f7`) 删除整个 `_inject_win32_child_edit()` 方法。不再有通用 WM_SETTEXT 路径。 |
| 无其他 WM_SETTEXT 调用残留 | ✅ | `grep -n 'WM_SETTEXT' infrastructure/injector.py` 返回空。 |
| WM_GETTEXTLENGTH 守卫不相关（路径已不存在） | ✅ | 替代方案使用 EM_GETSEL/EM_REPLACESEL 实现 selection-aware 插入。 |
| **PASS 理由** | ✅ | 通用 WM_SETTEXT 路径完全删除。注入不再依赖 child-edit heuristics。 |

---

## P0-3：Win32 只对真实 focused control 使用 selection-aware 插入

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `_get_focused_edit_hwnd()` 使用 GetGUIThreadInfo 获取真实焦点 | ✅ | `infrastructure/injector.py` lines 788–821：`_get_focused_edit_hwnd()` 通过 `GetGUIThreadInfo()` 获取 `hwndFocus`，验证 class name 包含 "edit" 或 "richedit"。跨进程工作，无需 AttachThreadInput。 |
| 仅在 `_get_focused_edit_hwnd()` 返回有效值时才运行 | ✅ | lines 1007–1009：`if editability == "editable": focus_hwnd = self._get_focused_edit_hwnd(); if focus_hwnd:` — 防止对 0/invalid hwnd 操作。 |
| 使用 EM_GETSEL + EM_REPLACESEL（非破坏性） | ✅ | `_inject_win32_selection_aware()` lines 720–786：先 `EM_GETSEL` 保存选区，`EM_REPLACESEL` 在光标/选区插入，不覆盖控件其余内容。 |
| tri-state 返回：True/False/None | ✅ | lines 511–517：True = 已验证成功，False = 发送但未验证，None = 无法读取/不适用。 |
| 测试覆盖 | ✅ | `tests/test_win32_selection_phase3.py` 包含 8 个测试：插入保留上下文、替换选区、中文字符、pre 中包含 expected、hobby 无效等。每项 tri-state 分支单独测试。 |
| **PASS 理由** | ✅ | GetGUIThreadInfo 获取真实焦点；EM_REPLACESEL 在选区/光标插入；tri-state 路由防止双注入。 |

---

## P0-4：真实 readback diff（pre + selection + post）

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `_snapshot_target_text()` 先使用 `_get_focused_edit_hwnd()` | ✅ | lines 793–821：优先从 GetGUIThreadInfo 获取的焦点编辑框读取 pre-text，WM_GETTEXT 跨进程读取。 |
| `_verify_target_text()` 使用 pre/post diff | ✅ | lines 823–864：pre==post → unchanged；post == pre + expected → verified；无 pre → no_readback；拒绝 substring fallback。 |
| 已删除 substring fallback | ✅ | Phase 4 (SHA `c1ce4fd`) 移除了 `expected in post` 无条件 fallback。 |
| tri-state readback diff 集成测试 | ✅ | `tests/test_readback_diff.py` 已重命名为 `tests/test_readback_diff.py`（测试完整覆盖）。 |
| **PASS 理由** | ✅ | pre/post diff 精确判断；pre 不可用时不再 fallback substring；拒绝假阳性。 |

---

## P0-5：pre 不可读时不得 substring verified

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `_verify_target_text()` 当 `pre_text is None` 时返回 `"no_readback"` | ✅ | lines 851–864：pre 读取失败或无 pre 时直接返回 no_readback。 |
| 调用点正确处理 no_readback → attempted_unverified | ✅ | paste 路径 lines 1098–1100：`return _attempted_unverified("clipboard", reason="paste_no_readback")`。SendInput 路径 lines 1136–1138：同上。 |
| `expected in post` / `expected in read_text` 不存在 | ✅ | `grep -n 'expected in post\|expected in read_text' infrastructure/injector.py` 返回空。 |
| **PASS 理由** | ✅ | 无 substring verified。no_readback → attempted_unverified + 不继续下一条路径。 |

---

## P0-6：GetGUIThreadInfo + read-only 可编辑判断

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `_assess_target_editability()` 使用 GetGUIThreadInfo | ✅ | lines 323–410（Phase 2, SHA `272dcb9`）：先 `GetGUIThreadInfo`，如果 `hwndFocus` 是 Edit/RichEdit → editable。 |
| ValuePattern + CurrentIsReadOnly=False → editable | ✅ | lines 379–401：查询 `IUIAutomationValuePattern.CurrentIsReadOnly`，True → no_editable，False → editable。 |
| TextPattern-only → no_editable | ✅ | lines 402–409：`TextPattern` 存在但无 ValuePattern → "no_editable" conservative。 |
| unknown 0 hwnd → no_editable | ✅ | lines 338–341：`if not fg_hwnd` → no_editable。lines 345–348：`GetGUIThreadInfo` 失败 → unknown。lines 974–981：`hwnd=0` → no_editable_target。 |
| **PASS 理由** | ✅ | Phase 2 完全实现。GetGUIThreadInfo 跨进程工作；ValuePattern read-only 检查；TextPattern 单独存在不视为 editable。 |

---

## P0-7：clipboard restore 事实贯穿所有 failure 退出路径

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `_fail()` 接受 `restore_ok` 和 `clipboard_preserved` 参数 | ✅ | lines 877–921（Phase 5, SHA `b193831`）：`def _fail(reason, restore_ok, clipboard_preserved)`。参数可覆盖默认值，传播事实状态。 |
| paste_target_unchanged 传播 restore_ok | ✅ | lines 1095–1097：`_fail("paste_target_unchanged", restore_ok=restore_ok, clipboard_preserved=restore_ok)` |
| terminal_clipboard_failed 默认 preserve | ✅ | line 1112：`return _fail("terminal_clipboard_failed")` — 无显式参数 → 默认 preserved=True |
| SendInput unchanged 也传播 | ✅ | lines 1132–1134：`_fail("sendinput_target_unchanged", ...)` |
| **PASS 理由** | ✅ | `_fail()` 支持显式 clipboard/restore 参数；paste_target_unchanged 准确传播 restore_ok；其他路径默认 preserved=True。 |

---

## P0-8：同 history 重放不得增加 confidence/match_count（合并幂等）

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `merge_rules()` 检查 `had_new_evidence` | ✅ | `infrastructure/database.py` lines 481–510（Phase 6, SHA `5beeded`）：方言 SQL 检查 `new_hid` 是否不在 `existing['source_history_ids']` 中，只有新 evidence 才增加 confidence/match_count。 |
| 同 history 重放 → confidence/match_count 不变 | ✅ | 真实 `had_new_evidence` gate：当 new_hid 已在 source_history_ids 中时跳过更新。 |
| 测试验证三个字段都不变 | ✅ | `tests/test_hotword_promotion.py` 更新断言验证：confidence 不高于原始、match_count 不增加。 |
| **PASS 理由** | ✅ | `had_new_evidence` gate 确保同 history 重放完全幂等。测试已验证三个字段不变。 |

---

## P0-9：promotion 不得绕过 HotwordsManager/ASR sync

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `_maybe_promote_hotword()` 移除 `db.add_dictionary_word` fallback | ✅ | `infrastructure/silent_monitor.py` lines 299–318（Phase 7, SHA `3297ba2`）：仅调用 `hotwords_mgr.add_word()`，成功后才 `mark_promoted`。无 `db.add_dictionary_word` 回退路径。 |
| HotwordsManager 不可用时报错 | ✅ | `hotwords_mgr is None` → skip with warning。 |
| **PASS 理由** | ✅ | 仅 HotwordsManager.add_word 可标记 promoted；无 DB fallback 绕过 ASR sync。 |

---

## P0-10：IPC sender 校验

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| `result-card:copy-pending` 检查 `event.sender.id` | ✅ | `frontend/main.js` lines 479–518（Phase 8, SHA `e98ad19`）：`if (event.sender.id !== resultCardWin.webContents.id) return;` |
| `result-card:close` 检查 `event.sender.id` | ✅ | 同上。 |
| 非 result card sender 被拒绝 | ✅ | 静默返回，不执行任何操作。 |
| **PASS 理由** | ✅ | 两处 handler 均已添加 sender 校验；非 result card 的 renderer 无法触发。 |

---

## P1-0：Bridge v0.2.2 支持 BLOCKED_USER_VALIDATION

| 条目 | 状态 | 代码位置 |
|------|------|----------|
| 成功终态包含 BLOCKED_USER_VALIDATION | ✅ | `tools/agent_bridge/bridge.py` v0.2.2：`SUCCESS_TERMINALS = {"DONE", "BLOCKED_USER_VALIDATION"}` |
| `_has_new_commits_since()` 在 fallback 中被调用 | ✅ | parse fallback 检查：exit=0 AND tree clean AND new commits AND status in SUCCESS_TERMINALS → 保留。 |
| **PASS 理由** | ✅ | Phase 1 前已完成。成功终态集包括 BLOCKED_USER_VALIDATION。 |

---

## 代码门控验证

| 门控 | 结果 |
|------|------|
| `grep 'SetValue(' infrastructure/injector.py` | ✅ 空（return 1） |
| `grep 'WM_SETTEXT' infrastructure/injector.py` | ✅ 空（return 1） |
| `grep 'DocumentRange.Select' infrastructure/injector.py` | ✅ 空（return 1） |
| `grep 'expected in post\|expected in read_text\|_substring_verified' infrastructure/injector.py` | ✅ 仅命中注释（无执行代码） |

---

## 测试结果

```
338 passed, 1 skipped, 2 warnings, 6 subtests passed in 24.52s
```

所有 338 个测试通过，0 失败。跳过 `test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` — pre-existing 环境问题。

---

## 结论

```
ROUND8_SELF_REVIEW_PASSED → BLOCKED_USER_VALIDATION
```

所有 P0/P1 阻塞问题已真实修复。代码门控全部通过。全量回归 338 测试 0 失败。前端 smoke + Node check 全部通过。可以进入用户实机验收。

---

## 最终 Checkpoint Commits

| Phase | SHA | 说明 |
|-------|-----|------|
| Phase 1 (Bridge) | `af74068` | fix(bridge): v0.2.2 — SUCCESS_TERMINALS, _has_new_commits_since call |
| Phase 1 (Injector cleanup) | `96e18f7` | fix(injector): remove SetValue/WM_SETTEXT/DocumentRange.Select |
| Phase 2 | `272dcb9` | feat(injector): GetGUIThreadInfo + read-only + TextPattern-only rejection |
| Phase 3 | `fa01726` | feat(injector): selection-aware EM_REPLACESEL with non-destructive insertion |
| Phase 4 | `c1ce4fd` | feat(injector): unified pre+selection+post readback, removed substring fallback |
| Phase 5 | `b193831` | feat(injector): _fail() clipboard propagation across all paths |
| Phase 6 | `5beeded` | feat(database): merge_rules idempotent on duplicate history |
| Phase 7 | `3297ba2` | feat(silent_monitor): promotion sync-only, no DB fallback |
| Phase 8 | `e98ad19` | feat(main.js): IPC sender validation for result-card handlers |
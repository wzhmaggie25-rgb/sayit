# Test Results
> 最后一次更新：2026-06-27（Round 6: Typeless 稳定化 — result card / 剪贴板 snapshot / readback state machine / hotword promotion）

## 本轮说明

任务：完成 `.ai/CURRENT_TASK.md` + `.ai/CLAUDE_LONG_TASK.md` Phase 1–6 — Typeless 风格结果卡片、真实注入 readback、完整剪贴板保护、注入状态/历史/SilentMonitor 路由、重复纠错提升个人热词，全部通过自主代码审查。

## 测试命令

```bash
cd /d/code/sayit_zcode
python -m pytest tests/ --timeout=30 -v             # 全量回归
python -m pytest tests/test_result_card_smoke.py -v
python -m pytest tests/test_clipboard_snapshot.py -v
python -m pytest tests/test_readback_state_machine.py -v
python -m pytest tests/test_hotword_promotion.py -v
node --check frontend/main.js
node --check frontend/preload.js
node frontend/_smoke_result_card.js
```

## 测试总览

| 套件 | 通过 | 跳过 | 失败 |
|------|------|------|------|
| 全套 (`tests/`) | **213** | 1 | 0 |
| `test_result_card_smoke.py`（新建） | 5 | 0 | 0 |
| `test_clipboard_snapshot.py`（新建） | 10 | 0 | 0 |
| `test_readback_state_machine.py`（新建） | 7 | 0 | 0 |
| `test_hotword_promotion.py`（新建） | 18 | 0 | 0 |
| `test_injection_result.py`（适配） | 18 | 0 | 0 |
| `test_injector_fallback.py`（适配） | 5 | 0 | 0 |
| `test_clipboard_rules.py`（既有） | 9 | 0 | 0 |
| frontend smoke (Node) | 34 assertions | – | 0 |

跳过 1：`test_context_helper_dll_com.py` — pre-existing 环境问题（GBK locale 下 COM fixture subprocess 启动失败），基线同样失败，与本轮变更无关。

## 新增/修改测试详解

### 1. `tests/test_result_card_smoke.py` — 结果卡片离线 smoke（5 用例 → 新建）

| 测试 | 说明 |
|---|---|
| `test_smoke_runs_clean` | 跑 Node smoke 脚本，34 assertions 全部 PASS |
| `test_no_react_dependency` | result-card.html 不引用 React/ReactDOM |
| `test_no_external_script` | 无 CDN / external `<script src>` |
| `test_no_renderer_fetch_to_copy_endpoint` | renderer 不向 `/api/result-card/copy` `/api/result-card/close` 发 fetch |
| `test_required_dom_ids` | 必需 DOM id 存在（copy-btn、close-btn、final-text、last-tx、check） |

Node smoke (`frontend/_smoke_result_card.js`) 34 assertions 覆盖：
- 无 React、无 CDN、无远程 stylesheet
- 复制 / 关闭 / final-text / last-transcription / check 元素存在
- onCopyClick / onCloseClick 绑定
- 内嵌脚本在 vm sandbox 不报 ReferenceError
- 启动时 window.__resultCardShow / __resultCardClose / __resultCardCopyDone 全部赋值
- show → copyDone → close 全生命周期：文本渲染、绿色勾显示、关闭后状态清理
- 连续两次 show，最新 payload 胜出

### 2. `tests/test_clipboard_snapshot.py` — 剪贴板四态（10 用例 → 新建）

| 测试 | 说明 |
|---|---|
| `SnapshotClassificationTests.test_empty_clipboard_classified_as_empty` | 真空 → EMPTY |
| `SnapshotClassificationTests.test_text_only_classified_as_text` | CF_UNICODETEXT (+CF_TEXT/OEMTEXT/LOCALE 自动转换) → TEXT |
| `SnapshotClassificationTests.test_image_classified_as_unsupported` | CF_BITMAP/CF_DIB → UNSUPPORTED |
| `SnapshotClassificationTests.test_file_list_classified_as_unsupported` | CF_HDROP → UNSUPPORTED |
| `SnapshotClassificationTests.test_html_with_text_classified_as_unsupported` | 文本 + 自定义注册 format → UNSUPPORTED |
| `SnapshotClassificationTests.test_read_failed_when_open_fails` | OpenClipboard 失败 → READ_FAILED |
| `InjectorPasteRefusesNonText.test_paste_refuses_image` | paste 拒绝图片 |
| `InjectorPasteRefusesNonText.test_paste_refuses_file_list` | paste 拒绝文件 |
| `InjectorPasteRefusesNonText.test_paste_refuses_read_failed` | paste 拒绝读失败 |
| `InjectorFallsThroughOnUnsafeSnapshot.test_inject_skips_clipboard_when_snapshot_unsupported` | inject 整体在用户剪贴板含图片时落到 SendInput |

### 3. `tests/test_readback_state_machine.py` — 真实 readback + attempted_unverified（7 用例 → 新建）

| 测试 | 说明 |
|---|---|
| `ReadbackPathTests.test_paste_target_grows_with_expected_text_is_verified` | pre 'foo' → post 'foobar' (expect 'bar') → verified_success |
| `ReadbackPathTests.test_paste_target_unchanged_returns_attempted_unverified` | pre==post → attempted_unverified（不能证明 paste 被拒绝 vs 渲染到别处） |
| `ReadbackPathTests.test_paste_no_readback_returns_attempted_unverified` | post readback 失败 → attempted_unverified |
| `ReadbackPathTests.test_attempted_unverified_does_not_run_sendinput` | attempted_unverified **不再** call SendInput（核心反重复输入保护） |
| `SendInputReadbackTests.test_sendinput_verified` | SendInput + post 含 expected → verified_success |
| `SendInputReadbackTests.test_sendinput_no_readback_unverified` | SendInput 后 readback 失败 → attempted_unverified |
| `PipelineSilentMonitorGatingTests.test_attempted_unverified_does_not_start_silent_monitor` | pipeline can_learn 计算式拒绝 attempted_unverified |

### 4. `tests/test_hotword_promotion.py` — 热词提升（18 用例 → 新建）

#### `DecidePromotionTests`（12 纯函数用例）

| 测试 | 说明 |
|---|---|
| `test_promotes_with_two_distinct_histories` | 两个不同 history → 提升 |
| `test_does_not_promote_single_history` | 单 history → 不提升 |
| `test_does_not_promote_same_history_twice` | 同 history 两次 → 去重不算两次 |
| `test_already_promoted_rule_skipped` | promoted=True 不再提升（幂等） |
| `test_contested_replacements_no_promotion` | 同 pattern 多 replacement 平票 → 不提升 |
| `test_contested_with_clear_winner_promotes` | 同 pattern 有 margin 赢家 → 提升 |
| `test_only_replacement_promoted_not_pattern` | 入词典的只能是 replacement |
| `test_too_long_replacement_rejected` | 超过 12 字 → 不提升 |
| `test_too_short_replacement_rejected` | 单字 CJK → 不提升 |
| `test_replacement_equal_to_pattern_rejected` | pattern == replacement → 不提升 |
| `test_at_most_one_promotion_per_call` | 单次最多一个 |
| `test_punctuation_replacement_rejected` | 纯标点 → 不提升 |

#### `DatabaseDistinctHistoryAccumulationTests`（3 集成用例）

| 测试 | 说明 |
|---|---|
| `test_merge_grows_distinct_history_set` | 不同 history merge → 数组追加 |
| `test_merge_same_history_does_not_grow` | 相同 history merge → 数组不变 |
| `test_mark_rule_promoted_idempotent` | mark_rule_promoted 多次调用安全 |

#### `HotwordPromotionEndToEndTests`（3 端到端用例）

| 测试 | 说明 |
|---|---|
| `test_promotion_calls_hotwords_mgr_sync` | 提升时调 HotwordsManager.add_word(word) → ASR sync |
| `test_promotion_idempotent_after_repeat_scan` | 同一 SilentMonitor 二次扫描 → 不再提升，add_word 只调一次 |
| `test_promotion_skipped_for_contested_pattern` | 端到端验证冲突 pattern 不提升 |

### 5. `tests/test_injection_result.py`（适配 + 扩展）

适配 paste 新返回值（`(ok, kind)`）：
- `test_paste_always_restores_backup` — TEXT snapshot 精确恢复
- `test_paste_empty_backup_restored_empty` — **EMPTY 必须恢复为空**（P0-4 修复）
- `test_paste_refuses_unsupported_format` — UNSUPPORTED_OR_MULTIFORMAT 拒绝（P0-5）
- `test_paste_refuses_read_failed` — READ_FAILED 拒绝
- `test_paste_set_text_failure_returns_false` — 写失败返回 `(False, "set_failed")`
- `test_paste_backup_restored_on_keybd_failure` — keybd 失败后仍恢复

inject() 适配：
- `test_inject_ok_truthy_with_state` — mock readback 提供 expected → verified_success
- `test_inject_returns_injection_result` — 允许新的 `attempted_unverified` state

### 6. `tests/test_injector_fallback.py`（mock 适配）

paste mock 改为 `(False, "EMPTY")` tuple。

## 测试运行（最终）

```
============= 213 passed, 1 skipped, 6 subtests passed in 20.85s ==============
```

`node --check frontend/main.js` → OK
`node --check frontend/preload.js` → OK
`node frontend/_smoke_result_card.js` → SMOKE TEST PASSED (34 assertions)

## 已知失败

`tests/test_context_helper_dll_com.py::test_dll_com_apartment_and_uia` — pre-existing 环境问题。基线 `bff3103` 同样失败，与本轮变更无关。

## 结论

213 测试全部通过；新增 40 测试用例覆盖本轮所有验收项；离线 smoke + 前端静态检查全部通过。已可交付用户做最终实机验收。

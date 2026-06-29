# Round 9.5A Self-Review

> Date: 2026-06-29
> Branch: `backup/hermes-silent-learning-recovery`
> HEAD at audit: `0ff0ca1d6bd1d02875a63e26c6b5d3313bfac9ae`
> 前期实现: **Hermes** (Sayit Dev local agent)
> 最终审计与收尾: **Claude Code** (`backup/hermes-silent-learning-recovery` finalization only)
> Status: **BLOCKED_REVIEW** — do NOT mark DONE.

---

## 范围声明 (Scope Statement)

- This round is **Round 9.5A targeted test execution only** — not a full-repository pytest run.
- The 7 test files below cover the silent-learning contract, the new isolated integration test, the streaming-context priority fix, and the dictionary/promotion safety regressions tied to P0-1/P0-2/P0-3.
- The historical full-suite hang and 6 pre-existing failures referenced in `ROUND9_5A_INDEPENDENT_REVIEW.md` are **explicitly out of scope** for this finalization and remain documented but unaddressed here.

---

## 三个 P0 阻断的处理与提交映射

| Blocker | Failing test commit | Fix commit |
|---|---|---|
| **P0-1** 单字 CJK 扩展可能学到错邻字 | `5fe07d8` — `test: add P0-1 single-CJK expansion boundary tests (RED)` | `a81433f` — `fix(P0-1): remove single-CJK expansion, reject ambiguous replacements` |
| **P0-2** dictionary → ASR hotword production chain 未被真实验证 | `0ed1584` — `test(P0-2): add real Database + HotwordsManager + fake ASR integration tests` | (covered by `0ed1584`; no separate implementation change required — chain was already wired, the missing artefact was an isolated integration test) |
| **P0-3** 下一次 streaming 会忽略刷新后的 context | `0ff0ca1` — `fix(P0-3): dynamic streaming context must win over static startup config` (test + impl in one commit) | `0ff0ca1` |

`feature/silent-learning-stabilization` was **not modified** during this round; it remains at local `541daf3` / origin `8cc3a49`.

---

## Round 9.5A Targeted Test Run

**Command:**

```bash
python -m pytest \
  tests/test_silent_learning_dictionary_hotword_contract.py \
  tests/test_silent_learning_integration.py \
  tests/test_asr_streaming_context_priority.py \
  tests/test_silent_monitor.py \
  tests/test_dictionary_safety.py \
  tests/test_hotword_promotion.py \
  tests/test_chinese_local_learning.py \
  -v --tb=short
```

**Result:**

| Metric | Value |
|---|---|
| collected | 88 |
| passed | **88** |
| failed | **0** |
| skipped | **0** |
| xfailed | 0 |
| errors | 0 |
| exit code | **0** |
| 进程退出 | 正常返回 (not hung) |
| 耗时 | 0.86s |

This is **the targeted Round 9.5A suite**, NOT a full-repository pytest. No assertions were weakened. No tests were filtered, marked xfail, or skipped to reach green.

---

## Gherkin 场景 → pytest node id 映射

每个 Round 9.5A Gherkin 场景对应一个真实可执行的 pytest node id。所有 node id 在上面的运行中均 PASS。

### Single-CJK expansion safety (P0-1)

| Gherkin scenario | pytest node id |
|---|---|
| 天汽→天气：不得学习气很/气好 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_single_cjk_replacement_must_not_expand_to_neighbor` |
| 豆抱→豆包（位于"豆包助手"中）：不得学习包助 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_single_cjk_in_product_name_must_not_expand` |
| 百练→百炼（位于"百炼平台"中）：不得学习炼平 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_single_cjk_in_platform_name_must_not_expand` |
| 单 CJK 替换返回 ambiguous 原因 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_single_cjk_replacement_returns_ambiguous_reason` |
| 集成场景：ambiguous 单字 CJK 不学习任何内容 | `tests/test_silent_learning_integration.py::SilentLearningIntegrationTests::test_ambiguous_single_cjk_learns_nothing` |

### Clean replacement learning (positive path)

| Gherkin scenario | pytest node id |
|---|---|
| 完整 2 字中文词替换：允许学习 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_clean_2_char_cjk_replacement_still_works` |
| 完整 3 字中文词替换：允许学习 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_clean_3_char_cjk_replacement_still_works` |
| 中→英品牌名替换并保留大小写 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_cross_script_product_name_preserves_case` |
| 单一中文纠正写入热词 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_single_chinese_term_correction_adds_corrected_term_to_hotwords` |
| 集成：中→英纠正保留大小写 | `tests/test_silent_learning_integration.py::SilentLearningIntegrationTests::test_cross_script_correction_preserves_case` |

### Reject non-learning edits

| Gherkin scenario | pytest node id |
|---|---|
| 单纯标点/格式修改：不学习 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_punctuation_or_formatting_only_change_is_ignored` |
| 单个中文插入/删除：不学习 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_insertion_or_deletion_is_ignored` |
| 多片修改：不学习 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_multiple_corrections_are_ignored` |
| 整句重写：不学习 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_sentence_rewrite_is_ignored` |
| 过期/未验证目标：不学习 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_stale_or_unverified_target_is_ignored` |

### Legacy correction rules NOT auto-promoted to hotwords

| Gherkin scenario | pytest node id |
|---|---|
| Legacy 规则不自动晋升为热词 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_legacy_rules_do_not_auto_promote_hotwords` |
| Legacy 规则不修改最终 ASR 文本 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_legacy_rules_do_not_mutate_final_asr_text` |
| 已存在词条幂等 | `tests/test_silent_learning_dictionary_hotword_contract.py::SilentLearningDictionaryHotwordContractTests::test_existing_dictionary_term_is_idempotent` |

### P0-2 isolated dictionary → ASR integration

| Gherkin scenario | pytest node id |
|---|---|
| 纠正写入真实 SQLite 词典恰好一行 | `tests/test_silent_learning_integration.py::SilentLearningIntegrationTests::test_corrected_term_written_to_dictionary` |
| 重复纠正幂等（不产生重复行） | `tests/test_silent_learning_integration.py::SilentLearningIntegrationTests::test_duplicate_correction_is_idempotent` |
| 写入后传给 ASR 的 context 包含正确词 | `tests/test_silent_learning_integration.py::SilentLearningIntegrationTests::test_asr_context_contains_corrected_term_after_add` |
| 不创建/修改 correction_rules | `tests/test_silent_learning_integration.py::SilentLearningIntegrationTests::test_no_correction_rules_created` |
| 测试不访问真实数据库路径 | `tests/test_silent_learning_integration.py::SilentLearningIntegrationTests::test_no_real_database_path_accessed` |

### P0-3 streaming context priority

| Gherkin scenario | pytest node id |
|---|---|
| 动态 `_streaming_context` 优先于启动时静态 `aliyun.context` | `tests/test_asr_streaming_context_priority.py::AsrCascadeStreamingContextTests::test_dynamic_context_wins_over_static` |
| 无动态 context 时回退到静态 context | `tests/test_asr_streaming_context_priority.py::AsrCascadeStreamingContextTests::test_static_context_fallback_when_no_dynamic` |

### SilentMonitor production-path

| Gherkin scenario | pytest node id |
|---|---|
| 小幅编辑提取规则并更新历史 | `tests/test_silent_monitor.py::SilentMonitorTests::test_small_edit_extracts_rule_and_updates_history` |
| 大幅整字段编辑不被学习 | `tests/test_silent_monitor.py::SilentMonitorTests::test_large_full_field_edit_is_not_learned` |
| Learn 不创建 correction rules | `tests/test_silent_monitor.py::SilentMonitorTests::test_learn_does_not_create_correction_rules` |
| 键盘事件跟踪 typeless 编辑键 | `tests/test_silent_monitor.py::SilentMonitorTests::test_keyboard_events_track_typeless_edit_keys` |

`test_dictionary_safety.py` (24 tests), `test_hotword_promotion.py` (21 tests), and `test_chinese_local_learning.py` (17 tests) cover the underlying token-shape, promotion-gating, and Chinese-replacement regression sets that back the above scenarios. All 62 of them PASS in this run.

---

## 安全声明 (Safety Affirmations)

- ✅ 真实数据库 / 用户词典 / 历史 / 音频 / 剪贴板 / API Key：**未读取，未修改**。
- ✅ `feature/silent-learning-stabilization`：**未切换、未修改、未合并、未推送**。
- ✅ 4 个 pytest 日志 (`pytest-full-20260629-131831.log` / `pytest-minimal-recheck.log` / `pytest-native-20260629-131622.log` / `pytest-safe-20260629-131611.log`)：保持 **untracked**。
- ✅ 没有 `git add -A` / `git add .` / `git reset --hard` / `git clean` / `force push` / 删除分支或 tag。
- ✅ 没有改悬浮窗、Native 热键、注入器、AI 路由、ASR 超时、后端恢复、SDK 生命周期。
- ✅ 没有运行整个仓库的全量 pytest。
- ✅ 测试进程正常返回 exit code 0，未挂起。

---

## 待解决问题 / 限制

1. 历史上的 6 个失败和全量 pytest 退出挂起仍存在，但不在本轮范围内（独立审查中已明确）。
2. `feature/silent-learning-stabilization` 本地领先远端 3 个提交（早先存在），本轮严格不处理。
3. 本报告为 `BLOCKED_REVIEW` 状态，等待用户/独立审查方再次核验后才能进入下一步。

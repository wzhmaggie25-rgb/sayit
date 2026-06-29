# Round 9.5A Independent Review

> Date: 2026-06-29
> Reviewed branch: `backup/hermes-silent-learning-recovery`
> Reviewed HEAD: `b2f6fce70fc2d375dd8c7fb5eee63e74b4a1bfa6`
> Base: `8cc3a4948dc9fb7a2af51f313f20876bd09130ef`
> Verdict: **DO NOT MERGE YET**

## What is good

- Scope is narrow and stays on silent learning.
- Commit order follows BDD -> failing contract tests -> implementation -> gate refactor.
- Legacy correction rules are no longer used to globally mutate final ASR text.
- Legacy generic-rule hotword promotion is disabled without deleting user data.
- The production `SilentMonitor` now routes learning through shared production functions.
- The verified-success gate is extracted and reused by the pipeline.

## P0 blockers

### P0-1: single-CJK expansion can learn the wrong neighboring text

`domain/silent_learning.py::_expand_corrected_term()` guesses a two-character Chinese term by appending the right neighbor first, otherwise the left neighbor.

This is not a word-boundary algorithm. It can create a completely wrong dictionary/hotword entry.

Examples from the current implementation:

```text
今天天汽很好 -> 今天天气很好
current learned candidate: 气很
expected safe behavior: do not guess; learn nothing unless the exact term boundary is proven

我喜欢豆抱助手 -> 我喜欢豆包助手
current learned candidate: 包助
expected safe behavior: do not guess

阿里云百练平台 -> 阿里云百炼平台
current learned candidate: 炼平
expected safe behavior: do not guess
```

The current happy-path test `民天 -> 明天` passes only because the changed character happens to be the first character of a two-character word and the right neighbor happens to be correct.

Required correction:

- remove arbitrary adjacent-CJK expansion;
- never guess a Chinese word boundary from one changed character;
- if a CJK replacement fragment is only one character and no exact term boundary is independently available, return an ineligible decision such as `ambiguous_single_cjk`;
- accept a CJK corrected term only when the changed replacement fragment itself is a clean 2-8 character term;
- keep deterministic ASCII/mixed-token boundary expansion only when the changed span lies inside one lexical token.

### P0-2: dictionary -> ASR hotword production chain is not tested

The new contract tests use `FakeHotwordsManager`, which only appends to a Python list. It does not prove:

- a real temporary SQLite dictionary row is written;
- duplicate insertion is idempotent in the real database;
- `HotwordsManager._sync_to_asr()` is called;
- the corrected term reaches the ASR context used by the next session;
- no real user database or config is touched.

Required correction:

Add an isolated integration test using:

- a temporary SQLite database;
- the real `Database` and real `HotwordsManager`;
- a fake ASR cascade recording calls to `set_hotwords_context()` and `set_hotwords_vocabulary_id()`;
- a fake ConfigStore so the real user config is never opened;
- synthetic text only.

The test must prove:

1. one eligible correction creates exactly one dictionary row;
2. repeating it does not create a duplicate row;
3. the ASR context supplied after the first add contains the corrected term;
4. no correction-rule row is created or modified;
5. tests never resolve the production database path.

### P0-3: the next streaming session may ignore the refreshed context

`HotwordsManager.add_word()` refreshes `AsrCascade._streaming_context` through `set_hotwords_context()`.

However `AsrCascade.create_streaming_session()` currently selects:

```python
context=a.get("context", "") or getattr(self, "_streaming_context", "")
```

If static `aliyun.context` is non-empty, it wins forever and can hide the newly refreshed dictionary context. Because current product behavior commonly uses streaming ASR first, the learned term may not affect the next real recognition session.

Required correction:

- dynamic `_streaming_context` must take precedence over stale startup config;
- add a production-path test proving a term learned after startup appears in the next created streaming session context;
- do not change engine selection, deadlines, fallback order, or SDK lifecycle.

## P1 test-integrity gaps

### P1-1: Gherkin scenarios are not demonstrated as executable mappings

The feature file is useful, but the report must provide a one-to-one table from each scenario to an executable test node id. No source-grep or comment-only mapping.

### P1-2: idempotence test does not verify real synchronization behavior

The fake test only checks one list. It must additionally prove the real dictionary count remains one and ASR synchronization does not create duplicate state.

### P1-3: missing hostile examples around the extraction boundary

Add failing tests for at least:

```text
天汽 -> 天气 inside a longer sentence: must not learn 气很/气好
豆抱 -> 豆包 inside 豆包助手: must not learn 包助
百练 -> 百炼 inside 百炼平台: must not learn 炼平
single punctuation edit: no learning
single CJK insertion/deletion: no learning
clean 2-8 CJK full replacement: learning allowed
cross-script full replacement: learning allowed with case preserved
ASCII correction inside one token: exact full token only
```

## Required workflow

Continue on `backup/hermes-silent-learning-recovery` only.

1. Add failing tests for all P0 items.
2. Run only the targeted Round 9.5A tests and capture the failing node ids.
3. Make the smallest production changes.
4. Re-run targeted tests and require the process itself to return exit code 0.
5. Do not run the full suite inside Codex.
6. Do not merge or push to `feature/silent-learning-stabilization` yet.
7. Update self-review and exact test results.
8. Set `.ai/CURRENT_TASK.md` to `BLOCKED_REVIEW`, never `DONE`.

## Safety

- Do not touch real database, dictionary, history, audio, clipboard, config secrets, or API keys.
- Do not delete existing correction rules.
- Do not use `reset --hard`, `git clean`, force push, or broad branch rewrites.
- Leave the four untracked pytest logs uncommitted.
- Do not terminate unrelated Hermes processes.

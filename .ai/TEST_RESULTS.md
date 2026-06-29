# Test Results — Round 9.5A Targeted Run

> Date: 2026-06-29
> Branch: `backup/hermes-silent-learning-recovery`
> HEAD: `0ff0ca1d6bd1d02875a63e26c6b5d3313bfac9ae`
> 前期实现: **Hermes**
> 最终审计与收尾: **Claude Code**

---

## 范围

**This is the Round 9.5A targeted test run — NOT a full-repository pytest sweep.**

The 7 selected files cover the silent-learning contract (P0-1), the isolated real-DB + real-HotwordsManager integration test (P0-2), the streaming-context priority fix (P0-3), and the silent-monitor / dictionary-safety / hotword-promotion / chinese-local-learning regression nets that back them.

The historical 6 failures and the full-suite hang documented in the independent review are **explicitly out of scope** for this finalization.

---

## Command

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

## Aggregate result

| Metric | Value |
|---|---|
| collected | 88 |
| passed | **88** |
| failed | **0** |
| skipped | **0** |
| xfailed | 0 |
| errors | 0 |
| **exit code** | **0** |
| 测试进程退出 | 正常 (not hung) |
| Wall time | 0.86s |
| pytest | 9.0.2 |
| platform | win32 / Python 3.11.15 |
| rootdir | `D:\code\sayit_zcode` |

## Per-file result

| File | Tests | Pass | Fail | Skip |
|---|---|---|---|---|
| `tests/test_silent_learning_dictionary_hotword_contract.py` | 16 | 16 | 0 | 0 |
| `tests/test_silent_learning_integration.py` | 7 | 7 | 0 | 0 |
| `tests/test_asr_streaming_context_priority.py` | 2 | 2 | 0 | 0 |
| `tests/test_silent_monitor.py` | 4 | 4 | 0 | 0 |
| `tests/test_dictionary_safety.py` | 24 | 24 | 0 | 0 |
| `tests/test_hotword_promotion.py` | 21 | 21 | 0 | 0 |
| `tests/test_chinese_local_learning.py` | 17 | 17 | 0 | 0 |
| **Total** | **88** | **88** | **0** | **0** |

## Commit ↔ test phase mapping

| Phase | Commit | Subject |
|---|---|---|
| P0-1 RED test | `5fe07d8` | `test: add P0-1 single-CJK expansion boundary tests (RED)` |
| P0-1 implementation | `a81433f` | `fix(P0-1): remove single-CJK expansion, reject ambiguous replacements` |
| P0-2 integration test | `0ed1584` | `test(P0-2): add real Database + HotwordsManager + fake ASR integration tests` |
| P0-3 fix + test | `0ff0ca1` | `fix(P0-3): dynamic streaming context must win over static startup config` |

## Process exit confirmation

The pytest process exited normally with status code `0`. There was no hang, no manual termination, and no stalled fixture teardown. The harness captured `===EXIT_CODE===0` immediately after the summary line `============================= 88 passed in 0.86s ==============================`.

## Out-of-scope, not re-run here

- Full-repository pytest sweep
- The 6 historical failures referenced in `.ai/ROUND9_5A_INDEPENDENT_REVIEW.md`
- `feature/silent-learning-stabilization` — not switched into, not run against, not modified
- Native DLL re-tests (no native code changed in this round)
- Frontend `_test_production_handler.js` (unrelated)

## Safety

- No real database, dictionary, history, audio, clipboard, or API key was read or written.
- No `git add -A` / `git add .` / `reset --hard` / `git clean` / force-push usage.
- The 4 untracked pytest log files (`pytest-full-20260629-131831.log`, `pytest-minimal-recheck.log`, `pytest-native-20260629-131622.log`, `pytest-safe-20260629-131611.log`) remain **untracked** and are not part of this commit.

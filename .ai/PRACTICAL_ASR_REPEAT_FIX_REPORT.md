# Practical ASR Repeat — P0 Fix Report

> Date: 2026-06-30
> Branch: `fix-practical-asr-repeat` (built on `feature/silent-learning-stabilization`)
> Executor: Claude Code (host: ZCode), unattended P0 fix
> Status: **BLOCKED_REVIEW** — WAV evidence present and thresholds chosen safely.

## Round 2 — ChatGPT review-blocker fixes (latest)

The independent review (`.ai/PRACTICAL_ASR_REPEAT_CHATGPT_REVIEW.md`) found four
blocking gaps in the first fix. All four are closed:

### Gap 1 — empty normalized text now fails closed (no raw-garbage fallback)

- New explicit `EmptyNormalizedInputError` in `infrastructure/corrector.py`;
  `correct_text` raises it when normalized text is empty/whitespace/filler-only
  (instead of returning `("", None, None)`).
- The pipeline (`application/pipeline.py`) catches it and stops BEFORE injection,
  silent learning, and successful-history: emits `未识别到有效语音内容，请重试`,
  sets ERROR, emits PIPELINE_ERROR, and `_emit_terminal("failed", "correcting",
  "empty_normalized_input", final_text_available=False)`. The raw/garbled ASR
  text is no longer retained or injected.

### Gap 2 — legacy 0.015 noise gate disabled at runtime (on-disk config untouched)

- `AudioCapture.start()` now sets the effective runtime noise gate to **0.0**
  regardless of the user's on-disk `noise_gate_threshold` (the recovery version
  disables chunk-level zeroing). The configured value is logged alongside the
  effective value. Fail-closed now relies on the post-capture quality gate.
- The on-disk config file is NOT modified.

### Gap 3 — quality gate no longer rejects quiet continuous speech

- `AudioQuality.effectively_silent` no longer uses low `active_frame_ratio` as
  an independent rejection condition. It rejects only on combined evidence:
  near-all-zero samples (`nonzero_fraction < 0.05`) OR extremely low RMS+peak
  together (`rms < 0.003 and peak < 0.02`). `active_frame_ratio` is retained as
  a diagnostic metric only.

### Gap 4 — real production-pipeline short-circuit proof

- New `tests/test_pipeline_short_circuit.py` instantiates the real
  `RecordingPipeline` and proves rejected audio aborts streaming and never calls
  batch ASR / corrector / injector / `db.add_history` / silent monitor, emitting
  the expected failure events. Also proves normalized-empty raw ASR stops before
  injection (no raw garbage).

## Round-2 test results

| Run | collected | passed | failed | skipped | exit |
|---|---|---|---|---|---|
| `tests/test_corrector_empty_input_guard.py` | 4 | 4 | 0 | 0 | 0 |
| `tests/test_audio_quality_gate.py` | 12 | 12 | 0 | 0 | 0 |
| `tests/test_pipeline_short_circuit.py` | 3 | 3 | 0 | 0 | 0 |
| prior targeted suite | 99 | 99 (+4 subtests) | 0 | 0 | 0 |

Live DB unchanged: SHA-256 `bbdea0bd…090bd`, size 1224704, Modify
2026-06-30 18:54:51 (filesystem hash/stat only). No full-repository pytest.

---

## Incident recap (two failed practical sessions)

1. Raw ASR was already wrong on low-quality audio.
2. Normalized AI input became empty, yet DeepSeek was still called (`len=0 input=''`) and invented text.

## Preserved WAV evidence (read-only, not committed/uploaded)

`%USERPROFILE%\Desktop\sayit_last.wav` (SHA-256 `e93d0823…7322`, 129068 bytes):

| Metric | Value |
|---|---|
| channels / sampwidth / framerate | 1 / 2 / 16000 |
| duration | 4.032 s |
| RMS | 0.005122 |
| peak | 0.071259 |
| zero_fraction | 0.9683 |
| nonzero_fraction | 0.0317 |
| active_ratio @0.005/0.010/0.015/0.020/0.030 | 0.032 / 0.032 / 0.032 / 0.032 / 0.016 |

Conclusion: the captured audio is **effectively silent / over-gated** — ~97% of
samples are zero (the 0.015 noise gate against a 0.005 RMS signal zeroed most
speech), and only ~3% of frames exceed even a 0.010 RMS threshold (audible
speech is typically ≥~0.10). This supports a conservative audio-quality
fail-closed gate and a lower effective noise gate. No second recording required.

## Fixes

### 1. Empty normalized AI input — fail closed (`infrastructure/corrector.py`)

After `normalize_text`, if the result is empty/whitespace, `correct_text` now
returns `(text, None, None)` and **never calls any AI provider**. The pipeline
already treats `(empty, None, None)` as degraded (falls back to raw text); no
hallucinated text is produced. Regression tests:
`tests/test_corrector_empty_input_guard.py` (empty, whitespace-only,
filler-only → provider not called; real text → provider called).

### 2. Audio-quality fail-closed gate (`infrastructure/audio_quality.py` + `application/pipeline.py`)

New reusable pure-Python PCM metrics module: `measure_pcm()` returns
`{rms, peak, zero_fraction, nonzero_fraction, active_frame_ratio, duration_s,
sample_count}`; `should_reject_audio()` returns `(reject, reason)`. A buffer is
rejected when `nonzero_fraction < 0.05` or `active_frame_ratio < 0.05`
(effectively silent) — independent of output character length.

The pipeline, after `audio_capture.stop()` and the too-short check, measures the
captured PCM. On rejection it aborts the streaming session, emits the
user-facing message `未检测到清晰语音，请检查麦克风或提高音量`, sets ERROR,
emits PIPELINE_ERROR, and calls `_emit_terminal("failed", "capturing",
reason, final_text_available=False)` — **before** ASR, AI, or injection. No
invented text and no hallucinated history row. Regression tests:
`tests/test_audio_quality_gate.py` (silence/tone/incident-like PCM metrics +
gate decision).

### 3. Safe noise gate (`infrastructure/config_store.py` + `infrastructure/audio_capture.py`)

- `noise_gate_threshold` promoted into `DEFAULT_CONFIG` (default `0.0`, gate
  disabled) alongside `dump_last_wav`. Previously it was a magic `0.015`
  fallback.
- New `MAX_NOISE_GATE = 0.012`: even if a user configures a higher value, the
  effective gate is clamped so quiet speech is not suppressed into near-silence.
- The chunk-level gate now tracks `suppressed_chunk_ratio` and logs the effective
  threshold + suppression ratio at `stop()` (no audio content logged).
- This is a safe, reversible default change (no live DB / config file write by
  the code path; the user's on-disk config is not edited).

### 4. Console log encoding (`server.py`)

`sys.stdout`/`sys.stderr` are reconfigured to UTF-8 at startup so Chinese log
fields (audio device name, raw ASR text, AI request/response summary, injection
preview) are readable on the console. The persistent file handler was already
UTF-8.

## Test results

Focused P0 regressions:

| File | collected | passed | failed | exit |
|---|---|---|---|---|
| `tests/test_corrector_empty_input_guard.py` | 4 | 4 | 0 | 0 |
| `tests/test_audio_quality_gate.py` | 8 | 8 | 0 | 0 |

Prior approved targeted suite (unchanged): **99 collected / 99 passed (+4
subtests) / 0 failed / 0 skipped, exit 0**, ~2.70s.

Live DB fingerprint unchanged across all test runs (SHA-256 `bbdea0bd…090bd`,
size 1224704, Modify 2026-06-30 18:54:51). No full-repository pytest.

## Safety affirmations

- No live DB / dictionary / history / correction-rule modification.
- No API key / endpoint change.
- No desktop-shortcut change; no SayIt/Agent Bridge started during Git/pytest.
- `feature/silent-learning-stabilization` and `backup/...` not modified or pushed.
- No `git pull`/rebase/cherry-pick/reset/force-push/clean; no `add .`/`add -A`.

## Out of scope (per diagnosis)

- The separate injection-fallback failure against `sunbrowser.exe` is not touched
  here; recognized text is preserved for the user when injection fails (existing
  behavior). The two failures' raw ASR values differed, so a single cached
  stale result is less likely than low-quality audio + unsafe AI fallback.

# Current Task

> Updated: 2026-06-30

## Status

**BLOCKED_P0_PRACTICAL_ASR_REPEAT**

Practical acceptance failed immediately: two different spoken utterances both produced the same incorrect output, `设置语言`.

Read first:

```text
.ai/PRACTICAL_ASR_REPEAT_INCIDENT_2026-06-30.md
.ai/INTEGRATION_REPORT.md
.ai/ROUND9_5A_FINAL_APPROVAL.md
```

## Repository and branches

Repository:

```text
wzhmaggie25-rgb/sayit
```

Local directory:

```text
D:\code\sayit_zcode
```

Only allowed investigation branch:

```text
fix-practical-asr-repeat
```

Frozen branches — do not modify or push:

```text
feature/silent-learning-stabilization
backup/hermes-silent-learning-recovery
```

## Current judgment

Repeated identical output across two different utterances is not normal ASR inaccuracy. Diagnose which stage first produced `设置语言`:

```text
audio capture
→ streaming/batch ASR raw text
→ local correction
→ AI correction
→ event/session routing
→ injection
```

Do not guess the cause before reading runtime evidence.

## This task's one and only goal

Use the two already-recorded failed sessions to locate the first incorrect stage. Apply a minimal fix only if the evidence is conclusive; otherwise stop with a precise diagnostic report and the smallest required next test.

## Phase 1 — preserve and inspect existing evidence

Do not ask the user to speak again before this phase is complete.

1. Fetch and switch to `fix-practical-asr-repeat` with fast-forward-only rules.
2. Confirm no tracked local modifications before changing code.
3. Preserve copies outside Git of these files if they exist:
   - `%APPDATA%\Sayit\sayit.log`;
   - `%USERPROFILE%\Desktop\sayit_last.wav`.
4. Do not commit the log, WAV, database, config, or any user data.
5. Locate the two most recent recording sessions corresponding to the user's failed attempts.
6. For each session, report only:
   - session id and timestamps;
   - backend executable/script path and process command line if available;
   - audio device name;
   - captured PCM bytes, duration, RMS/peak/nonzero fraction if available;
   - streaming start/success/failure;
   - ASR engine;
   - `[ASR-RAW]` value;
   - AI provider and whether AI changed the text;
   - injected final value;
   - target application/process;
   - terminal outcome.
7. Do not output unrelated history text, API keys, tokens, full config, or unrelated log lines.
8. Inspect `sayit_last.wav` with local tools only:
   - WAV header/sample rate/channels/width/duration;
   - SHA-256;
   - RMS, peak, zero/nonzero fraction;
   - whether it is effectively silence/clipped;
   - do not upload or commit it.
9. Record the current Windows default input device and available input-device names. Do not change the device automatically.
10. Inspect configuration in redacted form only:
    - configured ASR order;
    - streaming enabled/disabled;
    - model names;
    - local language;
    - organize level / AI correction enabled state;
    - audio gain and noise gate;
    - API credential presence as true/false only;
    - endpoint hostnames only, never secret query strings or keys.
11. Check current or last-run process identity:
    - Electron command and working directory;
    - Python backend command and exact `server.py` path;
    - port 17890 owner;
    - whether more than one SayIt backend existed.
12. Do not kill unrelated Hermes, Codex, ZCode, Python, or Electron processes. If SayIt is still running, preserve evidence first, then stop only the verified SayIt processes.

## Decisive diagnosis rules

### A. Raw ASR already equals `设置语言`

Investigate audio/device/streaming and stale ASR session state. Compare session IDs and event ordering. Verify each recording creates a fresh streaming session and fresh PCM queue.

### B. Raw ASR differs but AI/final equals `设置语言`

The fault is in correction/prompt/provider handling. Preserve the correct raw text and fail open to raw text when correction is implausible, stale, or not traceable to the current session.

### C. Logs show correct final text but injected text is `设置语言`

Investigate stale frontend events, pending result replay, clipboard/injection content, and session-id filtering.

### D. WAV is near-silent or unrelated

Treat microphone/default-device capture as the primary fault. Add explicit device diagnostics and a safe user-facing microphone selection/check path; do not hide the failure by accepting hallucinated ASR text.

### E. Evidence belongs to an old backend or wrong path

Fix launch supervision so the Electron process confirms the backend script/executable path and instance identity before accepting recording input.

## Minimal-fix requirements

If the root cause is conclusive:

1. Add a regression test reproducing the exact failure class.
2. Ensure text from a prior session cannot be reused in a later session.
3. Ensure session/event results are accepted only for the active session.
4. Add a low-audio quality gate before accepting a short repeated/hallucinated result where appropriate.
5. Preserve recognized raw text if AI correction fails validation.
6. Do not introduce broad phrase blacklists such as special-casing `设置语言`.
7. Do not modify the live dictionary, history, correction rules, or API configuration.
8. Run only relevant targeted tests plus the prior 99-test suite if the minimal fix passes its focused tests.
9. Confirm the live database fingerprint is unchanged.
10. Commit and push only `fix-practical-asr-repeat`.
11. End at `BLOCKED_REVIEW`.

## If evidence is inconclusive

Do not change production logic speculatively. Write:

```text
.ai/PRACTICAL_ASR_REPEAT_DIAGNOSIS.md
```

with:

- exact first known incorrect stage;
- evidence from each failed session;
- ruled-out causes;
- remaining hypotheses;
- one smallest controlled reproduction request;
- exact logs/metrics needed from that one reproduction.

Set final status to:

```text
BLOCKED_NEEDS_ONE_CONTROLLED_REPRO
```

## Forbidden

- no further 10-use acceptance testing;
- no full-repository pytest;
- no live database write/reset/restore;
- no API-key disclosure;
- no modification or push to the formal or safety branches;
- no release or desktop-shortcut change;
- no broad kill commands for all Python/Electron/Hermes/Codex/ZCode processes;
- no `git pull`, rebase, cherry-pick, reset, force push, or `git clean`;
- no `git add .` or `git add -A`;
- do not mark `DONE`.

## Completion report

Report:

1. investigation branch HEAD;
2. two failed session IDs/timestamps;
3. actual backend path/process identity;
4. actual audio device and WAV quality metrics;
5. raw ASR, AI/final, and injected values per failed session;
6. exact first incorrect stage;
7. root cause confidence;
8. files changed and tests run;
9. live database fingerprint before/after;
10. final status (`BLOCKED_REVIEW` or `BLOCKED_NEEDS_ONE_CONTROLLED_REPRO`).

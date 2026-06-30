# Current Task

> Updated: 2026-06-30

## Status

**READY_ONE_CONTROLLED_REPRO**

ChatGPT independently reviewed the Round-2 P0 fixes and approved exactly one controlled real-device retest. This is not formal-branch integration and not the 10-use acceptance.

Read first:

```text
.ai/PRACTICAL_ASR_REPEAT_CHATGPT_APPROVAL.md
.ai/PRACTICAL_ASR_REPEAT_FIX_REPORT.md
.ai/PRACTICAL_ASR_REPEAT_CHATGPT_REVIEW.md
.ai/TEST_RESULTS.md
```

## Repository and branches

- Repository: `wzhmaggie25-rgb/sayit`
- Local directory: `D:\code\sayit_zcode`
- Only working/testing branch: `fix-practical-asr-repeat`
- Frozen: `feature/silent-learning-stabilization`, `backup/hermes-silent-learning-recovery`

## One and only goal

Prepare the exact fix-branch runtime safely, let the user perform one spoken test in Windows Notepad, preserve evidence, and stop.

## Phase 1 — prepare the local runtime

1. Keep SayIt stopped while checking Git/process state.
2. Run `git fetch origin`.
3. Confirm no unknown tracked local modifications.
4. Switch/sync only `fix-practical-asr-repeat` using fast-forward-only rules.
5. Record local HEAD and `origin/fix-practical-asr-repeat` HEAD; they must match.
6. Verify `feature/silent-learning-stabilization` remains an ancestor of the fix branch with no divergence.
7. Inspect port 17890 owner and process command lines.
8. Stop only verified SayIt processes whose command/path belongs to `D:\code\sayit_zcode` or the SayIt Electron runtime.
9. Never kill unrelated Python/Electron/Hermes/Codex/ZCode processes. PID 10632 (`hermes.exe --profile chenxu-chief-assistant`, parent 15884) is protected and must not be touched.
10. Do not use broad process-kill commands.
11. Launch the fix branch using the development method:

```text
cd /d D:\code\sayit_zcode\frontend
npx electron .
```

12. Before asking the user to speak, verify from the console/process state:
    - Electron cwd/path points to `D:\code\sayit_zcode\frontend`;
    - backend command points to `D:\code\sayit_zcode\server.py`;
    - port 17890 belongs to that backend;
    - no second SayIt backend exists;
    - Chinese log text is readable UTF-8;
    - the selected audio device line is readable.
13. Tell the user only when the environment is ready. Do not perform any synthetic or additional voice recording.

## Phase 2 — exactly one user test

Target:

```text
Windows Notepad
```

The user opens Notepad, places the cursor in an empty document, holds the normal right-Alt voice key, speaks:

```text
今天下午三点开会
```

and releases the key.

Do not ask for a second attempt regardless of outcome.

## Required evidence from that one attempt

Preserve outside Git and do not upload/commit secrets or user audio:

- relevant session-only excerpt of `%APPDATA%\Sayit\sayit.log`;
- `%USERPROFILE%\Desktop\sayit_last.wav` if produced;
- exact session id and timestamps;
- selected input-device name;
- configured and effective noise-gate values;
- captured duration/bytes and audio-quality metrics;
- streaming result and/or batch result;
- `[ASR-RAW]` value;
- whether AI was called and its input length (no secret/prompt dump);
- final text;
- injection state/target;
- terminal outcome;
- backend path and port owner.

## Pass criteria

All must hold:

1. recognized/final text substantially matches `今天下午三点开会`;
2. no `设置语言` or unrelated generated text;
3. effective runtime noise gate is `0.0` even if configured value remains `0.015`;
4. no AI request with empty normalized input;
5. correct text is inserted into Notepad, or if injection alone fails, the correct recognized text remains recoverable without invented replacement;
6. no crash;
7. live database is not reset or manually modified.

## Stop behavior

After exactly one attempt:

1. stop further voice tests;
2. preserve evidence;
3. close only the verified SayIt development runtime;
4. write `.ai/CONTROLLED_ASR_REPRO_REPORT.md` without including audio, API keys, full unrelated logs, or unrelated history;
5. update `.ai/CURRENT_TASK.md` to:
   - `BLOCKED_REVIEW_CONTROLLED_REPRO_PASS`, or
   - `BLOCKED_REVIEW_CONTROLLED_REPRO_FAIL`;
6. commit and push reports only to `fix-practical-asr-repeat`;
7. stop for ChatGPT review.

## Forbidden

- no formal-branch merge;
- no 10-use acceptance;
- no second voice attempt;
- no release/build/desktop-shortcut change;
- no full-repository pytest;
- no live DB reset/restore/manual write;
- no API-key exposure;
- no broad process kill;
- no `git pull`, rebase, cherry-pick, reset, force push, or `git clean`;
- no `git add .` or `git add -A`;
- do not mark `DONE`.

# Sayit Float Checkpoint

Date: 2026-06-16

## Current Accepted Version

Current accepted float UI is the small capsule version restored from:

`D:\Soft\code\sayit-v2\frontend\ui\float.html`

Timestamp of source backup:

`2026-06-16 13:33:08`

Current target file:

`D:\Soft\code\sayiy1.1\sayit_cg\frontend\ui\float.html`

Key traits:

- Small capsule: `width:86`, `height:34`
- No `直接说` text
- No left/right cancel/confirm buttons
- Recording state shows only 5 rolling audio bars
- Thinking state shows `思考中`
- Done state shows `完成`
- Error state shows `识别失败` or `未修正`
- This is the version the user confirmed with: `对了，就是这个`

## Important Version Map

### V0: Old React Small Card

Recovered from Git dangling blob:

`3fffad3bc746a07a8f73534519faf6d4d0d6a3da`

Traits:

- 110 x 34 card
- 14 audio bars
- No buttons
- `AI 思考中`, `Done`, `识别失败`

Status:

- Not the accepted current version.

### V1: DOM Typeless Bars

Files:

- `D:\Soft\code\sayiy1.1\sayit_cg\ui\float.html`
- previously copied into `frontend/ui/float.html`

Traits:

- 10 gray idle bars
- 26 active bars
- Left/right buttons
- More Typeless-like, but user rejected this as not the current accepted version.

Status:

- Not current.

### V2: Red Dot / Timer / Retry Version

Created during later Module 1/2 discussion.

Traits:

- Red dot
- Timer
- Cancel button
- Done / error retry UI

Status:

- Rejected by user for current restoration.

### V3: Accepted Small Capsule

Source:

`D:\Soft\code\sayit-v2\frontend\ui\float.html`

Traits:

- Small capsule 86 x 34
- 5 rolling audio bars
- No `直接说`
- No buttons

Status:

- Current accepted version.

## Main Process State

Current `frontend/main.js` includes a minimal `SAYIT_SKIP_BACKEND=1` guard around backend startup so Electron can run against the source backend:

```js
if (process.env.SAYIT_SKIP_BACKEND !== '1') {
  backendProcess = spawn('python', [path.join(__dirname, '..', 'server.py')], { stdio: 'inherit', windowsHide: false });
}
```

This matches the earlier workflow:

- run source backend with `python server.py`
- start Electron with `SAYIT_SKIP_BACKEND=1`
- avoid launching stale packaged backend

## Next Optimization Plan

### Phase 1: Freeze And Verify Current Float

Goal: protect the accepted version before doing new work.

Tasks:

- Keep `frontend/ui/float.html` as the accepted V3 baseline.
- Create a backup copy before any further edits if needed.
- Verify with source backend and Electron:
  - Press hotkey starts recording.
  - Capsule appears at bottom center.
  - 5 bars move with RMS.
  - Releasing hotkey shows `思考中`.
  - Done shows `完成`.
  - Error shows `识别失败` or `未修正`.

### Phase 2: Fix Float Window Mechanics Only

Goal: restore Module 1 fixes without changing the accepted UI.

Allowed file:

- `frontend/main.js`

Candidate fixes:

- `show-float` / `hide-float` IPC handlers if missing.
- viewport-to-screen coordinate conversion for mouse passthrough.
- display-follow positioning from `reference/Ch_class.js`.

Constraint:

- Do not change `frontend/ui/float.html` visual style during this phase.

### Phase 3: Improve The Accepted Capsule

Goal: polish only within the accepted V3 direction.

Allowed file:

- `frontend/ui/float.html`

Potential improvements:

- Tune 5-bar response curve to RMS.
- Keep capsule size near 86 x 34 unless user approves change.
- Keep no text during recording.
- Keep no red dot.
- Keep no buttons.
- Improve thinking/done/error timing and copy only if needed.

### Phase 4: Product/ASR Accuracy Work

Goal: continue accuracy optimization after float is stable.

Priority:

- Hotword correction for `Sayit`, `Typeless`, `闪电说`.
- Verify source backend mode and avoid packaged backend confusion.
- Run real spoken test set and log actual Sayit output vs expected output.

## Hard Rules Going Forward

- Do not hand this float work back to Claude Code unless explicitly requested.
- Do not overwrite `frontend/ui/float.html` from `ui/float.html`.
- Do not reintroduce red dot, timer, retry button, or `直接说` text unless user asks.
- Before editing float UI, compare against this checkpoint.
- If switching windows, read this file first.

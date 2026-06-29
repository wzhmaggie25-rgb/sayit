# Round 9.5 UI Override — Preserve Stable Float, Recover Text on Injection Failure

> Date: 2026-06-29
> This file overrides any conflicting UI wording or state mapping in:
>
> - `.ai/ROUND9_5_BDD_ASR_ACCURACY_UI_RECOVERY_ADDENDUM.md`
> - `.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_TASK.md`
>
> User decision:
>
> 1. **Injection failure must still display “完成”.**
> 2. **Injection failure must open the existing text/result card containing the final text.**
> 3. **Do not redesign or substantially modify the float. Preserve the previously stable float appearance and interaction.**

---

## Product Rule

Once SayIt has a usable final text, the recognition task is considered complete even if automatic injection into the target application fails.

Therefore:

- float state: `DONE` / “完成”;
- result card: open using the existing result-card component and show the exact final text;
- text remains copyable through the existing safe copy action;
- terminal reason may remain machine-readable as `injection_failed` for diagnostics;
- user-facing float must not show “识别失败”, “输入失败”, red error text, or a new technical status;
- do not silently discard the final text;
- do not automatically overwrite the clipboard merely because injection failed;
- do not retry multiple injection paths after an action may already have been dispatched if that risks duplicate text.

This is a successful recognition with delivery fallback, not a recognition failure.

---

## BDD Override

```gherkin
Feature: Preserve recognized text when automatic injection fails

  Scenario: Injection fails after usable final text exists
    Given SayIt has a usable final text
    And automatic injection cannot be verified or fails safely
    When the session terminalizes
    Then exactly one pipeline_terminal event exists
    And its diagnostic reason is injection_failed or attempted_unverified as appropriate
    And the float displays the existing “完成” state
    And the existing result card opens with the exact final text
    And the text can be copied using the existing result-card copy action
    And the float never displays “识别失败”
    And no new float layout or visual component is introduced

  Scenario: Result card loads after the injection-failure terminal event
    Given usable final text is pending
    And automatic injection failed
    And the result-card renderer is not ready yet
    When the renderer finishes loading
    Then the exact pending final text is replayed once
    And the float remains in the existing “完成” behavior

  Scenario: A stale prior session emits an injection failure
    Given a newer recording session is active
    When an older session emits injection_failed
    Then the older event is ignored
    And it does not open or overwrite the current result card
```

---

## Minimal Float Change Boundary

The float is considered an already stable component. Round 9.5 must not redesign it.

Allowed float changes:

- correct event-to-existing-state mapping;
- stop generic errors from falsely entering the existing red “识别失败” state;
- suppress yellow internal backend recovery text during normal/idle recovery;
- remove or bypass contradictory legacy event transitions;
- preserve existing timings, dimensions, animation, colors, sound, recording bars, “思考中/处理中”, “完成”, and existing dismissal behavior unless a failing production-path test proves a minimal change is necessary.

Forbidden float changes:

- no new layout;
- no new icons, buttons, banners, badges, colors, typography, animation, or expanded width;
- no broad CSS/React rewrite;
- no replacement of the current reducer solely for style or architecture preference;
- no new user-facing technical wording;
- no changing the existing normal recording and completion experience;
- no result-card redesign unless required to fix a proven functional bug, and then only the smallest possible change.

Architecture extraction is allowed only behind the UI: production state/controller logic may be extracted for testability, but rendered appearance and stable interactions must remain materially unchanged.

---

## Required Production Mapping

| Internal outcome | Existing float behavior | Result card |
|---|---|---|
| successful injection | “完成” | normally no new fallback card |
| injection_failed with usable final text | “完成” | open with exact final text |
| attempted_unverified with usable final text | “完成” | follow existing safety policy; open card when delivery cannot be trusted, never show recognition failure |
| no_editable_target with usable final text | “完成” or existing neutral completion behavior | open with exact final text |
| AI degraded but usable pre-AI text | “完成” | only according to normal delivery result |
| no usable ASR text | existing error presentation, with concise retry wording if minimal mapping supports it | no empty card |
| backend interrupted during active session before usable text | existing error presentation | no empty card |
| idle backend recovery | no visible yellow message | none |

Do not create an `input_failed` visible float state.

---

## TDD Requirements

Add failing production-path tests before changing implementation:

1. usable final text + `injection_failed` currently enters an error state or loses the text;
2. corrected behavior emits exactly one terminal, maps float to existing DONE, and opens existing result card;
3. result-card late-load replays exact pending text after injection failure;
4. stale-session injection failure cannot overwrite the current result card;
5. no source path maps `injection_failed` with usable text to `sayitOnError`;
6. normal successful recording/processing/completion snapshot or behavior tests remain unchanged;
7. float DOM/style contract remains unchanged except for explicitly approved event wiring;
8. idle backend recovery produces no visible hint.

Tests must execute the same production controller/handler used by `main.js`. Source grep alone is insufficient.

---

## Acceptance Gates

- Injection failure with usable text shows “完成”.
- Existing result card opens with the exact final text.
- Copy action works through the existing trusted IPC path.
- No automatic clipboard mutation is added.
- No duplicate injection retry is introduced.
- No “识别失败” is displayed for injection failure.
- No new `input_failed` visible state is added.
- Stable float appearance and normal behavior remain materially unchanged.
- Yellow backend recovery text is suppressed for idle recovery.
- Exactly one terminal outcome controls the session.
- All existing result-card race, stale-session, clipboard-safety, and normal float lifecycle tests pass.

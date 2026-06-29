# Round 9.5 Addendum — BDD/TDD for ASR Accuracy and Clear User Feedback

> Date: 2026-06-29
> User-reported production symptoms:
>
> 1. Recognition output is very inaccurate / mostly wrong characters.
> 2. Float ends by displaying “识别失败”.
> 3. New yellow technical messages such as backend recovery appear and make the UI confusing.
> 4. The repair must use BDD + TDD, not another implementation-first patch.

This addendum is mandatory and must be completed together with `.ai/ROUND9_5_TEST_INTEGRITY_RUNTIME_BOUNDARY_TASK.md`.

---

## Product Goal

For one physical RAlt recording cycle, SayIt must provide one understandable outcome:

- usable text is inserted, or
- no usable speech was obtained and the user receives one concise retry message.

The float must never expose internal recovery jargon, contradict itself, or label an injection/backend/AI problem as “识别失败”.

Accuracy is measured separately at four stages:

1. provider raw ASR candidate;
2. local hotword/learned-rule result;
3. AI-organized result;
4. final selected/injected text.

No stage may silently destroy a better preceding result.

---

# BDD Specifications

Create committed feature specifications under `features/` (or another clearly named test-spec directory). Use real `.feature` files when the existing environment supports them; otherwise keep the Gherkin files as executable-spec sources and map every scenario to an explicitly named pytest/Node test.

## Feature 1 — Canonical final recognition

```gherkin
Feature: Choose a reliable final transcription

  Scenario: Streaming partial text is not the canonical final result
    Given streaming ASR produced a non-empty but incorrect-looking final candidate
    And batch ASR is available within the remaining deadline
    When recording finalization runs
    Then batch ASR is executed
    And the batch result is selected as the canonical raw transcription
    And streaming remains a UI-progress source only

  Scenario: Batch ASR fails but streaming candidate is usable
    Given streaming produced a final candidate
    And batch ASR fails within the global deadline
    When the streaming candidate passes the strict fallback quality gate
    Then SayIt uses the streaming candidate
    And records selected_source as streaming_fallback
    And does not display recognition failure

  Scenario: Both final candidates are unusable
    Given batch ASR failed or returned empty text
    And the streaming candidate fails the fallback quality gate
    When the session terminalizes
    Then no text is injected
    And exactly one terminal event has reason no_usable_asr_result
    And the float displays one concise retry message
```

### Required implementation behavior

For the stabilization release, streaming may provide partial/progress text, but **batch ASR is the canonical final path whenever it is available within the deadline**. Do not accept streaming merely because its character count is long enough.

A streaming fallback gate must be a pure tested function and reject at minimum:

- empty/whitespace/punctuation-only output;
- extreme repeated-character output;
- impossible character-per-second ratios;
- overwhelmingly wrong-script output for configured Chinese mode;
- control characters or obvious protocol/error fragments.

Do not claim the gate proves semantic correctness. Its purpose is to prevent obviously unusable fallback text.

---

## Feature 2 — Learned rules cannot corrupt a sentence

```gherkin
Feature: Safe silent-learning correction

  Scenario: A learned rule would replace many occurrences
    Given a raw ASR sentence
    And active learned rules would modify multiple unrelated positions
    When local correction is evaluated
    Then the risky rule application is rejected
    And the raw ASR sentence is preserved

  Scenario: Correction changes too much of the sentence
    Given local correction changes more than the configured safe edit ratio
    When the safety gate evaluates the candidate
    Then SayIt falls back to the raw ASR text
    And records local_correction_rejected without logging user text

  Scenario: One high-confidence token correction is safe
    Given one whole-token rule has sufficient confidence and distinct-session evidence
    And it changes only one bounded token
    When local correction is evaluated
    Then the corrected candidate may be accepted
```

### Required implementation behavior

Do not delete or rewrite the user's real rule database.

Introduce a conservative pure safety gate around rule application. At minimum:

- match on token/word boundaries where applicable, not unrestricted global substring replacement;
- reject conflicting rules for the same pattern;
- cap accepted replacements per session;
- cap total edit ratio;
- require stronger confidence and distinct-session evidence than the current broad threshold;
- preserve raw ASR when uncertain.

Until these conditions are met, learned rules operate in **shadow mode**: evaluate and record redacted metrics, but do not change final text.

The default for the stabilization branch must favor preserving provider text over applying a risky learned correction.

---

## Feature 3 — AI organization cannot destroy a better result

```gherkin
Feature: Conservative AI organization

  Scenario: AI returns empty text
    Given usable locally refined text exists
    When AI returns empty text
    Then the locally refined text remains final
    And the session succeeds

  Scenario: AI changes an implausibly large portion of text
    Given usable locally refined text exists
    When AI output exceeds the safe edit-ratio or script-consistency gate
    Then SayIt rejects the AI candidate
    And uses locally refined text
    And does not display recognition failure

  Scenario: AI provider times out
    Given raw or locally refined text is usable
    When AI times out
    Then SayIt inserts the best pre-AI text
    And the float completes normally
    And no yellow technical warning is shown
```

Fix the current successful AI branch so it does not mark `ai_degraded=True`.

---

## Feature 4 — Correct user-facing outcome

```gherkin
Feature: Float displays the true outcome

  Scenario: ASR produced usable text and AI degraded
    Given usable ASR text exists
    And AI failed or timed out
    When the pipeline finishes
    Then the float displays completion
    And it does not display recognition failure

  Scenario: Injection failed after successful recognition
    Given usable final text exists
    And target injection failed
    When the session terminalizes
    Then the outcome is injection_failed
    And the float does not label it as recognition failure
    And the text remains recoverable through the existing safe result/history path

  Scenario: No speech could be recognized
    Given no usable ASR candidate exists
    When the session terminalizes
    Then the float displays “没听清，请重试” or another approved concise equivalent
    And it displays the message once

  Scenario: Backend process crashes during an active session
    Given a recording session is active
    When the backend exits abnormally
    Then the active session receives exactly one terminal outcome service_interrupted
    And the float displays “服务中断，请重试”
    And it does not display recognition failure

  Scenario: Backend restarts successfully while idle
    Given no recording session is active
    When the backend automatically restarts successfully
    Then recovery is logged internally
    And the float shows no yellow backend recovery message
```

### Required UI behavior

Replace generic `sayitOnError()` handling with typed outcome/reason handling.

The float must distinguish at least:

- `no_usable_asr_result` → concise retry message;
- `injection_failed` → concise input failure/recovery behavior;
- `service_interrupted` → concise service interruption message;
- successful text with AI degradation → normal completion;
- no target → existing result-card path, not recognition failure.

Remove these technical messages from normal float presentation:

- “后台异常，SayIt 正在恢复”;
- “后台已恢复”;
- provider/cascade/internal recovery wording.

Backend automatic recovery may remain, but successful idle recovery must be silent. Only unrecoverable failure or interruption of an active session should produce a user-facing message.

Do not use yellow technical text as a catch-all status channel.

---

## Feature 5 — One coherent terminal result

```gherkin
Feature: One session has one terminal truth

  Scenario Outline: Every pipeline outcome maps to one terminal and one float state
    Given a session reaches <reason>
    When backend events are delivered
    Then exactly one pipeline_terminal event exists
    And the float enters <ui_state>
    And no contradictory later event changes it

    Examples:
      | reason                  | ui_state              |
      | success                 | completed             |
      | no_usable_asr_result    | retry_recognition      |
      | injection_failed        | input_failed          |
      | no_editable_target      | result_card            |
      | service_interrupted     | retry_service          |
      | ai_degraded_with_text   | completed             |
```

Legacy `pipeline_done`, generic `error`, backend recovery events, and watchdog timeout must not independently overwrite the canonical terminal outcome.

---

# TDD Execution Order

## Step 1 — Red tests only

Before modifying production behavior, add tests that fail on current HEAD for the exact reasons below:

1. Batch ASR is not always executed when streaming returns sufficiently long wrong text.
2. Current learned-rule engine can globally replace repeated substrings and exceed the safe edit ratio.
3. AI failure with usable ASR can still be routed into generic error presentation.
4. `float.html` maps every generic error to “识别失败”.
5. Backend supervisor pushes yellow recovery text on successful restart.
6. Backend crash during an active session does not create a typed `service_interrupted` terminal.
7. A successful idle backend restart changes visible float state.
8. Multiple legacy events can overwrite the canonical terminal UI.

Each test must execute a production function/controller, not grep source text.

## Step 2 — Minimal production changes

Implement only enough code to make each scenario pass, in small checkpoint commits:

- checkpoint A: stage tracing and canonical batch-final selection;
- checkpoint B: local-rule shadow/safety gate;
- checkpoint C: AI candidate safety/fallback;
- checkpoint D: typed terminal outcome mapping;
- checkpoint E: silent idle backend recovery and active-session interruption handling;
- checkpoint F: full regression gates and documentation.

## Step 3 — Refactor under green tests

After the scenarios pass:

- centralize ASR candidate selection;
- centralize post-processing candidate safety;
- centralize terminal-to-UI mapping;
- remove duplicated generic error paths;
- keep all behavior tests green.

---

# Diagnostic Requirements

Add redacted per-session stage metrics without storing/logging user text:

- engine/source selected;
- raw length and SHA-256 prefix or non-reversible session hash;
- local-correction edit ratio and replacement count;
- AI edit ratio and accepted/rejected reason;
- final length;
- terminal reason;
- backend restart occurred yes/no;
- process/thread cleanup status.

Do not log raw transcription, corrected text, clipboard content, API keys, dictionary contents, or history text.

Tests may use synthetic fixed strings and assert exact stage outputs.

---

# Acceptance Gates

Round 9.5 cannot become `BLOCKED_USER_VALIDATION` until all are true:

1. BDD scenarios are committed and each maps to an executable test.
2. Batch ASR is the canonical final source when available.
3. Streaming wrong-but-long text cannot bypass final verification.
4. Learned rules cannot globally corrupt a sentence; uncertain rules are shadow-only.
5. AI failure/timeout with usable text completes successfully.
6. “识别失败” is shown only for a real no-usable-ASR outcome, using approved concise wording.
7. Injection/backend/AI failures are not mislabeled as recognition failure.
8. Successful idle backend restart is silent—no yellow “后台已恢复”.
9. Active-session backend crash produces exactly one `service_interrupted` terminal.
10. One canonical terminal controls the float; no later legacy event contradicts it.
11. Existing Round 9.5 killable-boundary, modifier, diagnostics, and exact-terminal gates also pass.
12. Full test report contains exact collected/pass/skip/fail counts and command output.

---

# Physical Validation Reserved for the User

After code review acceptance, the user should need only a short check:

- dictate three fixed Chinese sentences in Notepad;
- verify no widespread wrong characters;
- verify no final false “识别失败”;
- verify no yellow backend recovery text;
- verify RAlt start/stop and clean injection.

Do not ask the user to diagnose logs or repeatedly reproduce crashes before automated gates pass.

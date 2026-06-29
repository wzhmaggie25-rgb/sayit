Feature: Silent learning adds corrected terms to ASR hotwords
  SayIt should learn only clear user-corrected terms from verified injections.
  It must not learn whole sentences, ambiguous edits, or legacy replacement rules.

  # Conservative v1 (Round 9.5A): silent learning never guesses a Chinese word
  # boundary from the before/after text alone. A single changed Chinese
  # character is therefore NOT auto-learned, because its true word boundary
  # cannot be proven without an explicit user edit/selection signal. Learning is
  # limited to clean full replacements: a complete 2–8 character Chinese term, an
  # English/mixed product term, or a single unambiguous replacement span.

  Background:
    Given silent learning is enabled
    And the injection result is "verified_success"
    And the monitored target is the same verified target

  Scenario: Full Chinese term correction is learned
    Given SayIt injected "我看到了光明"
    When the user changes the inserted span to "我看到了黑暗"
    Then the corrected term "黑暗" is added once to the personal dictionary
    And ASR hotwords are refreshed with "黑暗"
    And no global replacement rule is created or applied

  Scenario: Single Chinese character correction is NOT learned in conservative v1
    Given SayIt injected "我今天去了民天广场"
    When the user changes the inserted span to "我今天去了明天广场"
    Then no dictionary term is added
    And ASR hotwords are not refreshed
    # Rationale: only the single character 民→明 changed. The intended word
    # "明天" cannot be proven from the final text without guessing the
    # neighboring character, so conservative v1 deliberately learns nothing.

  Scenario: Chinese phonetic error corrected to an English product name
    Given SayIt injected "我在用微差调试"
    When the user changes the inserted span to "我在用WeChat调试"
    Then the corrected term "WeChat" is added once to the personal dictionary
    And ASR hotwords are refreshed with "WeChat"
    And the corrected English case is preserved

  Scenario: Existing dictionary term is idempotent
    Given the personal dictionary already contains "WeChat"
    And SayIt injected "打开微差"
    When the user changes the inserted span to "打开WeChat"
    Then the personal dictionary still contains one "WeChat"
    And ASR hotword synchronization remains stable

  Scenario: Sentence rewrite is ignored
    Given SayIt injected "今天下午开会讨论预算"
    When the user changes the inserted span to "预算会我们改到明天下午讨论"
    Then no dictionary term is added
    And ASR hotwords are not refreshed

  Scenario: Multiple corrections in one edit are ignored
    Given SayIt injected "我用微差和豆抱"
    When the user changes the inserted span to "我用WeChat和豆包"
    Then no dictionary term is added
    And ASR hotwords are not refreshed

  Scenario: Insertion or deletion is ignored
    Given SayIt injected "打开豆包"
    When the user changes the inserted span to "请打开豆包"
    Then no dictionary term is added
    And ASR hotwords are not refreshed

  Scenario: Punctuation or formatting-only change is ignored
    Given SayIt injected "打开豆包"
    When the user changes the inserted span to "打开豆包。"
    Then no dictionary term is added
    And ASR hotwords are not refreshed

  Scenario: Stale or unverified target is ignored
    Given the injection result is "attempted_unverified"
    When the user changes the inserted span to "打开WeChat"
    Then no dictionary term is added
    And ASR hotwords are not refreshed

  Scenario: Legacy conflicting or chained rules do not change final ASR text
    Given legacy correction rules include "微差" to "WeChat"
    And legacy correction rules include "WeChat" to "微信"
    When ASR produces "打开微差"
    Then the final ASR text remains "打开微差"
    And no legacy replacement is promoted into ASR hotwords

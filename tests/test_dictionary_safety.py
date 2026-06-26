"""Strict auto-dictionary safety tests.

Covers the hardened policy in `domain.correction.extract_dictionary_terms`:

  - Only a SINGLE clean 1↔1 token replacement is accepted.
  - The replacement must shape like a proper-noun/term token (no whitespace,
    no Chinese or English sentence punctuation, length-bounded).
  - Pattern and replacement must share script family — no cross-script swaps.
  - At most ONE candidate is returned per edit.
  - When in doubt, the function returns [] (silently skip auto-add).

These cases enumerate the failure modes the user reported: whole sentences,
common phrases, direction-reversed edits, and punctuation-bearing
fragments must never reach the personal dictionary.
"""
from __future__ import annotations

import unittest

from domain.correction import extract_dictionary_terms


class DictionarySafetyTests(unittest.TestCase):

    # ── 1. Valid single-token replacements are accepted ────────────────

    def test_ascii_typo_correction_is_learned(self):
        # "wrld" → "world" — single token replacement, ASCII shape, both
        # sides share the ASCII script family. The smallest legitimate case.
        terms = extract_dictionary_terms("hello wrld", "hello world")
        self.assertEqual(terms, ["world"])

    def test_chinese_proper_noun_single_token_is_learned(self):
        # ASR mis-recognised the brand "言豆包" as "豆包包"; user fixes it.
        # Same script family, single 1↔1 replacement. Allowed.
        terms = extract_dictionary_terms("我喜欢 豆包包", "我喜欢 言豆包")
        self.assertEqual(terms, ["言豆包"])

    def test_at_most_one_term_per_edit(self):
        # Two separate single-token replacements in one edit. Policy says
        # at most one — and since the diff is not a SINGLE replace opcode,
        # extract returns []. (Strict interpretation of rule 1.)
        terms = extract_dictionary_terms(
            "hello wrld and goodby moon",
            "hello world and goodbye moon",
        )
        self.assertEqual(terms, [])

    # ── 2. Whole-sentence and phrase edits are rejected ───────────────

    def test_whole_chinese_sentence_replacement_is_rejected(self):
        # The user-reported failure: a whole sentence becomes a dictionary
        # entry. Any sentence-punctuation character is a hard reject.
        terms = extract_dictionary_terms(
            "今天天气很好",
            "今天天气很好，我们去公园吧。",
        )
        self.assertEqual(terms, [])

    def test_replacement_with_chinese_period_rejected(self):
        terms = extract_dictionary_terms("foo", "你好。")
        self.assertEqual(terms, [])

    def test_replacement_with_comma_rejected(self):
        terms = extract_dictionary_terms("a", "b, c")
        self.assertEqual(terms, [])

    def test_replacement_with_space_rejected(self):
        # Whitespace inside the replacement means it is not a single token.
        terms = extract_dictionary_terms("brand", "Hello World")
        self.assertEqual(terms, [])

    def test_replacement_with_newline_rejected(self):
        terms = extract_dictionary_terms("x", "abc\ndef")
        self.assertEqual(terms, [])

    def test_multi_token_phrase_replacement_rejected(self):
        # Multi-token diff (j2 - j1 > 1). Policy requires exactly 1↔1.
        terms = extract_dictionary_terms("hello", "hello there friend")
        self.assertEqual(terms, [])

    def test_long_chinese_phrase_rejected_by_length(self):
        # Even with no punctuation, anything longer than the CJK cap is
        # almost certainly a phrase, not a term. Hard length gate.
        terms = extract_dictionary_terms(
            "短",
            "这是一段很长的中文文字应当被拒绝",
        )
        self.assertEqual(terms, [])

    # ── 3. Reversed-direction and empty-pattern edits are rejected ────

    def test_pattern_must_be_a_real_token(self):
        # Empty original means the diff is insert-shaped, not replace.
        # We must NOT auto-learn pure insertions — direction is ambiguous.
        terms = extract_dictionary_terms("", "Sayit")
        self.assertEqual(terms, [])

    def test_replacement_equals_pattern_rejected(self):
        terms = extract_dictionary_terms("Sayit", "Sayit")
        self.assertEqual(terms, [])

    def test_cross_script_swap_rejected(self):
        # Pattern is CJK, replacement is ASCII — almost certainly an
        # unrelated paste, not a correction of the same mis-recognized word.
        terms = extract_dictionary_terms("微信", "WeChat")
        self.assertEqual(terms, [])
        terms = extract_dictionary_terms("WeChat", "微信")
        self.assertEqual(terms, [])

    def test_original_error_token_is_never_returned(self):
        # The error token "wrld" must NEVER appear in the returned list —
        # only the corrected side does.
        terms = extract_dictionary_terms("hello wrld", "hello world")
        self.assertNotIn("wrld", terms)

    # ── 4. Insert / delete / mixed edits are rejected ─────────────────

    def test_user_appends_new_sentence_no_term_added(self):
        # User continues writing after the injection — pure insertion at
        # tail. Diff is not a 1↔1 replace.
        terms = extract_dictionary_terms(
            "hello world",
            "hello world. Then I added more text.",
        )
        self.assertEqual(terms, [])

    def test_user_deletes_chunk_no_term_added(self):
        terms = extract_dictionary_terms(
            "this is a long sentence the user typed",
            "this is a long sentence",
        )
        self.assertEqual(terms, [])

    def test_numeric_token_rejected(self):
        terms = extract_dictionary_terms("123", "456")
        self.assertEqual(terms, [])

    def test_terminal_command_path_rejected(self):
        # PROTECTED_PATTERN guards paths / shell commands so we never
        # promote them into the ASR hotword set.
        terms = extract_dictionary_terms("foo", "C:\\Windows\\System32")
        self.assertEqual(terms, [])

    def test_unknown_shape_rejected(self):
        # Symbol-only replacement does not match any known term shape.
        terms = extract_dictionary_terms("foo", "###")
        self.assertEqual(terms, [])

    # ── 5. Uncertain inputs return empty ──────────────────────────────

    def test_empty_inputs_return_empty(self):
        self.assertEqual(extract_dictionary_terms("", ""), [])
        self.assertEqual(extract_dictionary_terms("foo", ""), [])
        self.assertEqual(extract_dictionary_terms("", "foo"), [])
        self.assertEqual(extract_dictionary_terms(None, "foo"), [])
        self.assertEqual(extract_dictionary_terms("foo", None), [])


class CorrectionRulesStillLearnIndependentlyTests(unittest.TestCase):
    """Correction rule learning must not be gated by the dict policy.

    The harder dictionary policy must NOT silently disable rule learning —
    they are independent surfaces. A "wrld → world" edit should still
    create a correction rule even though, depending on the diff shape, it
    may or may not also produce a dictionary candidate.
    """

    def test_rule_engine_still_learns_typo(self):
        from domain.correction import learn_from_edit
        existing: list[dict] = []
        new_rules, count = learn_from_edit(
            original_text="hello wrld",
            edited_text="hello world",
            existing_rules=existing,
        )
        self.assertGreaterEqual(count, 1)
        patterns = [r["pattern"] for r in new_rules]
        self.assertIn("wrld", patterns)


if __name__ == "__main__":
    unittest.main()

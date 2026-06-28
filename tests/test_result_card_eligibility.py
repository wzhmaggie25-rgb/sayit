"""Phase 3 tests: strict result card eligibility.

Verifies the eligibility pure function from the production module:

show_large_result_card =
  state == no_editable_target
  AND injection_dispatched == false
  AND inserted_verified == false
  AND target_is_sayit_window == false

Rules:
- verified_success → never show large card
- attempted_unverified → show lightweight hint only (no large card)
- injection_failed with injection_dispatched=True → no large card
- no_editable_target with injection_dispatched=False → show large card
- no_editable_target with injection_dispatched=True → no large card
- SayIt own windows (main, float, result-card) → always excluded
"""

from __future__ import annotations

import unittest

from application.result_card_eligibility import should_show_large_result_card
from infrastructure.injector import InjectionResult


class ResultCardEligibilityTests(unittest.TestCase):
    """Unit tests for result card eligibility pure function."""

    def test_verified_success_no_card(self):
        """verified_success must never show large card."""
        self.assertFalse(
            should_show_large_result_card("verified_success"))

    def test_attempted_unverified_no_card(self):
        """attempted_unverified must never show large card
        (injection was dispatched)."""
        # attempted_unverified always has injection_dispatched=True
        self.assertFalse(
            should_show_large_result_card("attempted_unverified",
                                           injection_dispatched=True))

    def test_injection_failed_with_dispatch_no_card(self):
        """injection_failed with injection_dispatched=True must not show card."""
        self.assertFalse(
            should_show_large_result_card("injection_failed",
                                           injection_dispatched=True))

    def test_no_editable_target_no_dispatch_shows_card(self):
        """no_editable_target with no dispatch may show card."""
        self.assertTrue(
            should_show_large_result_card("no_editable_target",
                                           injection_dispatched=False))

    def test_no_editable_target_with_dispatch_no_card(self):
        """no_editable_target with dispatch True must not show card."""
        self.assertFalse(
            should_show_large_result_card("no_editable_target",
                                           injection_dispatched=True))

    def test_recognition_failed_no_card(self):
        """recognition_failed never shows card (not a terminal state)."""
        self.assertFalse(
            should_show_large_result_card("recognition_failed"))

    def test_verified_insertion_no_card(self):
        """inserted_verified=True must block large card regardless of state."""
        for state in ("no_editable_target", "attempted_unverified",
                       "injection_failed", "verified_success"):
            self.assertFalse(
                should_show_large_result_card(state,
                                               inserted_verified=True),
                f"state={state} with inserted_verified=True")

    def test_sayit_own_window_excluded(self):
        """SayIt own windows must never show large card."""
        for state in ("no_editable_target", "attempted_unverified",
                       "injection_failed"):
            self.assertFalse(
                should_show_large_result_card(state,
                                               target_is_sayit_window=True),
                f"state={state} with target_is_sayit_window=True")

    def test_no_editable_target_on_sayit_no_card(self):
        """Even no_editable_target on SayIt window must not show card."""
        self.assertFalse(
            should_show_large_result_card(
                "no_editable_target",
                target_is_sayit_window=True))

    def test_exact_eligibility_formula(self):
        """Only exact formula match shows card."""
        # Must match: state==no_editable_target AND not injection_dispatched
        # AND not inserted_verified AND not target_is_sayit_window
        self.assertTrue(
            should_show_large_result_card(
                state="no_editable_target",
                injection_dispatched=False,
                inserted_verified=False,
                target_is_sayit_window=False))
        # Tweak each parameter: all must block
        self.assertFalse(
            should_show_large_result_card(
                state="verified_success",
                injection_dispatched=False,
                inserted_verified=False,
                target_is_sayit_window=False))
        self.assertFalse(
            should_show_large_result_card(
                state="no_editable_target",
                injection_dispatched=True,
                inserted_verified=False,
                target_is_sayit_window=False))
        self.assertFalse(
            should_show_large_result_card(
                state="no_editable_target",
                injection_dispatched=False,
                inserted_verified=True,
                target_is_sayit_window=False))
        self.assertFalse(
            should_show_large_result_card(
                state="no_editable_target",
                injection_dispatched=False,
                inserted_verified=False,
                target_is_sayit_window=True))

    def test_injection_result_has_injection_dispatched_field(self):
        """InjectionResult dataclass must have the injection_dispatched field."""
        result = InjectionResult()
        self.assertTrue(hasattr(result, "injection_dispatched"))
        self.assertFalse(result.injection_dispatched)

    def test_ok_result_sets_injection_dispatched_true(self):
        """_ok() returns InjectionResult with injection_dispatched=True."""
        # Simulate what _ok() does
        result = InjectionResult(
            ok=True, state="verified_success",
            verified=True, method="clipboard",
            injection_dispatched=True)
        self.assertTrue(result.injection_dispatched)

    def test_attempted_unverified_sets_injection_dispatched_true(self):
        """attempted_unverified results have injection_dispatched=True."""
        result = InjectionResult(
            ok=True, state="attempted_unverified",
            verified=False, method="win32_selection",
            injection_dispatched=True)
        self.assertTrue(result.injection_dispatched)

    def test_no_editable_target_default_dispatched_false(self):
        """no_editable_target result has injection_dispatched=False by default."""
        result = InjectionResult(
            ok=False, state="no_editable_target",
            clipboard_preserved=True)
        self.assertFalse(result.injection_dispatched)


if __name__ == "__main__":
    unittest.main()
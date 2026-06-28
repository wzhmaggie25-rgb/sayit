"""Result card eligibility — production gate for showing large result cards.

Per product requirements:

    show_large_result_card = state == no_editable_target
                             AND injection_dispatched == false
                             AND inserted_verified == false
                             AND target_is_sayit_window == false

Rules:
- verified_success → never show large card
- attempted_unverified → lightweight hint only (injection was dispatched)
- injection_failed with injection_dispatched=True → no large card
- no_editable_target with injection_dispatched=False → show large card
- no_editable_target with injection_dispatched=True → no large card
- SayIt own windows (main, float, result-card) → always excluded
"""
from __future__ import annotations


def should_show_large_result_card(
    state: str,
    injection_dispatched: bool = False,
    inserted_verified: bool = False,
    target_is_sayit_window: bool = False,
) -> bool:
    """Determine if a large result card should be shown.

    Args:
        state: One of "verified_success", "attempted_unverified",
               "no_editable_target", "injection_failed", "recognition_failed".
        injection_dispatched: True if any inject action (paste/sendinput) was sent.
        inserted_verified: True if the text was verified in the target.
        target_is_sayit_window: True if the target is a SayIt-owned window.

    Returns:
        True if the large result card should be shown.
    """
    if target_is_sayit_window:
        return False
    if inserted_verified:
        return False
    if state == "no_editable_target" and not injection_dispatched:
        return True
    return False
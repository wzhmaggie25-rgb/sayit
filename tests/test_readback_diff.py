"""Phase 3: true readback via pre/post diff — reject substring false positives.

Round 7 spec:
  - reliable unchanged (post == pre)          → injection_failed
  - genuine insertion (post = pre + expected) → verified_success
  - ambiguous / no readback                   → attempted_unverified

The old implementation used `expected in post` which produces false positives
when expected was already present in pre_text, or when post is empty.
"""
from __future__ import annotations
import unittest
from unittest.mock import patch, MagicMock

from infrastructure.injector import Injector, InjectionResult, InjectionTarget
from infrastructure import clipboard_snapshot as snapmod


def _empty_snapshot():
    return snapmod.ClipboardSnapshot(kind="EMPTY")


class VerifyTargetTextDiffTests(unittest.TestCase):
    """Direct tests of _verify_target_text — the core readback diff logic."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")

    # ── pre/post identical → "unchanged" ──

    def test_pre_post_identical_returns_unchanged(self):
        """pre == post → unchanged even if expected is a substring."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "hello world")):
            verdict = self.inj._verify_target_text(42, "hello", "hello world")
        self.assertEqual(verdict, "unchanged")

    def test_pre_post_identical_with_new_expected_returns_unchanged(self):
        """pre == post but expected not in pre → still unchanged (nothing changed)."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "some text")):
            verdict = self.inj._verify_target_text(42, "hello", "some text")
        self.assertEqual(verdict, "unchanged")

    # ── false positive rejection ──

    def test_expected_already_in_pre_not_verified(self):
        """expected already present in pre_text must not produce verified."""
        # pre="hello world", expected="world", post="hello world" (unchanged)
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "hello world")):
            verdict = self.inj._verify_target_text(42, "world", "hello world")
        self.assertEqual(verdict, "unchanged",
                         "Already-present expected must not be 'verified'")

    def test_expected_already_in_pre_with_new_post_not_verified(self):
        """expected already in pre, post changed but not due to expected insertion."""
        # pre="hello world", expected="world", post="hello WORLD!!"
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "hello WORLD!!")):
            verdict = self.inj._verify_target_text(42, "world", "hello world")
        self.assertEqual(verdict, "no_readback",
                         "Cannot verify when pre→post change is unrelated to expected")

    def test_empty_post_not_verified(self):
        """Empty post must not produce verified even if '' in expected is truthy."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "")):
            verdict = self.inj._verify_target_text(42, "hello", "some pre text")
        self.assertEqual(verdict, "no_readback",
                         "Empty post after non-empty pre must not be verified")

    def test_empty_post_no_pre_not_verified(self):
        """Empty post when pre_text is None must not produce verified."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "")):
            verdict = self.inj._verify_target_text(42, "hello", None)
        self.assertEqual(verdict, "no_readback")

    def test_partial_expected_not_verified(self):
        """Partial substring must not match."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "hell")):
            verdict = self.inj._verify_target_text(42, "hello", "pre text")
        self.assertEqual(verdict, "no_readback")

    # ── genuine insertion via diff ──

    def test_proper_pre_to_post_diff_at_end_verified(self):
        """post = pre + expected → verified."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "foobar")):
            verdict = self.inj._verify_target_text(42, "bar", "foo")
        self.assertEqual(verdict, "verified")

    def test_proper_pre_to_post_diff_in_middle_verified(self):
        """expected inserted in middle → verified."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "fooXYZbar")):
            verdict = self.inj._verify_target_text(42, "XYZ", "foobar")
        self.assertEqual(verdict, "verified")

    def test_proper_pre_to_post_diff_at_start_verified(self):
        """expected inserted at start → verified."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "HELLOworld")):
            verdict = self.inj._verify_target_text(42, "HELLO", "world")
        self.assertEqual(verdict, "verified")

    def test_expected_twice_in_pre_inserted_again_verified(self):
        """expected appears once in pre, inserted again → count increases → verified."""
        # pre="ab", expected="a", post="aab" — "a" was inserted before "ab"
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "aab")):
            verdict = self.inj._verify_target_text(42, "a", "ab")
        self.assertEqual(verdict, "verified")

    # ── snapshot failure ──

    def test_no_readback_returns_no_readback(self):
        """Snapshot failure → no_readback."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(False, "")):
            verdict = self.inj._verify_target_text(42, "hello", "pre")
        self.assertEqual(verdict, "no_readback")

    # ── no pre_text (weak match) ──

    def test_no_pre_text_with_match_verified(self):
        """No pre snapshot, expected in post → weak verified."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "hello world")):
            verdict = self.inj._verify_target_text(42, "hello", None)
        self.assertEqual(verdict, "verified")

    def test_no_pre_text_no_match_no_readback(self):
        """No pre snapshot, expected NOT in post → no_readback."""
        with patch.object(self.inj, "_snapshot_target_text",
                          return_value=(True, "goodbye")):
            verdict = self.inj._verify_target_text(42, "hello", None)
        self.assertEqual(verdict, "no_readback")


class VerifyUiaReadbackDiffTests(unittest.TestCase):
    """_verify_uia_readback is removed — placeholder to avoid reimport."""

    def test_verify_uia_readback_removed(self):
        """_verify_uia_readback was deleted — confirm it doesn't exist."""
        self.assertFalse(
            hasattr(Injector(injection_mode="auto"), "_verify_uia_readback"))


class PasteUnchangedMapsToInjectionFailed(unittest.TestCase):
    """Phase 3 spec: reliable unchanged → injection_failed (not attempted_unverified)."""

    def setUp(self):
        self.inj = Injector(injection_mode="auto")
        self.target = InjectionTarget(
            hwnd=4242, pid=1, proc="notepad.exe", cls="Edit", title="x")

    def _common_patches(self):
        return [
            patch.object(self.inj, "_lock", MagicMock()),
            patch.object(self.inj, "_focus_window", return_value=True),
            patch.object(self.inj, "_foreground_info",
                         return_value=(4242, "Edit", 1, "notepad.exe")),
            patch.object(self.inj, "_get_context_for_strategy", return_value={}),
            patch.object(self.inj, "_strategy_for_context",
                         return_value="clipboard"),
            patch.object(self.inj, "_is_terminal_target", return_value=False),
            patch.object(self.inj, "_inject_uia", return_value=False),
            patch("infrastructure.clipboard_snapshot.read_snapshot",
                  return_value=_empty_snapshot()),
            patch("infrastructure.clipboard_snapshot.restore_snapshot",
                  return_value=True),
            patch("ctypes.windll.user32.keybd_event"),
            patch("time.sleep"),
        ]

    def test_paste_unchanged_is_injection_failed(self):
        """pre == post after paste → injection_failed (not attempted_unverified)."""
        direct_mock = MagicMock(return_value=True)
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, "abc"), (True, "abc")]),
            patch.object(self.inj, "_direct_input", direct_mock),
        ]
        with patches[0]:
            with patches[1]:
                with patches[2]:
                    with patches[3]:
                        with patches[4]:
                            with patches[5]:
                                with patches[6]:
                                    with patches[7]:
                                        with patches[8]:
                                            with patches[9]:
                                                with patches[10]:
                                                    with patches[11]:
                                                        with patches[12]:
                                                            result = self.inj.inject(
                                                                "xyz", target=self.target)
        self.assertEqual(result.state, "injection_failed")
        self.assertEqual(result.reason, "paste_target_unchanged")
        # Must NOT fall through to SendInput
        direct_mock.assert_not_called()

    def test_paste_no_readback_still_attempted_unverified(self):
        """No/ambiguous readback after paste → attempted_unverified (not changed)."""
        patches = self._common_patches() + [
            patch.object(self.inj, "_snapshot_target_text",
                         side_effect=[(True, ""), (False, "")]),
        ]
        with patches[0]:
            with patches[1]:
                with patches[2]:
                    with patches[3]:
                        with patches[4]:
                            with patches[5]:
                                with patches[6]:
                                    with patches[7]:
                                        with patches[8]:
                                            with patches[9]:
                                                with patches[10]:
                                                    with patches[11]:
                                                        result = self.inj.inject(
                                                            "xyz", target=self.target)
        self.assertEqual(result.state, "attempted_unverified")
        self.assertEqual(result.reason, "paste_no_readback")


if __name__ == "__main__":
    unittest.main()
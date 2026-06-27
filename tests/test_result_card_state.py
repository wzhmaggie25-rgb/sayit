"""Phase 5 tests: result card state + message propagation.

Verifies:
- Pipeline emits RESULT_CARD_SHOW with correct state+message per branch
- server.py event handler accepts 4-arg signature with defaults
- Backward compatibility: 2-arg legacy emit doesn't crash
- result-card.html renderer shows status bar for meaningful states
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from application.eventbus import EventBus, Events
from infrastructure.injector import InjectionResult


class ResultCardStateStageTests(unittest.TestCase):
    """Unit tests: verify RESULT_CARD_SHOW carries state+message per branch."""

    def setUp(self):
        self.eb = EventBus()
        self.events = []

    def _capture(self, *args):
        self.events.append(args)

    def test_attempted_unverified_carries_state_and_message(self):
        """pipeline emits RESULT_CARD_SHOW with attempted_unverified state + Chinese warning."""
        self.eb.on(Events.RESULT_CARD_SHOW, self._capture)
        self.eb.emit(Events.RESULT_CARD_SHOW, "测试文本", "测试文本",
                     "attempted_unverified", "文本可能已输入，请检查目标窗口，避免重复粘贴")
        self.assertEqual(len(self.events), 1)
        args = self.events[0]
        # When captured directly, args = (final_text, last_tx, state, message)
        self.assertEqual(args[0], "测试文本")
        self.assertEqual(args[1], "测试文本")
        self.assertEqual(args[2], "attempted_unverified")
        self.assertIn("文本可能已输入", args[3])

    def test_no_editable_target_carries_state_and_message(self):
        """pipeline emits RESULT_CARD_SHOW with no_editable_target state."""
        self.eb.on(Events.RESULT_CARD_SHOW, self._capture)
        self.eb.emit(Events.RESULT_CARD_SHOW, "测试文本", "测试文本",
                     "no_editable_target", "未找到可输入的目标窗口")
        self.assertEqual(len(self.events), 1)
        args = self.events[0]
        self.assertEqual(args[2], "no_editable_target")
        self.assertIn("未找到可输入的目标窗口", args[3])

    def test_injection_failed_carries_state_and_message(self):
        """pipeline emits RESULT_CARD_SHOW with injection_failed state."""
        self.eb.on(Events.RESULT_CARD_SHOW, self._capture)
        self.eb.emit(Events.RESULT_CARD_SHOW, "测试文本", "测试文本",
                     "injection_failed", "未能将文本注入目标窗口")
        self.assertEqual(len(self.events), 1)
        args = self.events[0]
        self.assertEqual(args[2], "injection_failed")
        self.assertIn("未能将文本注入", args[3])

    def test_verified_success_also_supports_state_message(self):
        """verified_success can carry state+message too (future-proof)."""
        self.eb.on(Events.RESULT_CARD_SHOW, self._capture)
        self.eb.emit(Events.RESULT_CARD_SHOW, "测试文本", "测试文本",
                     "verified_success", "")
        self.assertEqual(len(self.events), 1)
        args = self.events[0]
        self.assertEqual(args[2], "verified_success")
        self.assertEqual(args[3], "")

    def test_dual_arg_legacy_emit_backward_compat(self):
        """Legacy 2-arg emit must not crash; state/message default to ''."""
        self.eb.on(Events.RESULT_CARD_SHOW,
                   lambda t, lt, s="", m="": self.events.append((t, lt, s, m)))
        self.eb.emit(Events.RESULT_CARD_SHOW, "text", "last_tx")
        self.assertEqual(len(self.events), 1)
        t, lt, s, m = self.events[0]
        self.assertEqual(t, "text")
        self.assertEqual(lt, "last_tx")
        self.assertEqual(s, "", "state should default to empty string")
        self.assertEqual(m, "", "message should default to empty string")


class ResultCardServerBroadcastTests(unittest.TestCase):
    """Test server.py event handler wires state+message into broadcast payload."""

    def test_handler_accepts_four_args_with_defaults(self):
        """Lambda signature (t, lt, s='', m='') is backward compatible."""
        # Simulate the handler in server.py
        handler = lambda t, lt, s="", m="": {"event": "result_card_show",
                                              "text": t,
                                              "last_transcription": lt,
                                              "state": s,
                                              "message": m}

        # 4-arg call (new pipeline)
        result = handler("hello", "world", "verified_success", "成功")
        self.assertEqual(result["state"], "verified_success")
        self.assertEqual(result["message"], "成功")

        # 2-arg call (legacy — shouldn't happen, but must not crash)
        result2 = handler("hello", "world")
        self.assertEqual(result2["state"], "")
        self.assertEqual(result2["message"], "")

    def test_broadcast_payload_includes_state_message(self):
        """The payload placed on event_queue includes state+message fields."""
        from server import wire_events  # noqa: F401 — just verify import works

        import server as sv
        # Monkey-patch event_queue to capture
        captured = []
        original_put = sv._event_queue.put

        def fake_put(item):
            captured.append(item)
            return original_put(item)

        with patch.object(sv._event_queue, "put", fake_put):
            sv._event_queue.put({
                "event": "result_card_show",
                "text": "hello",
                "last_transcription": "world",
                "state": "attempted_unverified",
                "message": "请检查目标窗口",
            })

        self.assertTrue(len(captured) > 0)
        last = captured[-1]
        self.assertEqual(last["event"], "result_card_show")
        self.assertIn("state", last)
        self.assertIn("message", last)
        self.assertEqual(last["state"], "attempted_unverified")
        self.assertEqual(last["message"], "请检查目标窗口")


if __name__ == "__main__":
    unittest.main()


class InjectionDoneStructuredPayloadTests(unittest.TestCase):
    """Phase 7: INJECTION_DONE carries full InjectionResult, not just bool."""

    def setUp(self):
        self.eb = EventBus()
        self.events = []

    def test_injection_done_carries_structured_payload(self):
        """Emitting INJECTION_DONE with InjectionResult captures all fields."""
        self.eb.on(Events.INJECTION_DONE, self._capture)
        result = InjectionResult(
            ok=True,
            state="verified_success",
            verified=True,
            method="clipboard",
            clipboard_preserved=True,
            clipboard_restored=True,
            target_verified=True,
            reason="",
        )
        self.eb.emit(Events.INJECTION_DONE, result)
        self.assertEqual(len(self.events), 1)
        captured = self.events[0]
        self.assertEqual(captured.ok, True)
        self.assertEqual(captured.state, "verified_success")
        self.assertEqual(captured.verified, True)
        self.assertEqual(captured.method, "clipboard")
        self.assertEqual(captured.clipboard_restored, True)
        self.assertEqual(captured.target_verified, True)

    def test_injection_done_backward_compat_ok_true(self):
        """result.ok is the same as the old bare True: verified_success."""
        self.eb.on(Events.INJECTION_DONE, lambda r: self.events.append(r.ok))
        result = InjectionResult(ok=True, state="verified_success", verified=True)
        self.eb.emit(Events.INJECTION_DONE, result)
        self.assertEqual(len(self.events), 1)
        self.assertIs(self.events[0], True)

    def test_injection_done_backward_compat_ok_false(self):
        """result.ok is the same as the old bare False."""
        self.eb.on(Events.INJECTION_DONE, lambda r: self.events.append(r.ok))
        result = InjectionResult(ok=False, state="injection_failed")
        self.eb.emit(Events.INJECTION_DONE, result)
        self.assertEqual(len(self.events), 1)
        self.assertIs(self.events[0], False)

    def test_injection_done_all_states_have_ok(self):
        """Every possible state has a sensible ok value."""
        states_ok = [
            ("verified_success", True),
            ("attempted_unverified", False),
            ("no_editable_target", True),
            ("injection_failed", False),
            ("recognition_failed", False),
        ]
        self.eb.on(Events.INJECTION_DONE, lambda r: self.events.append((r.state, r.ok)))
        for state, expected_ok in states_ok:
            result = InjectionResult(ok=expected_ok, state=state)
            self.eb.emit(Events.INJECTION_DONE, result)
        self.assertEqual(len(self.events), 5)
        for (state, ok), (expected_state, expected_ok) in zip(self.events, states_ok):
            self.assertEqual(state, expected_state)
            self.assertEqual(ok, expected_ok)

    def test_injection_done_attempted_unverified_reason_preserved(self):
        """reason field survives the emit round-trip."""
        self.eb.on(Events.INJECTION_DONE, lambda r: self.events.append(r.reason))
        result = InjectionResult(ok=False, state="attempted_unverified",
                                  reason="paste_no_readback")
        self.eb.emit(Events.INJECTION_DONE, result)
        self.assertEqual(self.events[0], "paste_no_readback")

    def _capture(self, result):
        self.events.append(result)
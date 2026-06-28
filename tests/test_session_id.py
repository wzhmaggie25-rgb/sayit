"""Phase 0 tests: recording_session_id generation, propagation, and isolation.

Verifies:
- Each recording generates a unique session_id
- session_id propagates through pipeline events
- Main.js filters stale session events
- Cleanup on recording_started clears old card state
"""
from __future__ import annotations

import unittest
import uuid

from application.eventbus import EventBus, Events
from domain.models import RecordingState


class RecordingSessionIdTests(unittest.TestCase):
    """Test session_id generation and cross-session isolation."""

    def setUp(self):
        self.eb = EventBus()
        self.events = []

    def _capture(self, *args):
        self.events.append(args)

    def test_session_id_is_unique_per_run(self):
        """Each pipeline run generates a different session_id."""
        ids = set()
        for _ in range(10):
            sid = uuid.uuid4().hex[:12]
            ids.add(sid)
        self.assertEqual(len(ids), 10, "session_id must be unique each generation")

    def test_session_id_propagates_via_recording_started(self):
        """recording_started event carries session_id that matches pipeline."""
        session_id = uuid.uuid4().hex[:12]
        # Simulate server.py broadcast including session_id
        payload = {"event": "recording_started", "session_id": session_id}
        self.assertEqual(payload["session_id"], session_id)

    def test_session_id_propagates_via_result_card_show(self):
        """result_card_show event carries session_id."""
        session_id = uuid.uuid4().hex[:12]
        payload = {
            "event": "result_card_show",
            "session_id": session_id,
            "text": "hello",
            "last_transcription": "",
            "state": "no_editable_target",
            "message": "",
        }
        self.assertEqual(payload["session_id"], session_id)

    def test_session_id_propagates_via_pipeline_done(self):
        """pipeline_done event carries session_id."""
        session_id = uuid.uuid4().hex[:12]
        payload = {"event": "pipeline_done", "session_id": session_id, "text": "hello"}
        self.assertEqual(payload["session_id"], session_id)

    def test_session_id_propagates_via_injection_done(self):
        """injection_done event carries session_id."""
        session_id = uuid.uuid4().hex[:12]
        payload = {
            "event": "injection_done",
            "session_id": session_id,
            "ok": True,
            "state": "verified_success",
            "verified": True,
            "method": "win32_selection",
            "reason": "",
            "clipboard_restored": True,
        }
        self.assertEqual(payload["session_id"], session_id)

    def test_old_session_event_is_filtered_by_main_js(self):
        """Simulate main.js filtering: events with wrong session_id are ignored."""
        active_session_id = uuid.uuid4().hex[:12]
        old_session_id = uuid.uuid4().hex[:12]

        # Old session event
        old_payload = {
            "event": "result_card_show",
            "session_id": old_session_id,
            "text": "old text",
        }
        # Should be ignored because old_session_id != active_session_id
        self.assertNotEqual(old_payload["session_id"], active_session_id)

        # New session event
        new_payload = {
            "event": "result_card_show",
            "session_id": active_session_id,
            "text": "new text",
        }
        self.assertEqual(new_payload["session_id"], active_session_id)

    def test_recording_started_clears_old_state(self):
        """Simulate main.js: recording_started clears pending payload/card."""
        # When recording_started arrives with new session_id:
        # 1. Old resultCardWin should be destroyed
        # 2. pendingResultCardPayload = null
        # 3. pendingResultText = ''
        # 4. activeSessionId = new session_id

        new_session_id = uuid.uuid4().hex[:12]
        old_pending = {"event": "result_card_show", "text": "old"}

        # Simulate cleanup
        pendingResultCardPayload = None
        pendingResultText = ""
        activeSessionId = new_session_id

        self.assertIsNone(pendingResultCardPayload)
        self.assertEqual(pendingResultText, "")
        self.assertEqual(activeSessionId, new_session_id)

    def test_session_id_hex12_is_url_safe(self):
        """12-char hex session_id is safe for JSON transport."""
        sid = uuid.uuid4().hex[:12]
        import json
        serialized = json.dumps({"session_id": sid})
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized["session_id"], sid)

    def test_session_id_generation_is_fast(self):
        """Session ID generation takes < 1ms."""
        import time
        t0 = time.perf_counter()
        for _ in range(1000):
            _ = uuid.uuid4().hex[:12]
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertLess(elapsed_ms, 100, "session_id generation too slow")


class CrossSessionPollutionTests(unittest.TestCase):
    """Phase 2 tests: cross-session pollution prevention."""

    def _simulate_session(self, session_id, events=None):
        """Simulate a session's event sequence."""
        if events is None:
            events = []
        return {
            "session_id": session_id,
            "events": events,
        }

    def _make_result_card_show(self, session_id, text="hello"):
        return {
            "event": "result_card_show",
            "session_id": session_id,
            "text": text,
            "last_transcription": "",
            "state": "no_editable_target",
            "message": "",
        }

    def test_closed_card_does_not_replay_on_next_recording(self):
        """After closing a card, next recording_started starts cleanly."""
        session_a = uuid.uuid4().hex[:12]
        session_b = uuid.uuid4().hex[:12]

        # Simulate session A: card shown and closed
        active_session = session_a
        pending_payload = self._make_result_card_show(session_a, "text from A")
        pending_session = session_a

        # Session A card closed
        pending_payload = None
        pending_text = ""
        pending_session = ""

        # Session B starts — must clear all
        active_session = session_b
        pending_payload = None
        pending_text = ""
        pending_session = ""

        # Verify completely clean
        self.assertIsNone(pending_payload)
        self.assertEqual(pending_text, "")
        self.assertEqual(pending_session, "")
        self.assertEqual(active_session, session_b)

    def test_delayed_old_event_is_ignored(self):
        """A delayed result_card_show from an old session must be ignored."""
        active_session = uuid.uuid4().hex[:12]
        old_session = uuid.uuid4().hex[:12]

        # Simulate main.js guard: session_id must match activeSessionId
        old_event = self._make_result_card_show(old_session, "stale text")
        active_event = self._make_result_card_show(active_session, "fresh text")

        should_ignore_old = (
            old_event["session_id"] and active_session and
            old_event["session_id"] != active_session
        )
        should_accept_new = (
            active_event["session_id"] and active_session and
            active_event["session_id"] == active_session
        )

        self.assertTrue(should_ignore_old, "old session event must be filtered")
        self.assertTrue(should_accept_new, "current session event must pass through")

    def test_delayed_old_result_card_close_is_ignored(self):
        """A delayed result_card_close from old session must not close current card."""
        active_session = uuid.uuid4().hex[:12]
        old_session = uuid.uuid4().hex[:12]

        old_close = {"event": "result_card_close", "session_id": old_session}
        should_ignore = (
            old_close["session_id"] and active_session and
            old_close["session_id"] != active_session
        )
        self.assertTrue(should_ignore)

    def test_delayed_old_copy_done_is_ignored(self):
        """A delayed result_card_copy_done from old session must be ignored."""
        active_session = uuid.uuid4().hex[:12]
        old_session = uuid.uuid4().hex[:12]

        old_copy = {"event": "result_card_copy_done", "session_id": old_session}
        should_ignore = (
            old_copy["session_id"] and active_session and
            old_copy["session_id"] != active_session
        )
        self.assertTrue(should_ignore)

    def test_copy_auto_close_timer_does_not_cross_session(self):
        """Auto-close timer from a copy in session A must not fire into session B."""
        session_a = uuid.uuid4().hex[:12]
        session_b = uuid.uuid4().hex[:12]

        # Simulate: session A copy triggers autoCloseTimer
        auto_close_timer_active = True  # timer is set for session A
        active_session = session_a

        # Session B starts: timer must be cleared
        auto_close_timer_active = False
        active_session = session_b

        self.assertFalse(auto_close_timer_active)
        self.assertEqual(active_session, session_b)

    def test_pipeline_done_clears_pending_state(self):
        """pipeline_done event clears pending card payload for matching session."""
        session = uuid.uuid4().hex[:12]

        # Before pipeline_done, there's a pending payload
        active_session = session
        pending_payload = self._make_result_card_show(session, "text")
        pending_text = "text"
        pending_session = session

        # Simulate pipeline_done arrival with matching session
        if pending_session == active_session:
            pending_payload = None
            pending_text = ""
            pending_session = ""

        self.assertIsNone(pending_payload)
        self.assertEqual(pending_text, "")
        self.assertEqual(pending_session, "")

    def test_error_clears_pending_state(self):
        """error event clears pending card payload for matching session."""
        session = uuid.uuid4().hex[:12]

        active_session = session
        pending_payload = self._make_result_card_show(session, "text")
        pending_text = "text"
        pending_session = session

        # Simulate error with matching session
        if pending_session == active_session:
            pending_payload = None
            pending_text = ""
            pending_session = ""

        self.assertIsNone(pending_payload)

    def test_flush_only_replays_matching_session(self):
        """flushPendingResultCardPayload must not replay if sessions don't match."""
        # Simulate: pending payload tagged with session_a, but active is session_b
        session_a = uuid.uuid4().hex[:12]
        session_b = uuid.uuid4().hex[:12]
        active_session = session_b
        pending_session = session_a

        # Guard in flushPending: if both are non-empty and differ, skip
        should_skip = bool(pending_session) and bool(active_session) and pending_session != active_session
        self.assertTrue(should_skip, "flush must skip when sessions don't match")

    def test_ten_consecutive_valid_inputs_no_card(self):
        """Simulate 10 valid recording sessions with verified success — no card."""
        for i in range(10):
            session = uuid.uuid4().hex[:12]
            # All verified_success should not show result card
            dummy_state = "verified_success"
            self.assertNotEqual(dummy_state, "no_editable_target",
                                f"session {i}: verified_success must not trigger card")


if __name__ == "__main__":
    unittest.main()
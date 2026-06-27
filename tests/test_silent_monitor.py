from __future__ import annotations

import unittest

import infrastructure.silent_monitor as silent_monitor
from infrastructure.focus_context import (
    AppInfo,
    CursorState,
    FocusContext,
    InputCapabilities,
    InputInfo,
    build_input_box_identifier,
)


def make_context(full_text: str, inserted_text: str = "hello wrld") -> FocusContext:
    app = AppInfo(
        app_name="notepad.exe",
        app_identifier="notepad.exe",
        window_title="Untitled - Notepad",
        hwnd=100,
        process_id=200,
        window_class="Notepad",
    )
    before = "prefix "
    after = " suffix"
    input_info = InputInfo(
        accessibility_role="50030",
        input_capabilities=InputCapabilities(
            is_editable=True,
            dom_classes="Edit",
        ),
        cursor_state=CursorState(
            cursor_position=-1,
            text_before_cursor=before,
            text_after_cursor=after,
            full_field_content=full_text,
        ),
    )
    return FocusContext(
        active_application=app,
        text_insertion_point=input_info,
        input_box_identifier=build_input_box_identifier(app, input_info),
    )


class FakeDatabase:
    updates: list[dict] = []
    merged_rules: list[dict] = []
    added_words: list[str] = []

    def __init__(self):
        pass

    @classmethod
    def reset(cls):
        cls.updates = []
        cls.merged_rules = []
        cls.added_words = []

    def update_history_edit(self, entry_id, edited_text, status, attempts_delta=1):
        self.updates.append({
            "entry_id": entry_id,
            "edited_text": edited_text,
            "status": status,
            "attempts_delta": attempts_delta,
        })

    def get_rules(self, active_only=False):
        return []

    def merge_rules(self, rules):
        self.merged_rules.extend(rules)
        return len(rules)

    def add_dictionary_word(self, word):
        self.added_words.append(word)
        return False


class SilentMonitorTests(unittest.TestCase):
    def setUp(self):
        self._old_database = silent_monitor.Database
        FakeDatabase.reset()
        silent_monitor.Database = FakeDatabase

    def tearDown(self):
        silent_monitor.Database = self._old_database

    def test_small_edit_extracts_rule_and_updates_history(self):
        monitor = silent_monitor.SilentMonitor()
        monitor._history_id = "42"
        monitor._refined_text = "hello wrld"
        monitor._track_context = make_context("prefix hello wrld suffix")
        monitor._last_context = make_context("prefix hello world suffix")

        monitor._check_edited_text("track_timeout")

        self.assertTrue(FakeDatabase.merged_rules)
        self.assertEqual(FakeDatabase.merged_rules[0]["pattern"], "wrld")
        self.assertEqual(FakeDatabase.merged_rules[0]["replacement"], "world")
        self.assertEqual(FakeDatabase.updates[-1]["status"], "EXTRACTED")
        self.assertEqual(FakeDatabase.updates[-1]["edited_text"], "hello world")
        # Phase 6: auto dictionary terms must NOT be added on single edit
        self.assertEqual(FakeDatabase.added_words, [],
                         "single edit must NOT auto-add dictionary terms")

    def test_large_full_field_edit_is_not_learned(self):
        monitor = silent_monitor.SilentMonitor()
        monitor._history_id = "43"
        monitor._refined_text = "hello wrld"
        monitor._track_context = make_context("prefix hello wrld suffix")
        monitor._last_context = make_context("completely different text")

        monitor._check_edited_text("track_timeout")

        self.assertEqual(FakeDatabase.merged_rules, [])
        self.assertEqual(FakeDatabase.updates[-1]["status"], "LARGE_MODIFY")
        self.assertIsNone(FakeDatabase.updates[-1]["edited_text"])

    def test_keyboard_events_track_typeless_edit_keys(self):
        monitor = silent_monitor.SilentMonitor()

        monitor._record_keyboard_events([{"keyName": "Shift"}])
        self.assertIsNone(monitor._last_pressed_info)

        monitor._record_keyboard_events([{"keyName": "A"}, {"keyName": "Enter"}])

        self.assertIsNotNone(monitor._last_pressed_info)
        self.assertEqual(
            [event["keyName"] for event in monitor._last_pressed_info["pressingKeys"]],
            ["A", "Enter"],
        )
        self.assertTrue(monitor._recent_enter_pressed())

    def test_learn_does_not_auto_add_dictionary_terms(self):
        """Phase 6: _learn must NOT call _auto_add_dictionary_terms.
        Dictionary entries come ONLY from the promotion engine."""
        monitor = silent_monitor.SilentMonitor()
        monitor._history_id = "99"
        monitor._refined_text = "hello wrld"
        monitor._track_context = make_context("prefix hello wrld suffix")
        monitor._last_context = make_context("prefix hello world suffix")

        monitor._check_edited_text("track_timeout")

        # Rules are still learned (correction rules untouched)
        self.assertTrue(FakeDatabase.merged_rules,
                        "correction rules should still be learned")
        # But no dictionary words added
        self.assertEqual(FakeDatabase.added_words, [],
                         "no dictionary words should be added by _learn alone")
        self.assertNotEqual(FakeDatabase.updates[-1]["status"], "LEARN_FAILED",
                            "learn should succeed even without auto-add")


if __name__ == "__main__":
    unittest.main()

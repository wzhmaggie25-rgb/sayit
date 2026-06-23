from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from infrastructure.context_helper_client import ContextHelperClient
from infrastructure.focus_context import (
    _reset_last_focused_info,
    execute_last_focused_info_task,
    get_focus_context,
    get_last_focus_context,
    get_last_focused_info,
)


class ContextHelperClientTests(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.get("SAYIT_CONTEXT_HELPER")
        ContextHelperClient._instance = None
        _reset_last_focused_info()

    def tearDown(self):
        ContextHelperClient().close()
        ContextHelperClient._instance = None
        if self._old_env is None:
            os.environ.pop("SAYIT_CONTEXT_HELPER", None)
        else:
            os.environ["SAYIT_CONTEXT_HELPER"] = self._old_env
        _reset_last_focused_info()

    def test_missing_helper_falls_back_to_none(self):
        os.environ["SAYIT_CONTEXT_HELPER"] = str(Path(tempfile.gettempdir()) / "missing-sayit-context-helper.exe")
        client = ContextHelperClient()
        self.assertIsNone(client.call("ping", timeout=0.05))
        self.assertIsNone(client.get_full_context(timeout=0.05))
        self.assertEqual(client.poll_keyboard_events(timeout=0.05), [])

    def test_fake_helper_json_rpc_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = self._write_fake_helper(Path(tmp))
            os.environ["SAYIT_CONTEXT_HELPER"] = str(helper)
            client = ContextHelperClient()

            self.assertEqual(client.call("ping", timeout=1.0), {"pong": True})
            context = client.get_full_context(timeout=1.0)
            self.assertIsInstance(context, dict)
            self.assertEqual(context["active_application"]["app_name"], "notepad.exe")
            self.assertEqual(
                context["text_insertion_point"]["cursor_state"]["full_field_content"],
                "hello world",
            )
            window_context = client.get_full_context_for_window(456, timeout=1.0)
            self.assertIsInstance(window_context, dict)
            self.assertEqual(window_context["active_application"]["hwnd"], 456)
            self.assertEqual(client.poll_keyboard_events(timeout=1.0), [{"keyName": "Enter"}])

    def test_focus_context_maps_native_full_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = self._write_fake_helper(Path(tmp))
            os.environ["SAYIT_CONTEXT_HELPER"] = str(helper)
            ContextHelperClient._instance = None

            context = get_focus_context("world")

            self.assertIsNotNone(context)
            self.assertEqual(context.active_application.app_name, "notepad.exe")
            self.assertEqual(context.active_application.hwnd, 456)
            self.assertEqual(context.text_insertion_point.cursor_state.full_field_content, "hello world")
            self.assertEqual(context.text_insertion_point.cursor_state.text_before_cursor, "hello ")
            self.assertEqual(context.text_insertion_point.cursor_state.text_after_cursor, "")
            self.assertIn("notepad.exe", context.input_box_identifier)

    def test_last_focused_info_cache_matches_typeless_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = self._write_fake_helper(Path(tmp))
            os.environ["SAYIT_CONTEXT_HELPER"] = str(helper)
            ContextHelperClient._instance = None

            initial = get_last_focused_info()
            self.assertEqual(initial["startTime"], 0)
            self.assertEqual(initial["endTime"], 0)
            self.assertEqual(initial["appInfo"]["app_name"], "")

            refreshed = execute_last_focused_info_task("world")
            cached_context = get_last_focus_context()

            self.assertIsNotNone(cached_context)
            self.assertGreaterEqual(refreshed["startTime"], 1)
            self.assertGreaterEqual(refreshed["endTime"], refreshed["startTime"])
            self.assertEqual(refreshed["appInfo"]["app_name"], "notepad.exe")
            self.assertEqual(refreshed["appInfo"]["hwnd"], 456)
            self.assertEqual(
                refreshed["inputInfo"]["cursor_state"]["full_field_content"],
                "hello world",
            )

    @staticmethod
    def _write_fake_helper(root: Path) -> Path:
        script = root / "fake_helper.py"
        script.write_text(
            textwrap.dedent(
                r"""
                import json
                import sys

                for line in sys.stdin:
                    req = json.loads(line)
                    method = req.get("method")
                    if method == "ping":
                        result = {"pong": True}
                    elif method in ("get_full_context", "get_full_context_for_window"):
                        hwnd = int((req.get("params") or {}).get("hwnd") or 456)
                        result = {
                            "device_environment": {"platform": "windows"},
                            "active_application": {
                                "app_name": "notepad.exe",
                                "app_identifier": "notepad.exe",
                                "window_title": "Untitled - Notepad",
                                "window_position": {"x": 1, "y": 2, "width": 3, "height": 4},
                                "app_type": "native_app",
                                "app_metadata": {
                                    "process_id": 123,
                                    "app_path": "C:/Windows/notepad.exe",
                                    "window_id": 456,
                                },
                                "browser_context": None,
                                "hwnd": hwnd,
                                "process_id": 123,
                                "window_class": "Notepad",
                            },
                            "text_insertion_point": {
                                "input_area_type": "text_field",
                                "accessibility_role": "50004",
                                "position_on_screen": {"x": 1, "y": 2, "width": 3, "height": 4},
                                "input_capabilities": {
                                    "is_editable": True,
                                    "supports_markdown": False,
                                    "dom_id": "",
                                    "dom_classes": "Edit",
                                },
                                "cursor_state": {
                                    "cursor_position": -1,
                                    "has_text_selected": False,
                                    "selected_text": "",
                                    "text_before_cursor": "",
                                    "text_after_cursor": "",
                                    "full_field_content": "hello world",
                                },
                                "surrounding_context": {
                                    "text_before_input_area": "",
                                    "text_after_input_area": "",
                                },
                            },
                            "context_metadata": {
                                "is_own_application": False,
                                "capture_timestamp": "",
                                "capture_frequency": {
                                    "app_focus_count": 0,
                                    "input_field_focus_count": 0,
                                    "system_info_refresh_count": 0,
                                },
                            },
                        }
                    elif method == "poll_keyboard_events":
                        result = [{"keyName": "Enter"}]
                    else:
                        print(json.dumps({"id": req.get("id"), "ok": False, "error": "unknown"}), flush=True)
                        continue
                    print(json.dumps({"id": req.get("id"), "ok": True, "result": result}), flush=True)
                """
            ),
            encoding="utf-8",
        )
        cmd = root / "fake_helper.cmd"
        cmd.write_text(f'@echo off\r\n"{sys.executable}" "{script}"\r\n', encoding="utf-8")
        return cmd


if __name__ == "__main__":
    unittest.main()

"""Unit tests for tools/agent_bridge/bridge.py — v0.2.2 additions.

Covers:
- BLOCKED_USER_VALIDATION status handling
- _has_new_commits_since actually called in parse fallback
- SUCCESS_TERMINALS = {"DONE", "BLOCKED_USER_VALIDATION"}
- Both success terminals protected from commit_and_push_blocked overwrite
- Multi-segment JSON decoder picks last valid dict
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.agent_bridge import bridge  # noqa: E402


def _write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# SUCCESS_TERMINALS constant
# ---------------------------------------------------------------------------

class SuccessTerminalsTests(unittest.TestCase):
    """SUCCESS_TERMINALS must include both DONE and BLOCKED_USER_VALIDATION."""

    def test_contains_done(self):
        self.assertIn("DONE", bridge.SUCCESS_TERMINALS)

    def test_contains_blocked_user_validation(self):
        self.assertIn("BLOCKED_USER_VALIDATION", bridge.SUCCESS_TERMINALS)

    def test_does_not_contain_plain_blocked(self):
        self.assertNotIn("BLOCKED", bridge.SUCCESS_TERMINALS)


# ---------------------------------------------------------------------------
# Parse fallback with BLOCKED_USER_VALIDATION + _has_new_commits_since
# ---------------------------------------------------------------------------

class ParseFallbackV022Tests(unittest.TestCase):
    """Parse fallback must require new commits for success terminals."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        self._old_ai = bridge.AI_DIR
        bridge.AI_DIR = self._tmp_path / ".ai"
        bridge.AI_DIR.mkdir(parents=True, exist_ok=True)

        self._old_root = bridge.PROJECT_ROOT
        bridge.PROJECT_ROOT = self._tmp_path

        # Init minimal git repo
        subprocess.run(["git", "init"], cwd=self._tmp_path, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@t",
             "commit", "--allow-empty", "-m", "root"],
            cwd=self._tmp_path, capture_output=True,
        )

        # Patch is_working_directory_clean to return True by default
        self._clean_patch = mock.patch.object(
            bridge, "is_working_directory_clean", return_value=True)
        self._clean_patch.start()

    def tearDown(self):
        self._clean_patch.stop()
        bridge.AI_DIR = self._old_ai
        bridge.PROJECT_ROOT = self._old_root
        self._tmp.cleanup()

    def _make_result(self, stdout: str, returncode: int = 0):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout,
        )

    def _write_current_task(self, status: str, sha: str = "abc123def456"):
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md",
                     f"# Task\n\n**{status}**\n\n"
                     f"```text\n{sha}\n```\nDo the thing.\n")

    def test_blocked_user_validation_new_commits_success(self):
        """BLOCKED_USER_VALIDATION + clean + new commits → ok=True."""
        self._write_current_task("BLOCKED_USER_VALIDATION")
        r = self._make_result("no JSON here at all")
        with mock.patch.object(bridge, "_has_new_commits_since", return_value=True):
            parsed = bridge.parse_claude_result(r, task_sha="abc123def456")
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed.get("phase"), "parse_fallback")

    def test_blocked_user_validation_no_new_commits_fails(self):
        """BLOCKED_USER_VALIDATION but no new commits → parse failure."""
        self._write_current_task("BLOCKED_USER_VALIDATION")
        r = self._make_result("no JSON here at all")
        with mock.patch.object(bridge, "_has_new_commits_since", return_value=False):
            parsed = bridge.parse_claude_result(r, task_sha="abc123def456")
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed.get("phase"), "parse")

    def test_done_no_new_commits_fails(self):
        """DONE but no new commits → parse failure."""
        self._write_current_task("DONE")
        r = self._make_result("no JSON here at all")
        with mock.patch.object(bridge, "_has_new_commits_since", return_value=False):
            parsed = bridge.parse_claude_result(r, task_sha="abc123def456")
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed.get("phase"), "parse")

    def test_done_new_commits_and_no_sha_auto_reads_task(self):
        """When task_sha is not passed, parse fallback reads from CURRENT_TASK.md."""
        self._write_current_task("DONE", sha="abc123def456abc123def456abc123def456abc123ab")
        r = self._make_result("no JSON here at all")
        with mock.patch.object(bridge, "_has_new_commits_since", return_value=True):
            parsed = bridge.parse_claude_result(r)  # No task_sha arg
        self.assertTrue(parsed["ok"])


# ---------------------------------------------------------------------------
# commit_and_push_blocked protects both success terminals
# ---------------------------------------------------------------------------

class CommitAndPushBlockedV022Tests(unittest.TestCase):
    """commit_and_push_blocked must refuse to overwrite any SUCCESS_TERMINAL."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        self._old_root = bridge.PROJECT_ROOT
        self._old_ai = bridge.AI_DIR
        bridge.PROJECT_ROOT = self._tmp_path
        bridge.AI_DIR = self._tmp_path / ".ai"
        bridge.AI_DIR.mkdir(parents=True, exist_ok=True)

        # Init a minimal git repo
        subprocess.run(["git", "init"], cwd=self._tmp_path, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@t",
             "commit", "--allow-empty", "-m", "root"],
            cwd=self._tmp_path, capture_output=True,
        )
        _write_file(self._tmp_path / ".gitignore", ".ai/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=self._tmp_path, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@t",
             "commit", "-m", "gitignore"],
            cwd=self._tmp_path, capture_output=True,
        )

    def tearDown(self):
        bridge.PROJECT_ROOT = self._old_root
        bridge.AI_DIR = self._old_ai
        self._tmp.cleanup()

    def test_refuses_when_done(self):
        """commit_and_push_blocked returns True when DONE (no-op)."""
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md", "# Task\n\n**DONE**\n")
        result = bridge.commit_and_push_blocked("test", "summary")
        self.assertTrue(result)
        task_text = (bridge.AI_DIR / "CURRENT_TASK.md").read_text(encoding="utf-8")
        self.assertIn("**DONE**", task_text)

    def test_refuses_when_blocked_user_validation(self):
        """commit_and_push_blocked returns True when BLOCKED_USER_VALIDATION."""
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md",
                     "# Task\n\n**BLOCKED_USER_VALIDATION**\n")
        result = bridge.commit_and_push_blocked("test", "summary")
        self.assertTrue(result)
        task_text = (bridge.AI_DIR / "CURRENT_TASK.md").read_text(encoding="utf-8")
        self.assertIn("**BLOCKED_USER_VALIDATION**", task_text)


# ---------------------------------------------------------------------------
# JSON decoder — multi-segment noisy stdout, picks last valid
# ---------------------------------------------------------------------------

class JsonDecoderV022Tests(unittest.TestCase):
    """_try_parse_json must handle multi-segment stdout reliably."""

    def test_multi_json_last_valid(self):
        """Multiple JSON objects — pick the last valid one."""
        text = """
        some preamble text
        {"ok": false, "summary": "first"}
        more text in between
        {"ok": true, "summary": "last"}
        trailing text
        """
        result = bridge._try_parse_json(text)
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"], "last")

    def test_multi_json_with_invalid_middle(self):
        """Skip invalid JSON fragments, pick last valid."""
        text = '{"ok": true, "x": 1} ~~~ not json at all ~~~ {"ok": false, "summary": "valid"}'
        result = bridge._try_parse_json(text)
        self.assertIsNotNone(result)
        self.assertFalse(result["ok"])

    def test_single_json_noise(self):
        """Single JSON among noise works as expected."""
        text = "Pre {\"ok\": true, \"x\": 1} Post"
        result = bridge._try_parse_json(text)
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])

    def test_no_json_in_noise(self):
        """No JSON at all → None."""
        result = bridge._try_parse_json("Just random text, no JSON here")
        self.assertIsNone(result)

    def test_empty_returns_none(self):
        result = bridge._try_parse_json("")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
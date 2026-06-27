"""Unit tests for tools/agent_bridge/bridge.py — v0.2.1 additions.

Covers:
- utf-8-sig BOM config loading
- Noisy stdout JSON extraction
- DONE + parse failure fallback → success
- READY + parse failure → genuine failure (BLOCKED)
- BLOCKED preserved on parse failure
- commit_and_push_blocked() refuses to overwrite DONE
"""

from __future__ import annotations

import json
import os
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
# utf-8-sig BOM config loading
# ---------------------------------------------------------------------------

class LoadConfigBOMTests(unittest.TestCase):
    """load_config() must handle BOM-prefixed JSON files."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)
        self._config_path = self._tmp_path / "bridge_config.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_loads_utf8_without_bom(self):
        """Config without BOM still works."""
        _write_file(self._config_path, '{"branch": "test-branch"}')
        cfg = bridge.load_config(self._config_path)
        self.assertEqual(cfg.get("branch"), "test-branch")

    def test_loads_utf8_with_bom(self):
        """Config with BOM (\\ufeff) is loaded correctly."""
        with open(self._config_path, "w", encoding="utf-8") as f:
            f.write('\ufeff{"branch": "bom-branch"}')
        cfg = bridge.load_config(self._config_path)
        self.assertEqual(cfg.get("branch"), "bom-branch")

    def test_loads_utf8_with_bom_boolean_preserved(self):
        """Boolean values survive BOM loading."""
        with open(self._config_path, "w", encoding="utf-8") as f:
            f.write('\ufeff{"debug": true}')
        cfg = bridge.load_config(self._config_path)
        self.assertTrue(cfg.get("debug"))


# ---------------------------------------------------------------------------
# Noisy JSON parsing
# ---------------------------------------------------------------------------

class ParseNoisyJsonTests(unittest.TestCase):
    """_try_parse_json must handle noisy stdout."""

    def test_direct_json_parsed(self):
        result = bridge._try_parse_json('{"ok": true, "summary": "clean"}')
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])

    def test_json_with_surrounding_text(self):
        result = bridge._try_parse_json(
            "Here is the result:\n{\"ok\": true, \"summary\": \"embedded\"}\nDone."
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"], "embedded")

    def test_json_with_fence_and_text(self):
        result = bridge._try_parse_json(
            "```json\n{\"ok\": true, \"summary\": \"fenced\"}\n```\nExtra text."
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"], "fenced")

    def test_no_json_returns_none(self):
        result = bridge._try_parse_json("This is just a text message.")
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        result = bridge._try_parse_json("")
        self.assertIsNone(result)

    def test_incomplete_json_returns_none(self):
        result = bridge._try_parse_json('{"ok": true, "summary": "no close')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Parse failure fallback — DONE / BLOCKED / READY
# ---------------------------------------------------------------------------

class ParseFallbackDoneTests(unittest.TestCase):
    """When parse fails but Claude exits 0, check CURRENT_TASK status."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        # Keep bridges's AI_DIR pointed at our temp
        self._old_ai = bridge.AI_DIR
        bridge.AI_DIR = self._tmp_path / ".ai"
        bridge.AI_DIR.mkdir(parents=True, exist_ok=True)

        # Patch is_working_directory_clean to return True by default
        self._clean_patch = mock.patch.object(bridge, "is_working_directory_clean", return_value=True)
        self._clean_patch.start()

    def tearDown(self):
        self._clean_patch.stop()
        bridge.AI_DIR = self._old_ai
        self._tmp.cleanup()

    def _make_result(self, stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout,
        )

    def _write_current_task(self, status: str):
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md",
                     f"# Task\n\n**{status}**\n\nDo the thing.\n")

    # --- DONE + clean tree → success fallback ---
    def test_done_and_clean_yields_success(self):
        self._write_current_task("DONE")
        r = self._make_result("no JSON here at all")
        parsed = bridge.parse_claude_result(r)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed.get("phase"), "parse_fallback")

    # --- BLOCKED preserved ---
    def test_blocked_preserved(self):
        self._write_current_task("BLOCKED")
        r = self._make_result("no JSON here at all")
        parsed = bridge.parse_claude_result(r)
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed.get("phase"), "parse_fallback")
        self.assertIn("BLOCKED", parsed.get("summary", ""))

    # --- READY + parse failure → genuine parse failure ---
    def test_ready_parse_failure_is_blocked(self):
        self._write_current_task("READY")
        r = self._make_result("garbage output")
        parsed = bridge.parse_claude_result(r)
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed.get("phase"), "parse")

    # --- Non-zero exit → still parse failure, not fallback ---
    def test_nonzero_exit_without_json(self):
        self._write_current_task("DONE")
        r = self._make_result("some text", returncode=1)
        parsed = bridge.parse_claude_result(r)
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed.get("phase"), "claude")

    # --- DONE but dirty tree → parse failure (no fallback) ---
    def test_done_but_dirty_no_fallback(self):
        self._write_current_task("DONE")
        self._clean_patch.stop()
        with mock.patch.object(bridge, "is_working_directory_clean", return_value=False):
            r = self._make_result("no JSON here")
            parsed = bridge.parse_claude_result(r)
            self.assertFalse(parsed["ok"])
            self.assertEqual(parsed.get("phase"), "parse")
        self._clean_patch.start()


# ---------------------------------------------------------------------------
# commit_and_push_blocked refuses to overwrite DONE
# ---------------------------------------------------------------------------

class CommitAndPushBlockedDoneTests(unittest.TestCase):
    """commit_and_push_blocked must refuse when CURRENT_TASK is already DONE."""

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

    def test_refuses_when_task_is_done(self):
        """commit_and_push_blocked returns True when task already DONE (no-op)."""
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md", "# Task\n\n**DONE**\n")
        result = bridge.commit_and_push_blocked("test_reason", "test summary")
        self.assertTrue(result)
        # Verify status was NOT changed to BLOCKED
        task_text = (bridge.AI_DIR / "CURRENT_TASK.md").read_text(encoding="utf-8")
        self.assertIn("**DONE**", task_text)
        self.assertNotIn("**BLOCKED**", task_text)

    def test_proceeds_when_task_is_ready(self):
        """commit_and_push_blocked proceeds normally when task is READY."""
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md", "# Task\n\n**READY**\n")
        # Will fail to push (no remote), but should at least attempt staging
        result = bridge.commit_and_push_blocked("test_reason", "test summary")
        self.assertFalse(result)  # fails at push stage, not at DONE check

    def test_proceeds_when_task_is_blocked(self):
        """commit_and_push_blocked proceeds normally when task is already BLOCKED."""
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md", "# Task\n\n**BLOCKED**\n")
        result = bridge.commit_and_push_blocked("test_reason", "test summary")
        self.assertFalse(result)  # fails at push stage, not at DONE check


# ---------------------------------------------------------------------------
# _read_current_task_status
# ---------------------------------------------------------------------------

class ReadCurrentTaskStatusTests(unittest.TestCase):
    """_read_current_task_status extracts status marker correctly."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_done(self):
        p = _write_file(self._tmp_path / "task.md", "# Task\n\n**DONE**\n")
        self.assertEqual(bridge._read_current_task_status(p), "DONE")

    def test_reads_blocked(self):
        p = _write_file(self._tmp_path / "task.md", "# Task\n\n**BLOCKED**\n")
        self.assertEqual(bridge._read_current_task_status(p), "BLOCKED")

    def test_reads_ready(self):
        p = _write_file(self._tmp_path / "task.md", "# Task\n\n**READY**\n")
        self.assertEqual(bridge._read_current_task_status(p), "READY")

    def test_no_file_returns_none(self):
        p = self._tmp_path / "nonexistent.md"
        self.assertIsNone(bridge._read_current_task_status(p))

    def test_empty_file_returns_none(self):
        p = _write_file(self._tmp_path / "task.md", "")
        self.assertIsNone(bridge._read_current_task_status(p))


# ---------------------------------------------------------------------------
# _has_new_commits_since
# ---------------------------------------------------------------------------

class HasNewCommitsSinceTests(unittest.TestCase):
    """_has_new_commits_since detects HEAD changes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)
        subprocess.run(["git", "init"], cwd=self._tmp_path, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@t",
             "commit", "--allow-empty", "-m", "first"],
            cwd=self._tmp_path, capture_output=True,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _sha(self) -> str:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self._tmp_path,
            capture_output=True, text=True,
        )
        return r.stdout.strip()

    def test_no_new_commits(self):
        sha = self._sha()
        self.assertFalse(bridge._has_new_commits_since(sha, path=self._tmp_path))

    def test_new_commit_detected(self):
        sha_before = self._sha()
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@t",
             "commit", "--allow-empty", "-m", "second"],
            cwd=self._tmp_path, capture_output=True,
        )
        self.assertTrue(bridge._has_new_commits_since(sha_before, path=self._tmp_path))


if __name__ == "__main__":
    unittest.main()
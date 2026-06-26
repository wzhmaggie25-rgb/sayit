"""Unit tests for tools/agent_bridge/bridge.py (v0.2.0)

Follows the project's unittest patterns: setUp/tearDown, monkey-patching of
module-level functions, and fake subprocess scripts.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Precondition tests
# ---------------------------------------------------------------------------

class PreconditionTests(unittest.TestCase):
    """Each test patches git/state/CURRENT_TASK so only one guard is
    exercised at a time."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        # Minimal git repo
        subprocess.run(["git", "init"], cwd=self._tmp_path, capture_output=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t",
                        "commit", "--allow-empty", "-m", "root"],
                       cwd=self._tmp_path, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin",
                        self._tmp_path / ".git"],
                       cwd=self._tmp_path, capture_output=True)
        subprocess.run(["git", "checkout", "-b",
                        "feature/silent-learning-stabilization"],
                       cwd=self._tmp_path, capture_output=True)

        # .gitignore so .ai/ doesn't dirty the repo
        _write_file(self._tmp_path / ".gitignore", ".ai/\nbridge_state.json\nbridge.lock\n")
        subprocess.run(["git", "add", ".gitignore"],
                       cwd=self._tmp_path, capture_output=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t",
                        "commit", "-m", "gitignore"],
                       cwd=self._tmp_path, capture_output=True)

        self._old_root = bridge.PROJECT_ROOT
        self._old_ai = bridge.AI_DIR

        bridge.PROJECT_ROOT = self._tmp_path
        bridge.AI_DIR = self._tmp_path / ".ai"
        bridge.AI_DIR.mkdir(parents=True, exist_ok=True)

        self.config = {
            "branch": "feature/silent-learning-stabilization",
            "remote": "origin",
            "state_file": str(self._tmp_path / "bridge_state.json"),
            "lock_file": str(self._tmp_path / "bridge.lock"),
            "log_file": str(self._tmp_path / "bridge.log"),
        }

        _write_file(
            bridge.AI_DIR / "CURRENT_TASK.md",
            "# Current Task\n\n**READY**\n\nDo something\n",
        )

    def tearDown(self):
        bridge.PROJECT_ROOT = self._old_root
        bridge.AI_DIR = self._old_ai
        self._tmp.cleanup()

    def _current_sha(self) -> str:
        r = subprocess.run(["git", "rev-parse", "HEAD"],
                           cwd=bridge.PROJECT_ROOT, capture_output=True, text=True)
        return r.stdout.strip()

    # --- C1: READY in local, no remote changes → STILL executes ---
    def test_local_ready_without_remote_changes_still_executes(self):
        result = bridge.check_preconditions(self.config)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 40)

    # --- C2: DONE/BLOCKED, no remote changes → skip ---
    def test_done_without_remote_skips(self):
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md", "# Task\n\n**DONE**\n")
        result = bridge.check_preconditions(self.config)
        self.assertIsNone(result)

    def test_blocked_without_remote_skips(self):
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md", "# Task\n\n**BLOCKED**\n")
        result = bridge.check_preconditions(self.config)
        self.assertIsNone(result)

    # --- C3: Wrong branch → None ---
    def test_wrong_branch_returns_none(self):
        subprocess.run(["git", "checkout", "-b", "other-branch"],
                       cwd=bridge.PROJECT_ROOT, capture_output=True)
        result = bridge.check_preconditions(self.config)
        self.assertIsNone(result)

    # --- C4: Dirty working directory → None ---
    def test_dirty_directory_returns_none(self):
        _write_file(self._tmp_path / "dirty.txt", "changes")
        result = bridge.check_preconditions(self.config)
        self.assertIsNone(result)

    # --- C5: Already processed same SHA → skip ---
    def test_already_processed_skips(self):
        sha = self._current_sha()
        _write_file(
            Path(self.config["state_file"]),
            json.dumps({"last_processed_sha": sha}),
        )
        result = bridge.check_preconditions(self.config)
        self.assertIsNone(result)

    # --- C6: Restart recovery — new SHA after commit keeps READY ---
    def test_ready_after_new_commit_is_new_task(self):
        sha_before = self._current_sha()
        # Mark old SHA as processed
        _write_file(
            Path(self.config["state_file"]),
            json.dumps({"last_processed_sha": sha_before}),
        )
        # A new commit comes in (simulate by making a change)
        _write_file(self._tmp_path / "newfile.txt", "content")
        subprocess.run(["git", "add", "newfile.txt"],
                       cwd=bridge.PROJECT_ROOT, capture_output=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t",
                        "commit", "-m", "new"],
                       cwd=self._tmp_path, capture_output=True)
        # READY task still exists
        result = bridge.check_preconditions(self.config)
        self.assertIsNotNone(result)
        self.assertNotEqual(result, sha_before)

    # --- C7: Merge in progress → None ---
    def test_in_progress_operation_returns_none(self):
        (self._tmp_path / ".git" / "MERGE_HEAD").write_text("abc", encoding="utf-8")
        result = bridge.check_preconditions(self.config)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Claude JSON parsing tests — D
# ---------------------------------------------------------------------------

class ParseResultTests(unittest.TestCase):
    """Test parse_claude_result with various envelope shapes."""

    def _make_result(self, returncode: int, stdout: str) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout,
        )

    # D1: Direct flat JSON
    def test_direct_json_ok(self):
        r = self._make_result(0, '{"ok": true, "summary": "done"}')
        parsed = bridge.parse_claude_result(r)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["summary"], "done")

    # D2: Envelope with result string JSON
    def test_envelope_with_result_json(self):
        stdout = json.dumps({
            "type": "result",
            "result": '{"ok": true, "summary": "done inside"}',
            "is_error": False,
        })
        r = self._make_result(0, stdout)
        parsed = bridge.parse_claude_result(r)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["summary"], "done inside")

    # D3: Envelope with result as code block
    def test_envelope_with_result_code_block(self):
        stdout = json.dumps({
            "type": "result",
            "result": '```json\n{"ok": true, "summary": "code block"}\n```',
            "is_error": False,
        })
        r = self._make_result(0, stdout)
        parsed = bridge.parse_claude_result(r)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["summary"], "code block")

    # D4: Envelope with result as plain text (no JSON inside)
    def test_envelope_plain_text_result(self):
        stdout = json.dumps({
            "type": "result",
            "result": "Task completed successfully",
            "is_error": False,
        })
        r = self._make_result(0, stdout)
        parsed = bridge.parse_claude_result(r)
        self.assertTrue(parsed["ok"])
        self.assertIn("completed", parsed.get("summary", ""))

    # D5: Non-zero exit code → ok=False
    def test_nonzero_exit(self):
        r = self._make_result(1, "")
        parsed = bridge.parse_claude_result(r)
        self.assertFalse(parsed["ok"])
        self.assertIn("phase", parsed)

    # D6: Invalid JSON → ok=False
    def test_invalid_json(self):
        r = self._make_result(0, "This is not JSON")
        parsed = bridge.parse_claude_result(r)
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed.get("phase"), "parse")

    # D7: Envelope with is_error=true
    def test_envelope_is_error(self):
        stdout = json.dumps({
            "type": "result",
            "result": "Something went wrong",
            "is_error": True,
        })
        r = self._make_result(0, stdout)
        parsed = bridge.parse_claude_result(r)
        self.assertFalse(parsed["ok"])

    # D8: Code-block wrapped JSON at top level
    def test_top_level_code_block(self):
        stdout = "Here is the result:\n```json\n{\"ok\": true, \"summary\": \"block\"}\n```\n"
        r = self._make_result(0, stdout)
        parsed = bridge.parse_claude_result(r)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["summary"], "block")


# ---------------------------------------------------------------------------
# Claude invocation tests — B: cwd=PROJECT_ROOT
# ---------------------------------------------------------------------------

class ClaudeInvocationTests(unittest.TestCase):
    def test_call_claude_sets_cwd(self):
        """call_claude must pass cwd=PROJECT_ROOT to subprocess."""
        fake_result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"ok": true, "summary": "done"}',
        )
        with mock.patch("tools.agent_bridge.bridge.claude_binary_path", return_value="claude"):
            with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
                config = {"claude_binary": "claude",
                          "claude_timeout_seconds": 30}
                bridge.call_claude("test prompt", config)
                _, kwargs = mock_run.call_args
                self.assertEqual(kwargs["cwd"], bridge.PROJECT_ROOT)

    def test_claude_binary_path_sets_cwd(self):
        """claude --version must also be run from PROJECT_ROOT."""
        fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="2.1.0")
        with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
            bridge.claude_binary_path({"claude_binary": "claude"})
            _, kwargs = mock_run.call_args
            self.assertEqual(kwargs["cwd"], bridge.PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Lock tests
# ---------------------------------------------------------------------------

class LockTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lock_path = Path(self._tmp.name) / "test.lock"

    def tearDown(self):
        self._tmp.cleanup()

    def test_acquire_release(self):
        self.assertTrue(bridge.acquire_lock(str(self._lock_path)))
        self.assertTrue(self._lock_path.exists())
        bridge.release_lock(str(self._lock_path))
        self.assertFalse(self._lock_path.exists())

    def test_acquire_twice_fails(self):
        bridge.acquire_lock(str(self._lock_path))
        self.assertFalse(bridge.acquire_lock(str(self._lock_path)))

    def test_stale_lock_is_overwritten(self):
        self._lock_path.write_text("999999999", encoding="utf-8")
        self.assertTrue(bridge.acquire_lock(str(self._lock_path)))


# ---------------------------------------------------------------------------
# State tests
# ---------------------------------------------------------------------------

class StateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state_path = Path(self._tmp.name) / "state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_state(self):
        self.assertFalse(
            bridge.is_task_already_processed(str(self._state_path), "abc123")
        )

    def test_matches_sha(self):
        bridge.mark_task_processed(str(self._state_path), "abc123")
        self.assertTrue(
            bridge.is_task_already_processed(str(self._state_path), "abc123")
        )

    def test_different_sha(self):
        bridge.mark_task_processed(str(self._state_path), "abc123")
        self.assertFalse(
            bridge.is_task_already_processed(str(self._state_path), "def456")
        )


# ---------------------------------------------------------------------------
# Git helper tests
# ---------------------------------------------------------------------------

class GitHelperTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._repo = Path(self._tmp.name)
        subprocess.run(["git", "init"], cwd=self._repo, capture_output=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t",
                        "commit", "--allow-empty", "-m", "init"],
                       cwd=self._repo, capture_output=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_is_git_repo(self):
        self.assertTrue(bridge.is_git_repo(self._repo))

    def test_not_git_repo(self):
        not_repo = Path(tempfile.mkdtemp())
        try:
            self.assertFalse(bridge.is_git_repo(not_repo))
        finally:
            not_repo.rmdir()

    def test_get_current_branch(self):
        subprocess.run(["git", "checkout", "-b", "my-test-branch"],
                       cwd=self._repo, capture_output=True)
        self.assertEqual(bridge.get_current_branch(self._repo), "my-test-branch")

    def test_clean_working_directory(self):
        self.assertTrue(bridge.is_working_directory_clean(self._repo))

    def test_dirty_working_directory(self):
        (self._repo / "untracked.txt").write_text("hi", encoding="utf-8")
        self.assertFalse(bridge.is_working_directory_clean(self._repo))

    def test_in_progress_operation(self):
        self.assertFalse(bridge.has_in_progress_operation(self._repo))
        (self._repo / ".git" / "MERGE_HEAD").write_text("abc", encoding="utf-8")
        self.assertTrue(bridge.has_in_progress_operation(self._repo))

    def test_get_local_sha(self):
        sha = bridge.get_local_sha(self._repo)
        self.assertEqual(len(sha), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in sha))


# ---------------------------------------------------------------------------
# Readiness tests
# ---------------------------------------------------------------------------

class IsTaskReadyTests(unittest.TestCase):
    def test_ready_detected(self):
        self.assertTrue(bridge.is_task_ready("# Task\n\n**READY**\n"))

    def test_blocked_not_ready(self):
        self.assertFalse(bridge.is_task_ready("# Task\n\n**BLOCKED**\n"))

    def test_done_not_ready(self):
        self.assertFalse(bridge.is_task_ready("# Task\n\n**DONE**\n"))

    def test_empty_string(self):
        self.assertFalse(bridge.is_task_ready(""))


# ---------------------------------------------------------------------------
# Prompt build tests
# ---------------------------------------------------------------------------

class BuildPromptTests(unittest.TestCase):
    def test_build_prompt_contains_task_text(self):
        task = "Fix the bug in module X"
        prompt = bridge.build_claude_prompt(task, {})
        self.assertIn(task, prompt)
        self.assertIn("AGENTS.md", prompt)
        self.assertIn("PROJECT_STATE.md", prompt)
        self.assertIn("CURRENT_TASK.md", prompt)
        self.assertIn("force push", prompt)


if __name__ == "__main__":
    unittest.main()
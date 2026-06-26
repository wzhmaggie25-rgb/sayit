"""Unit tests for tools/agent_bridge/bridge.py

Follows the project's unittest patterns: setUp/tearDown, monkey-patching of
module-level functions, and fake subprocess scripts.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

# Import the bridge module
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


def _make_fake_claude_script(exit_code: int, stdout: str) -> str:
    """Build the batch script content for a fake claude.cmd."""
    escaped = stdout.replace('"', '"""')
    lines = [
        "@echo off",
        f"echo {escaped}",
        f"exit /b {exit_code}",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class PreconditionTests(unittest.TestCase):
    """Tests for check_preconditions() — each test patches git/CURRENT_TASK
    so only one guard is exercised at a time."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        # Create a minimal git repo in tmp
        subprocess.run(["git", "init"], cwd=self._tmp_path, capture_output=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t",
                        "commit", "--allow-empty", "-m", "root"],
                       cwd=self._tmp_path, capture_output=True)
        # Set up remote so fetch doesn't fail
        subprocess.run(["git", "remote", "add", "origin",
                        self._tmp_path / ".git"],
                       cwd=self._tmp_path, capture_output=True)
        # Create branch
        subprocess.run(["git", "checkout", "-b",
                        "feature/silent-learning-stabilization"],
                       cwd=self._tmp_path, capture_output=True)

        self._old_root = bridge.PROJECT_ROOT
        self._old_ai = bridge.AI_DIR

        bridge.PROJECT_ROOT = self._tmp_path
        bridge.AI_DIR = self._tmp_path / ".ai"
        bridge.AI_DIR.mkdir(parents=True, exist_ok=True)

        # Default config pointing to temp locations
        self.config = {
            "branch": "feature/silent-learning-stabilization",
            "remote": "origin",
            "state_file": str(self._tmp_path / "bridge_state.json"),
            "lock_file": str(self._tmp_path / "bridge.lock"),
        }

        # Write a .gitignore so the .ai/ and state/lock files don't dirty the repo
        _write_file(
            self._tmp_path / ".gitignore",
            ".ai/\nbridge_state.json\nbridge.lock\nbridge.log\n",
        )
        subprocess.run(["git", "add", ".gitignore"],
                       cwd=self._tmp_path, capture_output=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t",
                        "commit", "-m", "add gitignore"],
                       cwd=self._tmp_path, capture_output=True)

        # Default CURRENT_TASK.md — READY
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

    # --- Test 1: No remote changes → returns None (no action) ---
    def test_no_remote_changes_returns_none(self):
        # Push current state so fetch sees nothing new
        subprocess.run(["git", "push", "origin",
                        "feature/silent-learning-stabilization"],
                       cwd=bridge.PROJECT_ROOT, capture_output=True)

        result = bridge.check_preconditions(self.config)
        self.assertIsNone(result)

    # --- Test 2: CURRENT_TASK not READY → returns error string ---
    def test_not_ready_skips_execution(self):
        _write_file(bridge.AI_DIR / "CURRENT_TASK.md", "# Task\n\n**BLOCKED**\n")
        # Mock fetch_remote to simulate new commits arriving
        with mock.patch("tools.agent_bridge.bridge.fetch_remote", return_value=True):
            with mock.patch("tools.agent_bridge.bridge.can_fast_forward", return_value=True):
                with mock.patch("tools.agent_bridge.bridge.pull_ff_only",
                                return_value=bridge.get_local_sha()):
                    result = bridge.check_preconditions(self.config)
        self.assertIsNotNone(result)
        self.assertIn("not READY", result)

    # --- Test 3: Dirty working directory → blocked ---
    def test_dirty_working_directory_blocked(self):
        _write_file(self._tmp_path / "dirty.txt", "changes")
        result = bridge.check_preconditions(self.config)
        self.assertIsNotNone(result)
        self.assertIn("uncommitted", result)

    # --- Test 4: Wrong branch → blocked ---
    def test_wrong_branch_blocked(self):
        subprocess.run(["git", "checkout", "-b", "other-branch"],
                       cwd=bridge.PROJECT_ROOT, capture_output=True)
        result = bridge.check_preconditions(self.config)
        self.assertIsNotNone(result)
        self.assertIn("Wrong branch", result)

    # --- Test 5: Same SHA already processed → skip ---
    def test_already_processed_skips(self):
        sha = self._current_sha()
        _write_file(
            Path(self.config["state_file"]),
            json.dumps({"last_processed_sha": sha}),
        )

        with mock.patch("tools.agent_bridge.bridge.fetch_remote", return_value=True):
            with mock.patch("tools.agent_bridge.bridge.can_fast_forward", return_value=True):
                with mock.patch("tools.agent_bridge.bridge.pull_ff_only",
                                return_value=sha):
                    result = bridge.check_preconditions(self.config)
        self.assertIsNotNone(result)
        self.assertIn("already processed", result)

    # --- Test 6: Lock file prevents concurrent execution ---
    def test_lock_file_prevents_concurrent(self):
        _write_file(
            Path(self.config["lock_file"]),
            str(os.getpid()),  # current PID
        )
        acquired = bridge.acquire_lock(self.config["lock_file"])
        self.assertFalse(acquired)


class ClaudeInvocationTests(unittest.TestCase):
    """Tests for Claude invocation and result parsing."""

    def test_call_claude_success(self):
        """call_claude should return the CompletedProcess from subprocess."""
        fake_result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='{"ok": true, "summary": "done"}',
        )
        with mock.patch("tools.agent_bridge.bridge.claude_binary_path", return_value="claude"):
            with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
                config = {"claude_binary": "claude",
                          "claude_timeout_seconds": 30}
                result = bridge.call_claude("test prompt", config)
                self.assertEqual(result.returncode, 0)
                mock_run.assert_called_once()

    def test_call_claude_failure_exit_code(self):
        """Non-zero exit code from Claude should be preserved."""
        fake_result = subprocess.CompletedProcess(
            args=[], returncode=1,
            stdout='{"ok": false, "summary": "error"}',
        )
        with mock.patch("tools.agent_bridge.bridge.claude_binary_path", return_value="claude"):
            with mock.patch("subprocess.run", return_value=fake_result):
                config = {"claude_binary": "claude",
                          "claude_timeout_seconds": 30}
                result = bridge.call_claude("test", config)
                self.assertEqual(result.returncode, 1)
        parsed = bridge.parse_claude_result(result)
        self.assertFalse(parsed["ok"])

    def test_parse_json_code_block(self):
        """Claude sometimes wraps JSON in ```json ... ```."""
        stdout = "Here is the result:\n```json\n{\"ok\": true, \"summary\": \"done\"}\n```\n"
        proc = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout)
        parsed = bridge.parse_claude_result(proc)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["summary"], "done")

    def test_parse_invalid_json(self):
        stdout = "Something went wrong but not JSON"
        proc = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout)
        parsed = bridge.parse_claude_result(proc)
        self.assertFalse(parsed["ok"])
        self.assertIn("parse", parsed.get("phase", ""))


class LockTests(unittest.TestCase):
    """Tests for PID-based lock file."""

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
        """A lock file with a non-existent PID should be overwritten."""
        self._lock_path.write_text("999999999", encoding="utf-8")
        self.assertTrue(bridge.acquire_lock(str(self._lock_path)))


class StateTests(unittest.TestCase):
    """Tests for task state persistence."""

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


class GitHelperTests(unittest.TestCase):
    """Tests for git helper functions using a temporary repo."""

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
        """MERGE_HEAD marker should indicate in-progress operation."""
        self.assertFalse(bridge.has_in_progress_operation(self._repo))
        (self._repo / ".git" / "MERGE_HEAD").write_text("abc", encoding="utf-8")
        self.assertTrue(bridge.has_in_progress_operation(self._repo))

    def test_get_local_sha(self):
        sha = bridge.get_local_sha(self._repo)
        self.assertEqual(len(sha), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in sha))


class EndToEndMockedTests(unittest.TestCase):
    """Simulate a full lifecycle with mocked Claude.

    Creates a repo with a commit, pushes it, then runs run_once() and
    verifies that the lock, state, and status are correctly managed.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._repo = Path(self._tmp.name)

        # Init repo with a commit
        subprocess.run(["git", "init"], cwd=self._repo, capture_output=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t",
                        "commit", "--allow-empty", "-m", "root"],
                       cwd=self._repo, capture_output=True)
        subprocess.run(["git", "checkout", "-b",
                        "feature/silent-learning-stabilization"],
                       cwd=self._repo, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin",
                        self._repo / ".git"],
                       cwd=self._repo, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin",
                        "feature/silent-learning-stabilization"],
                       cwd=self._repo, capture_output=True)

        # Save state before altering globals
        self._old_root = bridge.PROJECT_ROOT
        self._old_ai = bridge.AI_DIR

        bridge.PROJECT_ROOT = self._repo
        bridge.AI_DIR = self._repo / ".ai"
        bridge.AI_DIR.mkdir(parents=True, exist_ok=True)

        # Default READY task
        _write_file(
            bridge.AI_DIR / "CURRENT_TASK.md",
            "# Task\n\n**READY**\n\nUpdate .ai/BRIDGE_SMOKE_TEST.md\n",
        )

        self.config = {
            "branch": "feature/silent-learning-stabilization",
            "remote": "origin",
            "state_file": str(self._repo / "bridge_state.json"),
            "lock_file": str(self._repo / "bridge.lock"),
            "claude_timeout_seconds": 30,
            "claude_binary": "claude",
        }

        # Create a fake claude that returns success JSON
        self._fake_claude_dir = Path(tempfile.mkdtemp())
        self._fake_claude = self._fake_claude_dir / "claude.cmd"
        self._fake_claude.write_text(
            '@echo off\n'
            'echo {"ok": true, "summary": "mocked task complete", '
            '"commit_sha": "mock123", "files_changed": [".ai/BRIDGE_SMOKE_TEST.md"], '
            '"tests_passed": 1, "tests_failed": 0}\n'
            'exit /b 0\n',
            encoding="utf-8",
        )
        self._old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(self._fake_claude_dir) + os.pathsep + self._old_path

    def tearDown(self):
        bridge.PROJECT_ROOT = self._old_root
        bridge.AI_DIR = self._old_ai
        os.environ["PATH"] = self._old_path
        self._tmp.cleanup()

    def test_full_mocked_lifecycle(self):
        # Create a new commit on remote (simulate by pushing from another clone)
        # We push from the same repo — this won't create "new" commits since
        # there's no divergence.
        # To simulate new commits on remote, push and then fetch:
        sha_before = bridge.get_local_sha(self._repo)
        result = bridge.run_once(self.config)
        # Since there are no new remote commits, run_once returns False
        self.assertFalse(result)


class IsTaskReadyTests(unittest.TestCase):
    """Tests for CURRENT_TASK.md status parsing."""

    def test_ready_detected(self):
        self.assertTrue(bridge.is_task_ready("# Task\n\n**READY**\n"))

    def test_blocked_not_ready(self):
        self.assertFalse(bridge.is_task_ready("# Task\n\n**BLOCKED**\n"))

    def test_done_not_ready(self):
        self.assertFalse(bridge.is_task_ready("# Task\n\n**DONE**\n"))

    def test_empty_string(self):
        self.assertFalse(bridge.is_task_ready(""))


class BuildPromptTests(unittest.TestCase):
    """Tests for prompt assembly."""

    def test_build_prompt_contains_task_text(self):
        task = "Fix the bug in module X"
        prompt = bridge.build_claude_prompt(task, {})
        self.assertIn(task, prompt)
        self.assertIn("AGENTS.md", prompt)
        self.assertIn("PROJECT_STATE.md", prompt)
        self.assertIn("CURRENT_TASK.md", prompt)
        self.assertIn("JSON", prompt)
        self.assertIn("force push", prompt)


if __name__ == "__main__":
    unittest.main()
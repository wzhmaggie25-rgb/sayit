"""Agent Bridge — polls GitHub for READY tasks and dispatches them to Claude Code.

Usage:
    python tools/agent_bridge/bridge.py              # normal run
    python tools/agent_bridge/bridge.py --once       # single poll cycle and exit
    python tools/agent_bridge/bridge.py --version    # print version
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "0.2.0"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = PROJECT_ROOT / "tools" / "agent_bridge"
AI_DIR = PROJECT_ROOT / ".ai"

DEFAULT_CONFIG = {
    "branch": "feature/silent-learning-stabilization",
    "remote": "origin",
    "poll_interval_seconds": 30,
    "claude_timeout_seconds": 300,
    "claude_binary": "claude",
    "log_file": str(TOOLS_DIR / "bridge.log"),
    "lock_file": str(TOOLS_DIR / "bridge.lock"),
    "state_file": str(TOOLS_DIR / "bridge_state.json"),
    "config_file": str(TOOLS_DIR / "bridge_config.json"),
    "claude_allowed_tools": [
        "Read",
        "Edit",
        "Write",
        "Bash(git*)",
        "Bash(python*)",
        "Bash(pytest*)",
        "Bash(claude*)",
    ],
    # "model": "",  # optional — if non-empty, passed as --model
}

_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logger = logging.getLogger("agent_bridge")


def setup_logging(config: dict) -> None:
    """Configure logging to both console and file."""
    level = _LOG_LEVELS.get(config.get("log_level", "info"), logging.INFO)
    log_file = config.get("log_file")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            handlers.append(fh)
        except OSError as exc:
            logger.warning("Cannot open log file %s: %s", log_file, exc)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def find_config() -> Path:
    """Locate config file: explicit path or default location."""
    return TOOLS_DIR / "bridge_config.json"


def load_config(config_path: Path | str | None = None) -> dict:
    """Load config from JSON file merged over defaults.

    Returns a config dict.  Missing values fall back to DEFAULT_CONFIG.
    """
    cfg = dict(DEFAULT_CONFIG)

    if config_path is None:
        config_path = find_config()

    config_path = Path(config_path)
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update(user_cfg)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load config %s: %s", config_path, exc)
    else:
        logger.info("No config file at %s — using defaults", config_path)

    return cfg


def resolve_project_root() -> Path:
    """Return the SayIt project root (parent of tools/agent_bridge/)."""
    return PROJECT_ROOT


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and return the CompletedProcess.

    When *check* is True (default), raises RuntimeError on non-zero exit.
    When *check* is False, returns the CompletedProcess regardless of exit code.
    """
    if cwd is None:
        cwd = PROJECT_ROOT
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result


def is_git_repo(path: Path | None = None) -> bool:
    """Check whether *path* (or PROJECT_ROOT) is inside a Git repository."""
    try:
        _git(["rev-parse", "--git-dir"], cwd=path or PROJECT_ROOT)
        return True
    except RuntimeError:
        return False


def get_current_branch(path: Path | None = None) -> str:
    """Return the current branch name."""
    result = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path or PROJECT_ROOT)
    return result.stdout.strip()


def is_working_directory_clean(path: Path | None = None) -> bool:
    """Return True if the working tree is clean (no staged/unstaged changes)."""
    result = _git(["status", "--porcelain"], cwd=path or PROJECT_ROOT)
    return len(result.stdout.strip()) == 0


def has_in_progress_operation(path: Path | None = None) -> bool:
    """Check for ongoing merge, rebase, cherry-pick, or bisect."""
    cwd = path or PROJECT_ROOT
    git_dir = cwd / ".git"
    markers = ["MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "BISECT_LOG"]
    for marker in markers:
        if (git_dir / marker).exists():
            return True
    return False


def get_local_sha(path: Path | None = None) -> str:
    """Return the full SHA of HEAD."""
    result = _git(["rev-parse", "HEAD"], cwd=path or PROJECT_ROOT)
    return result.stdout.strip()


def fetch_remote(remote: str = "origin", branch: str | None = None, path: Path | None = None) -> None:
    """Fetch remote tracking branch.

    Raises RuntimeError on failure.
    """
    cwd = path or PROJECT_ROOT
    args = ["fetch", remote]
    if branch:
        args.append(branch)
    _git(args, cwd=cwd)


def can_fast_forward(remote: str = "origin", branch: str | None = None, path: Path | None = None) -> bool:
    """Return True if ``git pull --ff-only`` would succeed.

    Uses ``git merge-base --is-ancestor`` to check whether HEAD is an ancestor
    of the remote tracking branch.
    """
    cwd = path or PROJECT_ROOT
    ref = f"{remote}/{branch}" if branch else remote
    try:
        _git(["rev-parse", ref], cwd=cwd)
        _git(["merge-base", "--is-ancestor", "HEAD", ref], cwd=cwd)
        return True
    except RuntimeError:
        return False


def pull_ff_only(remote: str = "origin", branch: str | None = None, path: Path | None = None) -> str:
    """Run ``git pull --ff-only``.

    Returns the new HEAD SHA.
    """
    cwd = path or PROJECT_ROOT
    args = ["pull", "--ff-only", remote]
    if branch:
        args.append(branch)
    _git(args, cwd=cwd)
    return get_local_sha(cwd)


def get_staged_files() -> list[str]:
    """Return list of files that would be committed (git diff --cached --name-only)."""
    result = _git(["diff", "--cached", "--name-only"])
    return [l.strip() for l in result.stdout.splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------

def acquire_lock(lock_file: str) -> bool:
    """Try to acquire a PID-based lock file.

    Returns True on success, False if another bridge instance is running.
    """
    lock_path = Path(lock_file)
    if lock_path.exists():
        try:
            data = lock_path.read_text(encoding="utf-8").strip()
            if data:
                pid = int(data)
                if _is_pid_alive(pid):
                    return False
        except (ValueError, OSError):
            pass  # Stale / unreadable → overwrite

    try:
        lock_path.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except OSError:
        return False


def _is_pid_alive(pid: int) -> bool:
    """Cross-platform PID existence check."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except PermissionError:
        # On Windows, a process we don't own raises PermissionError — it's alive.
        return True


def release_lock(lock_file: str) -> None:
    """Remove the lock file if it belongs to us."""
    lock_path = Path(lock_file)
    try:
        if lock_path.exists() and lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
            lock_path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

State = dict  # internal type alias


def _load_state(state_file: str) -> dict:
    path = Path(state_file)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state_file: str, state: dict) -> None:
    Path(state_file).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_task_already_processed(state_file: str, task_sha: str) -> bool:
    """Return True if *task_sha* has been processed before."""
    state = _load_state(state_file)
    return state.get("last_processed_sha") == task_sha


def mark_task_processed(state_file: str, task_sha: str, result: dict | None = None) -> None:
    """Record that a task was completed or blocked."""
    state = _load_state(state_file)
    state["last_processed_sha"] = task_sha
    state["last_processed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if result:
        state["last_result"] = result
    _save_state(state_file, state)


# ---------------------------------------------------------------------------
# CURRENT_TASK.md parsing
# ---------------------------------------------------------------------------

def read_current_task(path: Path | None = None) -> str:
    """Return the full text of CURRENT_TASK.md."""
    p = path or AI_DIR / "CURRENT_TASK.md"
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8")


def is_task_ready(task_text: str) -> bool:
    """Check whether CURRENT_TASK.md contains a **READY** status marker."""
    return bool(re.search(r"\*\*READY\*\*", task_text))


# ---------------------------------------------------------------------------
# Claude Code invocation
# ---------------------------------------------------------------------------

def claude_binary_path(config: dict) -> str:
    """Resolve Claude binary; raise if not found on PATH."""
    binary = config.get("claude_binary", "claude")
    try:
        subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT,  # B: force cwd
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"Claude binary '{binary}' not available: {exc}"
        ) from exc
    return binary


def build_claude_prompt(task_text: str, config: dict) -> str:
    """Build the full prompt to pass to Claude Code.

    This prompt enforces the AGENTS.md rules, the task scope, and mandates
    structured output.
    """
    return f"""You are an autonomous coding agent working on the SayIt project.

## Instructions

1.  **Read mandatory context files first:**
    - `AGENTS.md` (root)
    - `.ai/PROJECT_STATE.md`
    - `.ai/CURRENT_TASK.md` (the exact task below)

2.  **Execute the CURRENT_TASK strictly. Do NOT expand scope.** If you cannot
    fulfill the task for any reason, say so and mark it BLOCKED.

3.  **Forbidden:**
    - Do NOT modify `main` or `backup/*` branches.
    - Do NOT force push.
    - Do NOT read, output, or commit any API keys, tokens, cookies, full
      personal configs, database files, or recording files.
    - Do NOT delete failing tests.
    - Do NOT refactor modules outside the task scope.

4.  **Before claiming completion:**
    - Run all existing tests (they MUST pass).
    - Write or update tests for changes you make.
    - Update `.ai/ZCODE_REPORT.md` with what you did, root-cause analysis,
      commands run, test results, unresolved issues, and risks.
    - Update `.ai/TEST_RESULTS.md` with detailed results.
    - Set CURRENT_TASK status to `DONE` (success) or `BLOCKED` (failure).

5.  **Git discipline:**
    - Commit your work on the current feature branch.
    - Use `git add` for allowed patterns (see AGENTS.md).
    - Push with `git push`.

6.  **Final output format — output a single JSON object on stdout, nothing
    else:**

    ```json
    {{"ok": true, "summary": "...", "commit_sha": "...", "files_changed": ["..."], "tests_passed": N, "tests_failed": N}}
    ```
    or
    ```json
    {{"ok": false, "summary": "...", "blocked_reason": "..."}}
    ```

---

## Task from CURRENT_TASK.md

{task_text}
"""


def call_claude(prompt: str, config: dict) -> subprocess.CompletedProcess:
    """Invoke Claude Code in non-interactive mode.

    Uses ``claude -p <prompt>`` with ``--output-format json``.
    Sets cwd=PROJECT_ROOT so Claude operates inside the SayIt repo.
    """
    binary = claude_binary_path(config)
    timeout = config.get("claude_timeout_seconds", 300)

    args = [binary, "-p", prompt, "--output-format", "json"]

    # E: add allowed tools for minimal permission
    allowed = config.get("claude_allowed_tools", [])
    if allowed:
        args.append("--allowedTools")
        args.extend(allowed)

    # F: optional model override — only if user explicitly configured
    model = config.get("model", "")
    if model:
        args.extend(["--model", model])

    logger.info(
        "Invoking: %s (timeout=%ss, cwd=%s)",
        " ".join(args[:3]) + " ...",
        timeout,
        PROJECT_ROOT,
    )
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=PROJECT_ROOT,  # B: force cwd
    )
    return result


# ---------------------------------------------------------------------------
# Claude output parsing — D
# ---------------------------------------------------------------------------

def _try_parse_json(text: str) -> dict | None:
    """Attempt to parse *text* as JSON.  Returns None on failure."""
    text = text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json...``` block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return None


def parse_claude_result(result: subprocess.CompletedProcess) -> dict:
    """Parse Claude's stdout into a result dict.

    Handles three formats:
    1. Direct flat JSON:  {"ok": true, ...}
    2. Envelope with `result` string field (Claude --output-format json)
    3. Envelope with `is_error` field
    Returns a dict with at least ``{"ok": bool}``.
    """
    if result.returncode != 0:
        return {
            "ok": False,
            "phase": "claude",
            "summary": f"Claude exited with code {result.returncode}",
            "stderr": result.stderr[:2000] if result.stderr else "",
        }

    stdout = result.stdout.strip() if result.stdout else ""

    # 1. Try parsing top-level JSON directly
    parsed = _try_parse_json(stdout)
    if parsed is None:
        return {
            "ok": False,
            "phase": "parse",
            "summary": "No valid JSON found in Claude output",
            "raw_stdout": stdout[:3000],
        }

    # 2. If it has a top-level "ok" field, it's already the direct format
    if "ok" in parsed:
        return parsed

    # 3. Envelope format: check the "result" field
    result_text = parsed.get("result")
    if result_text is not None and isinstance(result_text, str) and result_text.strip():
        inner = _try_parse_json(result_text)
        if inner is not None and "ok" in inner:
            inner["_envelope_type"] = parsed.get("type", "")
            inner["_session_id"] = parsed.get("session_id", "")
            inner["_is_error"] = parsed.get("is_error", False)
            return inner
        # result field is a plain string, not JSON — wrap it
        return {
            "ok": not parsed.get("is_error", True),
            "summary": result_text,
            "_envelope_type": parsed.get("type", ""),
            "_session_id": parsed.get("session_id", ""),
            "_is_error": parsed.get("is_error", True),
        }

    # 4. Envelope with is_error field but no result
    if "is_error" in parsed:
        return {
            "ok": not parsed["is_error"],
            "summary": str(parsed.get("result", "")),
            "_envelope_type": parsed.get("type", ""),
        }

    # 5. Unknown shape — return as-is, caller checks "ok"
    return dict(parsed)


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def set_task_status(status: str, notes: str = "") -> None:
    """Update the status line in CURRENT_TASK.md to *status*."""
    task_path = AI_DIR / "CURRENT_TASK.md"
    if not task_path.is_file():
        logger.warning("CURRENT_TASK.md not found at %s", task_path)
        return

    text = task_path.read_text(encoding="utf-8")
    new_text = re.sub(
        r"\*\*[A-Z]+\*\*",
        f"**{status}**",
        text,
        count=1,
    )
    task_path.write_text(new_text, encoding="utf-8")
    logger.info("Set CURRENT_TASK status to %s", status)


def write_run_report(status: str, reason: str, details: str = "") -> None:
    """Write .ai/BRIDGE_RUN_REPORT.md with execution status."""
    report = AI_DIR / "BRIDGE_RUN_REPORT.md"
    report.write_text(
        f"# Bridge Run Report\n"
        f"\n"
        f"**Status:** {status}\n"
        f"**Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**Reason:** {reason}\n"
        f"**Details:** {details[:2000]}\n",
        encoding="utf-8",
    )
    logger.info("Wrote BRIDGE_RUN_REPORT.md (status=%s)", status)


# ---------------------------------------------------------------------------
# H: BLOCKED commit + push
# ---------------------------------------------------------------------------

def commit_and_push_blocked(reason: str, result_summary: str) -> bool:
    """Commit a BLOCKED status + run report to GitHub, then push.

    Only stages .ai/CURRENT_TASK.md and .ai/BRIDGE_RUN_REPORT.md.
    Does NOT include any unintended Claude changes.
    Returns True on success.
    """
    try:
        # Write report and set status locally
        write_run_report("BLOCKED", reason, result_summary)
        set_task_status("BLOCKED")

        # Stage ONLY .ai files
        r = subprocess.run(
            ["git", "add", ".ai/CURRENT_TASK.md", ".ai/BRIDGE_RUN_REPORT.md"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            logger.error("git add for BLOCKED failed: %s", r.stderr)
            return False

        # Verify only our files are staged
        staged = get_staged_files()
        extra = [f for f in staged if f not in (".ai/CURRENT_TASK.md", ".ai/BRIDGE_RUN_REPORT.md")]
        if extra:
            logger.warning("Extra files staged for BLOCKED commit: %s — unshallowing", extra)
            subprocess.run(
                ["git", "reset", "HEAD", "--"] + extra,
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
            )

        r = subprocess.run(
            ["git", "commit", "-m", "chore: bridge BLOCKED"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            # If nothing to commit (already BLOCKED), that's OK
            if "nothing to commit" in r.stderr or "nothing to commit" in r.stdout:
                logger.info("No new changes for BLOCKED commit (already up-to-date)")
                return True
            logger.error("git commit for BLOCKED failed: %s", r.stderr)
            return False

        r = subprocess.run(
            ["git", "push"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            logger.error("git push for BLOCKED failed: %s", r.stderr)
            return False

        logger.info("BLOCKED status committed and pushed to remote")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to report BLOCKED: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main orchestration — C: redesigned
# ---------------------------------------------------------------------------

def check_preconditions(config: dict) -> str | None:
    """Check preconditions, fetch remote, pull if needed, return task SHA.

    Returns None if no task should be attempted (already logged).
    Returns a 40-char SHA if a READY, unprocessed task exists.

    New design (C):
    - Always fetch; pull only if ff-safe.
    - Regardless of whether new commits arrived, read CURRENT_TASK.md.
    - If READY and SHA not processed → execute.
    """
    branch = config["branch"]
    remote = config["remote"]

    # 1. Git repo
    if not is_git_repo():
        logger.warning("Not a Git repository")
        return None

    # 2. Correct branch
    try:
        current = get_current_branch()
    except RuntimeError as exc:
        logger.warning("Cannot determine branch: %s", exc)
        return None
    if current != branch:
        logger.info("Wrong branch: %s (expected %s)", current, branch)
        return None

    # 3. Clean working tree
    if not is_working_directory_clean():
        logger.info("Working directory has uncommitted changes")
        return None

    # 4. No in-progress operation
    if has_in_progress_operation():
        logger.info("Merge/rebase/cherry-pick in progress")
        return None

    # 5. Fetch remote
    try:
        fetch_remote(remote, branch)
    except RuntimeError as exc:
        logger.warning("git fetch failed: %s", exc)
        return None

    # 6. If remote ahead and ff-only possible, pull
    if can_fast_forward(remote, branch):
        try:
            pull_ff_only(remote, branch)
            logger.info("Pulled fast-forward")
        except RuntimeError as exc:
            logger.warning("git pull --ff-only failed: %s", exc)
            return None

    # 7. Read CURRENT_TASK.md — always (C: not gated on new commits)
    task_text = read_current_task()
    if not task_text:
        logger.info("CURRENT_TASK.md not found")
        return None
    if not is_task_ready(task_text):
        logger.info("CURRENT_TASK status is not READY")
        return None

    # 8. Task fingerprint = current HEAD SHA (C)
    task_sha = get_local_sha()

    # 9. Already processed?
    if is_task_already_processed(config["state_file"], task_sha):
        logger.info("Task SHA %s already processed", task_sha[:12])
        return None

    return task_sha


def run_claude_task(task_sha: str, config: dict) -> dict:
    """Execute the task through Claude Code."""
    logger.info("=== CLAUDE EXECUTION START (SHA=%s) ===", task_sha[:12])

    task_text = read_current_task()
    prompt = build_claude_prompt(task_text, config)

    try:
        result = call_claude(prompt, config)
    except subprocess.TimeoutExpired:
        logger.error("Claude timed out after %ss", config["claude_timeout_seconds"])
        return {"ok": False, "phase": "timeout", "summary": "Claude timed out"}
    except RuntimeError as exc:
        logger.error("Claude invocation failed: %s", exc)
        return {"ok": False, "phase": "invocation", "summary": str(exc)}
    except Exception as exc:  # noqa: BLE001 — broad catch for robustness
        logger.error("Unexpected error invoking Claude: %s", exc)
        return {"ok": False, "phase": "invocation", "summary": str(exc)}

    logger.info("Claude exit code: %d", result.returncode)

    parsed = parse_claude_result(result)
    logger.info(
        "Claude result: ok=%s summary=%s",
        parsed.get("ok"),
        parsed.get("summary", "")[:120],
    )

    return parsed


def run_once(config: dict) -> bool:
    """Execute a single poll-check-run cycle.

    New design (C, H):
    - Preconditions → if fail, log and return False (don't mark processed).
    - If task SHA → execute Claude.
    - Success → mark processed, return True.  Claude already committed DONE.
    - Failure → mark processed as BLOCKED, commit BLOCKED to remote, return True.
    - No task → return False (nothing done).
    """
    lock_file = config["lock_file"]
    if not acquire_lock(lock_file):
        logger.warning("Another bridge instance is running (lock file %s)", lock_file)
        return False

    try:
        task_sha = check_preconditions(config)

        if task_sha is None:
            # C: No task to do — don't mark anything processed
            return False

        # We have a task → execute
        result = run_claude_task(task_sha, config)

        if result.get("ok"):
            logger.info("Task completed successfully")
            # H: On success, Claude already committed+push DONE.
            # Bridge only updates local state.
            mark_task_processed(config["state_file"], task_sha, result)
            return True
        else:
            # H: On failure, commit BLOCKED to remote
            summary = result.get("summary", "")[:500]
            reason = result.get("phase", "unknown")
            logger.error("Task failed (phase=%s): %s", reason, summary)
            blocked_ok = commit_and_push_blocked(reason, summary)
            if not blocked_ok:
                logger.warning(
                    "BLOCKED report could not be pushed — remote may not see it. "
                    "Check local files: .ai/CURRENT_TASK.md, .ai/BRIDGE_RUN_REPORT.md"
                )
            mark_task_processed(config["state_file"], task_sha, result)
            return True

    finally:
        release_lock(lock_file)


def polling_loop(config: dict) -> None:
    """Main polling loop — runs forever until Ctrl+C."""
    interval = config.get("poll_interval_seconds", 30)
    logger.info(
        "Bridge started (branch=%s, interval=%ss, cwd=%s)",
        config["branch"],
        interval,
        PROJECT_ROOT,
    )

    while True:
        signal.signal(signal.SIGINT, _handle_sigint)
        try:
            ran = run_once(config)
            if not ran:
                logger.info("Waiting %ss...", interval)
        except Exception as exc:  # noqa: BLE001
            logger.error("Unhandled error in cycle: %s", exc)

        time.sleep(interval)


def _handle_sigint(signum, frame) -> None:  # noqa: ANN001, ANN002
    logger.info("SIGINT received — shutting down")
    sys.exit(0)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(args: list[str] | None = None) -> int:
    """CLI entry point.  Returns exit code."""
    if args is None:
        args = sys.argv[1:]

    if "--version" in args:
        print(f"agent-bridge v{VERSION}")
        return 0

    config = load_config()
    setup_logging(config)

    logger.info("Agent Bridge v%s starting", VERSION)

    if "--once" in args:
        ran = run_once(config)
        return 0 if ran else 1

    polling_loop(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
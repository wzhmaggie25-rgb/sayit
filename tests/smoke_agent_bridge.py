"""Smoke test for the Agent Bridge — calls real Claude Code with a minimal task.

Run from project root:
    python tests/smoke_agent_bridge.py

This test:
1. Verifies correct branch and clean working directory
2. Launches Claude with a minimal, safe prompt
3. Verifies .ai/BRIDGE_SMOKE_TEST.md was created
4. Verifies a new commit exists
5. Verifies the commit was pushed
6. Returns non-zero on any failure
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI_DIR = ROOT / ".ai"
EXPECTED_FILE = AI_DIR / "BRIDGE_SMOKE_TEST.md"
EXPECTED_COMMIT_MSG = "test: bridge smoke test"
BRANCH = "feature/silent-learning-stabilization"
REMOTE = "origin"

PROMPT = (
    "You are running on the Sayit project ({branch} branch). "
    "Do ONLY this: update the file .ai/BRIDGE_SMOKE_TEST.md with the "
    "current timestamp and this exact sentence: 'Bridge smoke test passed at {now}'. "
    "Then git add .ai/BRIDGE_SMOKE_TEST.md, "
    "git commit -m '{commit_msg}', and git push. "
    "Do NOT modify any other file. "
    "Output a single JSON object at the end: "
    '{{"ok": true, "commit_sha": "<sha>"}}'
).format(
    branch=BRANCH,
    now=time.strftime("%Y-%m-%d %H:%M:%S"),
    commit_msg=EXPECTED_COMMIT_MSG,
)


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )


def main() -> int:
    failures = []

    def fail(msg: str) -> None:
        print(f"❌ {msg}")
        failures.append(msg)

    def ok(msg: str) -> None:
        print(f"✅ {msg}")

    print("=" * 60)
    print("Agent Bridge — Claude Smoke Test (v0.2.0)")
    print("=" * 60)

    # --- Pre-conditions ---
    print(f"\n* Project root: {ROOT}")

    # Branch check
    r = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    branch = r.stdout.strip()
    print(f"  Branch: {branch}")
    if branch != BRANCH:
        fail(f"Wrong branch: {branch} (expected {BRANCH})")
    else:
        ok(f"On branch {BRANCH}")

    # Clean working directory
    r = _run_git(["status", "--porcelain"])
    if r.stdout.strip():
        fail("Working directory has uncommitted changes")
    else:
        ok("Working directory clean")

    # No in-progress operations
    git_dir = ROOT / ".git"
    markers = ["MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "BISECT_LOG"]
    in_progress = any((git_dir / m).exists() for m in markers)
    if in_progress:
        fail("Git operation in progress (merge/rebase/cherry-pick)")
    else:
        ok("No in-progress git operations")

    # --- Claude availability ---
    try:
        r = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10, cwd=ROOT,
        )
        claude_version = r.stdout.strip()
        print(f"  Claude version: {claude_version}")
    except (FileNotFoundError, OSError) as exc:
        fail(f"Claude not available: {exc}")
        print(f"\n{len(failures)} failure(s) — aborting")
        return 1
    except subprocess.TimeoutExpired:
        fail("Claude --version timed out")
        return 1

    # --- Remove old smoke file if exists ---
    if EXPECTED_FILE.is_file():
        EXPECTED_FILE.unlink()
        ok("Removed previous BRIDGE_SMOKE_TEST.md")

    # --- Record SHA before ---
    sha_before = _run_git(["rev-parse", "HEAD"]).stdout.strip()

    # --- Invoke Claude ---
    print(f"\nInvoking Claude Code (non-interactive)...")
    print(f"  cwd: {ROOT}")
    t0 = time.monotonic()
    try:
        # Allowed tools must match what the bridge + config grant
        _ALLOWED = [
            "Read", "Edit", "Write",
            "Bash(git*)", "Bash(python*)", "Bash(pytest*)",
        ]
        result = subprocess.run(
            ["claude", "-p", PROMPT, "--output-format", "json",
             "--allowedTools"] + _ALLOWED,
            capture_output=True, text=True, timeout=120, cwd=ROOT,
        )
    except subprocess.TimeoutExpired:
        fail("Claude timed out after 120s")
        return 1

    elapsed = time.monotonic() - t0
    print(f"  Exit code: {result.returncode} (elapsed: {elapsed:.1f}s)")

    if result.returncode != 0:
        fail(f"Claude exited with code {result.returncode}")
        stderr = result.stderr[:1500] if result.stderr else ""
        print(f"  stderr: {stderr}")
    else:
        ok(f"Claude exit code 0")

    # Print raw output (redacted — no secrets)
    stdout_safe = result.stdout[:2000] if result.stdout else ""
    stderr_safe = result.stderr[:1000] if result.stderr else ""
    if stdout_safe:
        # Redact session_id and uuid
        safe = re.sub(r'"(session_id|uuid)"\s*:\s*"[^"]+"', r'"\1":"<redacted>"', stdout_safe)
        print(f"  stdout:\n{safe}")
    if stderr_safe:
        print(f"  stderr:\n{stderr_safe}")

    # --- Verify file was created ---
    if EXPECTED_FILE.is_file():
        ok(f"BRIDGE_SMOKE_TEST.md created ({EXPECTED_FILE.stat().st_size} bytes)")
        content = EXPECTED_FILE.read_text(encoding="utf-8")
        if "smoke test passed" in content.lower():
            ok("File contains expected content")
        else:
            fail("File content unexpected")
            print(f"  First 300 chars: {content[:300]}")
    else:
        fail(f"BRIDGE_SMOKE_TEST.md not found at {EXPECTED_FILE}")

    # --- Verify new commit ---
    sha_after = _run_git(["rev-parse", "HEAD"]).stdout.strip()
    if sha_after != sha_before:
        ok(f"New commit: {sha_after[:12]}")
        # Verify commit message
        r = _run_git(["log", "--format=%s", "-1"])
        commit_msg = r.stdout.strip()
        if commit_msg == EXPECTED_COMMIT_MSG:
            ok(f"Commit message matches: '{commit_msg}'")
        else:
            fail(f"Commit message mismatch: '{commit_msg}' (expected '{EXPECTED_COMMIT_MSG}')")
    else:
        fail("No new commit created")

    # --- Verify push ---
    r = _run_git(["rev-parse", f"{REMOTE}/{BRANCH}"])
    remote_sha = r.stdout.strip()
    if remote_sha == sha_after:
        ok(f"Commit pushed to {REMOTE}/{BRANCH}")
    elif remote_sha == sha_before:
        fail("Commit not pushed (remote SHA matches previous HEAD)")
    else:
        # Could be intermediate push — use git branch -r to verify
        fail("Push verification ambiguous")

    # --- Verify only the allowed file was changed ---
    r = _run_git(["diff", "--name-only", sha_before, sha_after])
    changed = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    extra = [f for f in changed if f != ".ai/BRIDGE_SMOKE_TEST.md"]
    if extra:
        fail(f"Unexpected files changed: {extra}")
    else:
        ok("Only .ai/BRIDGE_SMOKE_TEST.md was changed")

    # --- Parse Claude's JSON output ---
    if result.stdout:
        try:
            parsed = json.loads(result.stdout.strip())
            parsed_ok = parsed.get("ok", False) or not parsed.get("is_error", True)
            if parsed_ok:
                ok("Claude output indicates success")
            else:
                fail(f"Claude output indicates failure: {parsed.get('result', parsed)}")
        except json.JSONDecodeError:
            # Try envelope extraction
            try:
                inner = json.loads(result.stdout.strip())
                if isinstance(inner, dict) and inner.get("result"):
                    parsed_ok = not inner.get("is_error", True)
                    if parsed_ok:
                        ok("Claude envelope output indicates success")
                    else:
                        fail(f"Claude envelope indicates failure: {inner.get('result', '')[:200]}")
                else:
                    fail("Could not parse Claude output as expected JSON")
            except json.JSONDecodeError:
                fail("Could not parse Claude output as JSON")

    print(f"\nResults: {len(failures)} failure(s)")
    for f in failures:
        print(f"  ❌ {f}")

    if failures:
        print("\n❌ SMOKE TEST FAILED")
        return 1
    else:
        print("\n✅ SMOKE TEST PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
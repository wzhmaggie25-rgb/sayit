"""Smoke test for the Agent Bridge — calls real Claude Code with a minimal task.

Run from project root:
    python tests/smoke_agent_bridge.py

This test:
1. Launches Claude with ``-p "Only update .ai/BRIDGE_SMOKE_TEST.md with the
   current timestamp, then commit and push."``
2. Verifies BRIDGE_SMOKE_TEST.md was created
3. Verifies a new commit exists
4. Does NOT modify any SayIt business code
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI_DIR = ROOT / ".ai"

PROMPT = (
    "You are running on the SayIt project (feature/silent-learning-stabilization branch). "
    "Do ONLY this: update the file .ai/BRIDGE_SMOKE_TEST.md with the "
    "current timestamp and this exact sentence: 'Bridge smoke test passed at {now}'. "
    "Then git add .ai/BRIDGE_SMOKE_TEST.md, "
    "git commit -m 'test: bridge smoke test', and git push. "
    "Do NOT modify any other file. "
    "Output a single JSON object at the end: "
    '{{"ok": true, "commit_sha": "<sha>"}}'
).format(now=time.strftime("%Y-%m-%d %H:%M:%S"))


def main() -> int:
    print("=" * 60)
    print("Agent Bridge — Claude Smoke Test")
    print("=" * 60)
    print(f"Project root: {ROOT}")
    print(f"Prompt: {PROMPT[:120]}...")
    print()

    # 1. Check Claude is available
    try:
        r = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        print(f"Claude version: {r.stdout.strip()}")
    except (FileNotFoundError, OSError) as exc:
        print(f"FATAL: Claude not available: {exc}")
        return 1

    # 2. Record SHA before
    sha_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()

    # 3. Invoke Claude
    print("\nInvoking Claude Code (non-interactive)...")
    t0 = time.monotonic()
    result = subprocess.run(
        ["claude", "-p", PROMPT, "--output-format", "json"],
        capture_output=True, text=True, timeout=120,
    )
    elapsed = time.monotonic() - t0
    print(f"Claude exited in {elapsed:.1f}s, code={result.returncode}")

    # 4. Print output
    if result.stdout:
        print(f"stdout:\n{result.stdout[:2000]}")
    if result.stderr:
        print(f"stderr:\n{result.stderr[:1000]}")

    # 5. Verify file was created
    smoke_file = AI_DIR / "BRIDGE_SMOKE_TEST.md"
    if smoke_file.is_file():
        print(f"\n✅ BRIDGE_SMOKE_TEST.md created ({smoke_file.stat().st_size} bytes)")
        print(f"Content:\n{smoke_file.read_text(encoding='utf-8')[:500]}")
    else:
        print(f"\n❌ BRIDGE_SMOKE_TEST.md not found at {smoke_file}")

    # 6. Verify new commit
    sha_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()
    if sha_after != sha_before:
        print(f"✅ New commit: {sha_after[:12]}")
    else:
        print("❌ No new commit")

    # 7. Parse JSON if present
    if result.stdout:
        try:
            parsed = json.loads(result.stdout.strip())
            print(f"\nParsed result: ok={parsed.get('ok')}, sha={parsed.get('commit_sha', 'N/A')[:12]}")
        except json.JSONDecodeError:
            print("\n⚠ Could not parse Claude output as JSON")

    print("\nSmoke test complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
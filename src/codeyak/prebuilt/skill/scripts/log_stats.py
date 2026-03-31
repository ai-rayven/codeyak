#!/usr/bin/env python3
"""
Logs codeyak review results as a JSONL record for trend tracking.

Reads JSON from stdin (output of yak review --json) and appends
a stats record to data/stats.jsonl.

Works cross-platform (Windows, macOS, Linux).
"""

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DATA_DIR = SKILL_DIR / "data"
STATS_FILE = DATA_DIR / "stats.jsonl"


def get_git_info():
    """Get current git SHA and branch name."""
    git_sha = ""
    git_branch = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            git_sha = result.stdout.strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            git_branch = result.stdout.strip()
    except Exception:
        pass

    return git_sha, git_branch


def main():
    # Read JSON from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        print("WARNING: No input received", file=sys.stderr)
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"WARNING: Invalid JSON input: {e}", file=sys.stderr)
        return

    violations = data.get("violations", [])

    # Count violations by guideline_id
    violation_counts = Counter()
    high_confidence_count = 0
    files_with_violations = set()

    for v in violations:
        gid = v.get("guideline_id", "unknown")
        violation_counts[gid] += 1
        if v.get("confidence") == "high":
            high_confidence_count += 1
        if v.get("file_path"):
            files_with_violations.add(v["file_path"])

    git_sha, git_branch = get_git_info()

    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha,
        "git_branch": git_branch,
        "files_reviewed": sorted(files_with_violations),
        "violation_counts": dict(violation_counts),
        "total_violations": len(violations),
        "total_high_confidence": high_confidence_count,
    }

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Append record
    with open(STATS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    print(f"Stats logged to {STATS_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()

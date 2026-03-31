#!/usr/bin/env python3
"""
Orchestrator script for codeyak review within Claude Code skill.

Runs yak review --json, logs stats, and outputs results.
Works cross-platform (Windows, macOS, Linux).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# Resolve paths relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DATA_DIR = SKILL_DIR / "data"
LOG_STATS_SCRIPT = SCRIPT_DIR / "log_stats.py"
SHOW_TRENDS_SCRIPT = SCRIPT_DIR / "show_trends.py"


def main():
    # Check that yak is installed
    yak_path = shutil.which("yak")
    if yak_path is None:
        print("ERROR: 'yak' is not installed or not on PATH.", file=sys.stderr)
        print("Install it with: pip install codeyak", file=sys.stderr)
        print("Or: uv tool install codeyak", file=sys.stderr)
        sys.exit(1)

    # Build command: yak review --json + any forwarded arguments
    cmd = [yak_path, "review", "--json"] + sys.argv[1:]

    # Run yak review --json
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Forward stderr (progress output) to stderr
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    if result.returncode != 0:
        print(f"ERROR: yak review exited with code {result.returncode}", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        sys.exit(result.returncode)

    # Output the JSON to stdout for Claude to read
    json_output = result.stdout.strip()
    if json_output:
        print(json_output)

        # Log stats
        try:
            log_result = subprocess.run(
                [sys.executable, str(LOG_STATS_SCRIPT)],
                input=json_output,
                capture_output=True,
                text=True,
            )
            if log_result.stderr:
                print(log_result.stderr, file=sys.stderr, end="")
        except Exception as e:
            print(f"WARNING: Failed to log stats: {e}", file=sys.stderr)

        # Show brief trend
        try:
            trend_result = subprocess.run(
                [sys.executable, str(SHOW_TRENDS_SCRIPT), "--brief"],
                capture_output=True,
                text=True,
            )
            if trend_result.stdout.strip():
                print(f"\n[TREND] {trend_result.stdout.strip()}")
        except Exception:
            pass  # Trends are optional


if __name__ == "__main__":
    main()

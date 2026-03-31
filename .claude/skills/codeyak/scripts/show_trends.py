#!/usr/bin/env python3
"""
Displays codeyak violation trend data from stats.jsonl.

Supports:
  --brief: One-line summary
  --full:  Detailed breakdown by label with trend direction (default)

Works cross-platform (Windows, macOS, Linux).
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DATA_DIR = SKILL_DIR / "data"
STATS_FILE = DATA_DIR / "stats.jsonl"

# How many recent runs to use for trend comparison
TREND_WINDOW = 5


def load_records(max_records=100):
    """Load the most recent records from stats.jsonl."""
    if not STATS_FILE.exists():
        return []

    records = []
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Return only the most recent records
    return records[-max_records:]


def compute_trend_pct(recent_avg, previous_avg):
    """Compute percentage change. Negative = improvement."""
    if previous_avg == 0:
        if recent_avg == 0:
            return 0.0
        return 100.0  # went from 0 to something
    return ((recent_avg - previous_avg) / previous_avg) * 100


def brief_summary(records):
    """Print a one-line trend summary."""
    if not records:
        print("No review data yet.")
        return

    total_runs = len(records)
    total_violations = sum(r.get("total_violations", 0) for r in records)
    avg_violations = total_violations / total_runs if total_runs > 0 else 0

    if total_runs >= TREND_WINDOW * 2:
        recent = records[-TREND_WINDOW:]
        previous = records[-(TREND_WINDOW * 2):-TREND_WINDOW]
        recent_avg = sum(r.get("total_violations", 0) for r in recent) / len(recent)
        prev_avg = sum(r.get("total_violations", 0) for r in previous) / len(previous)
        pct = compute_trend_pct(recent_avg, prev_avg)
        if pct < -5:
            trend = f"improving ({pct:+.0f}%)"
        elif pct > 5:
            trend = f"worsening ({pct:+.0f}%)"
        else:
            trend = "stable"
    elif total_runs >= 2:
        first_half = records[:total_runs // 2]
        second_half = records[total_runs // 2:]
        first_avg = sum(r.get("total_violations", 0) for r in first_half) / len(first_half)
        second_avg = sum(r.get("total_violations", 0) for r in second_half) / len(second_half)
        pct = compute_trend_pct(second_avg, first_avg)
        if pct < -5:
            trend = f"improving ({pct:+.0f}%)"
        elif pct > 5:
            trend = f"worsening ({pct:+.0f}%)"
        else:
            trend = "stable"
    else:
        trend = "not enough data"

    print(f"{total_runs} reviews tracked. Avg {avg_violations:.1f} violations/review. Trend: {trend}")


def full_report(records):
    """Print a detailed trend report."""
    if not records:
        print("No review data yet. Run /codeyak to start tracking violations.")
        return

    total_runs = len(records)
    total_violations = sum(r.get("total_violations", 0) for r in records)
    total_high = sum(r.get("total_high_confidence", 0) for r in records)
    avg_violations = total_violations / total_runs

    print(f"=== Codeyak Violation Trends ===")
    print(f"Total reviews: {total_runs}")
    print(f"Total violations: {total_violations} ({total_high} high-confidence)")
    print(f"Average violations per review: {avg_violations:.1f}")
    print()

    # Per-label breakdown
    all_labels = Counter()
    recent_labels = Counter()
    previous_labels = Counter()

    for r in records:
        for label, count in r.get("violation_counts", {}).items():
            all_labels[label] += count

    if total_runs >= TREND_WINDOW * 2:
        for r in records[-TREND_WINDOW:]:
            for label, count in r.get("violation_counts", {}).items():
                recent_labels[label] += count
        for r in records[-(TREND_WINDOW * 2):-TREND_WINDOW]:
            for label, count in r.get("violation_counts", {}).items():
                previous_labels[label] += count

    print(f"{'Label':<45} {'Total':>6} {'Trend':>12}")
    print("-" * 65)

    for label, count in all_labels.most_common():
        if total_runs >= TREND_WINDOW * 2:
            recent_avg = recent_labels.get(label, 0) / TREND_WINDOW
            prev_avg = previous_labels.get(label, 0) / TREND_WINDOW
            pct = compute_trend_pct(recent_avg, prev_avg)
            if pct < -5:
                trend_str = f"v {pct:+.0f}%"
            elif pct > 5:
                trend_str = f"^ {pct:+.0f}%"
            else:
                trend_str = "stable"
        else:
            trend_str = "-"

        print(f"{label:<45} {count:>6} {trend_str:>12}")

    print()

    # Recent history
    print("Recent reviews:")
    for r in records[-5:]:
        ts = r.get("timestamp", "?")[:16]
        branch = r.get("git_branch", "?")
        total = r.get("total_violations", 0)
        high = r.get("total_high_confidence", 0)
        print(f"  {ts}  branch={branch}  violations={total} (high={high})")


def main():
    parser = argparse.ArgumentParser(description="Show codeyak violation trends")
    parser.add_argument("--brief", action="store_true", help="One-line summary")
    parser.add_argument("--full", action="store_true", help="Detailed report (default)")
    args = parser.parse_args()

    records = load_records()

    if args.brief:
        brief_summary(records)
    else:
        full_report(records)


if __name__ == "__main__":
    main()

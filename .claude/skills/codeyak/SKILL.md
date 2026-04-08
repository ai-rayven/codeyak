---
name: codeyak
description: Run codeyak AI code review on local changes and track violation trends over time. Use when asked to review code quality, check for bugs, or run codeyak.
disable-model-invocation: true
argument-hint: "[--trends] [--exclude <pattern>] [--path <dir>]"
---

# Codeyak Code Review

Run an AI-powered code review on local uncommitted changes and track violation statistics over time.

## Usage

### Review code (default)
Run `python` with the script path `.claude/skills/codeyak/scripts/run_review.py` followed by any extra arguments from `$ARGUMENTS` (excluding `--trends`).

Example:
```
python .claude/skills/codeyak/scripts/run_review.py
python .claude/skills/codeyak/scripts/run_review.py --exclude 'tests/'
python .claude/skills/codeyak/scripts/run_review.py --path /some/repo
```

### View trends
If `$ARGUMENTS` contains `--trends`, run:
```
python .claude/skills/codeyak/scripts/show_trends.py --full
```

## Presenting Results

After running a review:
1. Parse the JSON output from stdout
2. Present violations to the user grouped by file, showing:
   - File path and line number
   - Guideline ID (e.g., `security/sql-injection`)
   - Confidence level
   - Reasoning and suggested fix if available
3. If trend data is available at the end of the output (lines starting with `[TREND]`), mention the trend direction to the user

After showing trends:
1. Present the trend data in a clear table or summary format
2. Highlight labels that are improving (decreasing) or worsening (increasing)
3. Note the overall trend direction

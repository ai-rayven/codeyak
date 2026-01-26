"""
Entry point for running codeyak as a module.

Supports both the new CLI interface and backwards-compatible direct invocation:
    python -m codeyak review              # New: local review
    python -m codeyak mr <MR_ID> [PROJECT_ID]  # New: MR review
    python -m codeyak <MR_ID> [PROJECT_ID]     # Legacy: MR review
"""

import sys


def main():
    """Entry point that handles both CLI and legacy invocation."""
    # Check if using legacy invocation (first arg is a number = MR_ID)
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        # Legacy mode: convert to new CLI format
        # python -m codeyak <MR_ID> [PROJECT_ID] -> yak mr <MR_ID> [PROJECT_ID]
        sys.argv = [sys.argv[0], "mr"] + sys.argv[1:]

    # Import and run CLI
    from .apps.cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()

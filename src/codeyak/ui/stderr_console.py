"""
Stderr Rich console instance for JSON output mode.

When --json is used, all Rich output (banners, spinners, progress)
must go to stderr so stdout contains only clean JSON.
"""

import sys

from rich.console import Console

from .console import CODEYAK_THEME

# Console that writes to stderr instead of stdout
stderr_console = Console(theme=CODEYAK_THEME, file=sys.stderr)

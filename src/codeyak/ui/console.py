"""
Shared Rich console instance with CodeYak brand theme.
"""

from rich.console import Console
from rich.theme import Theme

# CodeYak brand theme
CODEYAK_THEME = Theme({
    "brand": "#A0522D",           # Brown - headers, branding
    "success": "#CD853F",         # Green - checkmark color
    "warning": "yellow",          # Yellow - from code highlights
    "error": "red bold",          # Red - errors
    "info": "white",               # Cyan - from tablet code
    "filepath": "#CD853F",        # Peru/tan - file paths
    "line_number": "white",        # Cyan - line numbers
    "guideline": "#DEB887",       # Burlywood - guideline IDs
    "muted": "dim",               # Dimmed text
    # Rich progress bar style overrides
    "progress.spinner": "#A0522D",
    "progress.percentage": "#CD853F",
    "bar.complete": "#A0522D",
    "bar.finished": "#CD853F",
    "progress.elapsed": "dim",
})

# Brand border style for panels and rules
BRAND_BORDER = "#A0522D"

# Shared console instance
console = Console(theme=CODEYAK_THEME)

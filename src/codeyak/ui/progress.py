"""
Progress reporter implementations for different output contexts.

Provides three implementations:
- RichProgressReporter: Interactive terminal with spinners, colors, progress bars
- CIProgressReporter: CI-friendly with simple lines, no spinners/ANSI
- NullProgressReporter: Silent for tests
"""

from typing import Any

from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.text import Text

from .console import console, BRAND_BORDER


class RichProgressReporter:
    """
    Interactive terminal reporter using Rich library.

    Provides spinners, colors, and progress bars for a rich CLI experience.
    """

    def __init__(self):
        self._progress: Progress | None = None
        self._status: Any = None

    def banner(self, name: str, version: str) -> None:
        """Display a styled application banner."""
        title = Text()
        title.append(name, style="bold #A0522D")
        title.append(f" v{version}", style="dim")
        panel = Panel(
            title,
            border_style=BRAND_BORDER,
            padding=(0, 2),
        )
        console.print(panel)

    def info(self, message: str) -> None:
        """Display an informational message."""
        console.print(f"[info]{message}[/info]")

    def warning(self, message: str) -> None:
        """Display a warning message."""
        console.print(f"[warning]{message}[/warning]")

    def success(self, message: str) -> None:
        """Display a success message."""
        console.print(f"[success]{message}[/success]")

    def start_progress(self, description: str, total: int) -> Any:
        """Start a progress bar and return a task handle."""
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style=BRAND_BORDER),
            TaskProgressColumn(),
            console=console,
        )
        self._progress.start()
        task = self._progress.add_task(f"[info]{description}[/info]", total=total)
        return task

    def update_progress(self, task: Any, description: str) -> None:
        """Update the description of a progress task."""
        if self._progress:
            self._progress.update(task, description=f"[info]{description}[/info]")

    def advance_progress(self, task: Any) -> None:
        """Advance the progress bar by one step."""
        if self._progress:
            self._progress.advance(task)

    def stop_progress(self) -> None:
        """Stop and clean up the progress bar."""
        if self._progress:
            self._progress.stop()
            self._progress = None

    def start_status(self, message: str) -> Any:
        """Start a status spinner and return a context handle."""
        self._status = console.status(f"[info]{message}[/info]", spinner="dots")
        self._status.start()
        return self._status

    def stop_status(self) -> None:
        """Stop the status spinner."""
        if self._status:
            self._status.stop()
            self._status = None


class CIProgressReporter:
    """
    CI-friendly reporter with simple line output.

    Uses plain print() without ANSI codes or spinners for compatibility
    with CI/CD systems like GitLab CI, GitHub Actions, etc.
    """

    def banner(self, name: str, version: str) -> None:
        """Display a simple text banner."""
        print(f"=== {name} v{version} ===")

    def info(self, message: str) -> None:
        """Display an informational message."""
        print(f"[INFO] {message}")

    def warning(self, message: str) -> None:
        """Display a warning message."""
        print(f"[WARNING] {message}")

    def success(self, message: str) -> None:
        """Display a success message."""
        print(f"[SUCCESS] {message}")

    def start_progress(self, description: str, total: int) -> Any:
        """Start a progress bar (just prints the description in CI mode)."""
        print(f"[INFO] {description} (0/{total})")
        return {"description": description, "total": total, "current": 0}

    def update_progress(self, task: Any, description: str) -> None:
        """Update the description of a progress task."""
        if isinstance(task, dict):
            task["description"] = description
            print(f"[INFO] {description}")

    def advance_progress(self, task: Any) -> None:
        """Advance the progress bar by one step."""
        if isinstance(task, dict):
            task["current"] += 1
            print(f"[INFO] {task['description']} ({task['current']}/{task['total']})")

    def stop_progress(self) -> None:
        """Stop and clean up the progress bar (no-op in CI mode)."""
        pass

    def start_status(self, message: str) -> Any:
        """Start a status spinner (just prints the message in CI mode)."""
        print(f"[INFO] {message}")
        return None

    def stop_status(self) -> None:
        """Stop the status spinner (no-op in CI mode)."""
        pass


class NullProgressReporter:
    """
    Silent reporter for tests.

    All methods are no-ops, useful for unit testing business logic
    without any console output.
    """

    def banner(self, name: str, version: str) -> None:
        """No-op."""
        pass

    def info(self, message: str) -> None:
        """No-op."""
        pass

    def warning(self, message: str) -> None:
        """No-op."""
        pass

    def success(self, message: str) -> None:
        """No-op."""
        pass

    def start_progress(self, description: str, total: int) -> Any:
        """No-op, returns None."""
        return None

    def update_progress(self, task: Any, description: str) -> None:
        """No-op."""
        pass

    def advance_progress(self, task: Any) -> None:
        """No-op."""
        pass

    def stop_progress(self) -> None:
        """No-op."""
        pass

    def start_status(self, message: str) -> Any:
        """No-op, returns None."""
        return None

    def stop_status(self) -> None:
        """No-op."""
        pass

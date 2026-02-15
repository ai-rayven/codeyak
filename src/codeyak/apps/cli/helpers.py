import sys

import click

from ...config import (
    is_gitlab_configured,
    is_llm_configured,
    config_file_exists,
)
from .configure import run_full_init, run_gitlab_init, run_llm_init
from ...ui import console


def ensure_llm_configured() -> None:
    """Ensure LLM (Azure OpenAI) is configured. Triggers init if not."""
    if is_llm_configured():
        return

    # Check if this is a CI/CD environment (no TTY)
    if not sys.stdin.isatty():
        click.echo(
            "Error: Azure OpenAI is not configured. "
            "Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT environment variables.",
            err=True,
        )
        sys.exit(1)

    # First time setup - no config file exists
    if not config_file_exists():
        run_full_init(include_gitlab=False)
    else:
        # Config file exists but LLM not configured
        console.print()
        console.print("[info]LLM provider is not configured. Let's set it up![/info]")
        run_llm_init()
        console.print()
        console.print("[info]Continuing with your command...[/info]")
        console.print()


def ensure_gitlab_configured() -> None:
    """Ensure GitLab is configured. Triggers init if not."""
    # First ensure LLM is configured
    ensure_llm_configured()

    if is_gitlab_configured():
        return

    # Check if this is a CI/CD environment (no TTY)
    if not sys.stdin.isatty():
        click.echo(
            "Error: GitLab is not configured. "
            "Set GITLAB_TOKEN environment variable.",
            err=True,
        )
        sys.exit(1)

    # First time setup - no config file exists
    if not config_file_exists():
        run_full_init(include_gitlab=True)
    else:
        # Config file exists but GitLab not configured
        console.print()
        console.print(
            "[info]GitLab integration is not configured. Let's set it up![/info]"
        )
        run_gitlab_init()
        console.print()
        console.print("[info]Continuing with your command...[/info]")
        console.print()

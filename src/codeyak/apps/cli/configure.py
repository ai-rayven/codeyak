"""
Interactive init flow for CodeYak configuration.

This module provides functions to interactively configure CodeYak settings
when users run commands without having configured the tool first.
"""

import os
import tomllib
from pathlib import Path

import click
import tomli_w
from rich.panel import Panel

from ...config import get_config_path, reset_settings
from ...ui import console, BRAND_BORDER


def _show_key_feedback(key: str, label: str) -> None:
    """Show feedback about entered key without revealing it."""
    if not key:
        console.print(f"  [warning]Warning: No {label} was entered[/warning]")
    elif len(key) < 10:
        console.print(f"  [success]{label} entered[/success] [muted]({len(key)} characters)[/muted]")
    else:
        # Show first 4 and last 4 chars for verification
        masked = f"{key[:4]}...{key[-4:]}"
        console.print(f"  [success]{label} entered:[/success] {masked} [muted]({len(key)} characters)[/muted]")


def _load_existing_config() -> dict:
    """Load existing config if it exists, otherwise return empty dict."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    return {}


def _save_config(config: dict) -> None:
    """Save config to TOML file with restrictive permissions."""
    config_path = get_config_path()

    # Create parent directories if needed
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write config with restrictive permissions (owner read/write only)
    with open(config_path, "wb") as f:
        tomli_w.dump(config, f)

    # Set file permissions to 600 (owner read/write only)
    os.chmod(config_path, 0o600)


def run_llm_init() -> None:
    """Run interactive init flow for LLM (Azure OpenAI) configuration only."""
    console.print()
    console.print(Panel(
        "[brand]LLM Provider[/brand]",
        border_style=BRAND_BORDER,
        padding=(0, 2)
    ))
    console.print("Available providers:")
    console.print("  1. Azure OpenAI")
    console.print()

    # Azure OpenAI Endpoint
    console.print("  [muted]Example: https://your-resource.openai.azure.com/[/muted]")
    endpoint = click.prompt("  Azure OpenAI Endpoint", type=str)

    # API Key
    console.print()
    console.print("  [muted]Found in Azure Portal > Your OpenAI Resource > Keys and Endpoint[/muted]")
    api_key = click.prompt("  Azure OpenAI API Key", type=str, hide_input=True)
    _show_key_feedback(api_key, "API Key")

    # Deployment Name
    console.print()
    deployment_name = click.prompt(
        "  Deployment Name", type=str, default="gpt-4o", show_default=True
    )

    # API Version
    api_version = click.prompt(
        "  API Version", type=str, default="2024-02-15-preview", show_default=True
    )

    # Load existing config and update with new values
    config = _load_existing_config()
    config["AZURE_OPENAI_ENDPOINT"] = endpoint
    config["AZURE_OPENAI_API_KEY"] = api_key
    config["AZURE_DEPLOYMENT_NAME"] = deployment_name
    config["AZURE_OPENAI_API_VERSION"] = api_version

    _save_config(config)
    reset_settings()

    config_path = get_config_path()
    console.print()
    console.print(f"[success]Configuration saved to {config_path}[/success]")


def run_gitlab_init() -> None:
    """Run interactive init flow for GitLab configuration only."""
    console.print()
    console.print(Panel(
        "[brand]GitLab Configuration[/brand]",
        border_style=BRAND_BORDER,
        padding=(0, 2)
    ))

    # GitLab URL
    gitlab_url = click.prompt(
        "  GitLab URL", type=str, default="https://gitlab.com", show_default=True
    )

    # GitLab Token
    console.print()
    console.print("  [muted]Personal Access Token (create at GitLab > Settings > Access Tokens)[/muted]")
    gitlab_token = click.prompt("  GitLab Token", type=str, hide_input=True)
    _show_key_feedback(gitlab_token, "Token")

    # Load existing config and update with new values
    config = _load_existing_config()
    config["GITLAB_URL"] = gitlab_url
    config["GITLAB_TOKEN"] = gitlab_token

    _save_config(config)
    reset_settings()

    console.print()
    console.print(f"[success]Configuration saved to {get_config_path()}[/success]")


def run_langfuse_init() -> None:
    """Run interactive init flow for Langfuse configuration only."""
    console.print()
    console.print(Panel(
        "[brand]Langfuse Configuration (Optional)[/brand]",
        border_style=BRAND_BORDER,
        padding=(0, 2)
    ))
    console.print("  [muted]Langfuse provides observability for your LLM calls.[/muted]")
    console.print()

    # Secret Key
    secret_key = click.prompt("  Langfuse Secret Key", type=str, hide_input=True)
    _show_key_feedback(secret_key, "Secret Key")

    # Public Key
    public_key = click.prompt("  Langfuse Public Key", type=str)

    # Host
    host = click.prompt(
        "  Langfuse Host",
        type=str,
        default="https://cloud.langfuse.com",
        show_default=True,
    )

    # Load existing config and update with new values
    config = _load_existing_config()
    config["LANGFUSE_SECRET_KEY"] = secret_key
    config["LANGFUSE_PUBLIC_KEY"] = public_key
    config["LANGFUSE_HOST"] = host

    _save_config(config)
    reset_settings()

    console.print()
    console.print(f"[success]Configuration saved to {get_config_path()}[/success]")


def run_full_init(include_gitlab: bool = False) -> None:
    """
    Run the complete first-time setup flow.

    Args:
        include_gitlab: If True, also prompt for GitLab configuration.
    """
    console.print()
    console.print("[info]Looks like you haven't configured CodeYak yet. Let's get you set up![/info]")

    # Always configure LLM
    run_llm_init()

    # Optionally configure GitLab
    if include_gitlab:
        run_gitlab_init()

    # Ask about Langfuse
    console.print()
    if click.confirm("Would you like to configure Langfuse for observability?", default=False):
        run_langfuse_init()

    console.print()
    console.print("[info]Continuing with your command...[/info]")
    console.print()

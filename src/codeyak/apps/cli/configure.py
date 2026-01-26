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

from ...config import get_config_path, reset_settings


def _show_key_feedback(key: str, label: str) -> None:
    """Show feedback about entered key without revealing it."""
    if not key:
        click.echo(f"  ⚠ Warning: No {label} was entered")
    elif len(key) < 10:
        click.echo(f"  ✓ {label} entered ({len(key)} characters)")
    else:
        # Show first 4 and last 4 chars for verification
        masked = f"{key[:4]}...{key[-4:]}"
        click.echo(f"  ✓ {label} entered: {masked} ({len(key)} characters)")


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
    click.echo()
    click.echo("=== LLM Provider ===")
    click.echo("Available providers:")
    click.echo("  1. Azure OpenAI")
    click.echo()

    # Azure OpenAI Endpoint
    click.echo("  Example: https://your-resource.openai.azure.com/")
    endpoint = click.prompt("  Azure OpenAI Endpoint", type=str)

    # API Key
    click.echo()
    click.echo("  Found in Azure Portal > Your OpenAI Resource > Keys and Endpoint")
    api_key = click.prompt("  Azure OpenAI API Key", type=str, hide_input=True)
    _show_key_feedback(api_key, "API Key")

    # Deployment Name
    click.echo()
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
    click.echo()
    click.echo(f"Configuration saved to {config_path}")


def run_gitlab_init() -> None:
    """Run interactive init flow for GitLab configuration only."""
    click.echo()
    click.echo("=== GitLab Configuration ===")

    # GitLab URL
    gitlab_url = click.prompt(
        "  GitLab URL", type=str, default="https://gitlab.com", show_default=True
    )

    # GitLab Token
    click.echo()
    click.echo("  Personal Access Token (create at GitLab > Settings > Access Tokens)")
    gitlab_token = click.prompt("  GitLab Token", type=str, hide_input=True)
    _show_key_feedback(gitlab_token, "Token")

    # Load existing config and update with new values
    config = _load_existing_config()
    config["GITLAB_URL"] = gitlab_url
    config["GITLAB_TOKEN"] = gitlab_token

    _save_config(config)
    reset_settings()

    click.echo()
    click.echo(f"Configuration saved to {get_config_path()}")


def run_langfuse_init() -> None:
    """Run interactive init flow for Langfuse configuration only."""
    click.echo()
    click.echo("=== Langfuse Configuration (Optional) ===")
    click.echo("  Langfuse provides observability for your LLM calls.")
    click.echo()

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

    click.echo()
    click.echo(f"Configuration saved to {get_config_path()}")


def run_full_init(include_gitlab: bool = False) -> None:
    """
    Run the complete first-time setup flow.

    Args:
        include_gitlab: If True, also prompt for GitLab configuration.
    """
    click.echo()
    click.echo("Looks like you haven't configured CodeYak yet. Let's get you set up!")

    # Always configure LLM
    run_llm_init()

    # Optionally configure GitLab
    if include_gitlab:
        run_gitlab_init()

    # Ask about Langfuse
    click.echo()
    if click.confirm("Would you like to configure Langfuse for observability?", default=False):
        run_langfuse_init()

    click.echo()
    click.echo("Continuing with your command...")
    click.echo()

import sys
from pathlib import Path

import click
import yaml

from .... import __version__
from ....config import get_settings, is_langfuse_configured
from ....infrastructure import LocalGitAdapter, AzureAdapter
from ....services import GuidelinesGenerator
from ....ui import RichProgressReporter
from ..helpers import ensure_llm_configured


@click.command()
@click.option(
    "--days",
    type=int,
    default=365,
    help="Number of days of history to analyze (default: 365)",
)
def learn(days: int):
    """Generate guidelines from git history analysis.

    Analyzes commits to identify patterns of mistakes and problematic areas,
    then generates codeyak guidelines to help avoid future issues.

    Output is written to .codeyak/project.yaml
    """
    # Show banner first
    progress = RichProgressReporter()
    progress.banner("Codeyak", __version__)

    # Ensure LLM is configured before proceeding
    ensure_llm_configured()

    repo_path = Path.cwd()

    # Show observability status
    obs_status = "ON" if is_langfuse_configured() else "OFF"
    progress.info(f"Observability: {obs_status}")

    # Verify we're in a git repository
    try:
        vcs = LocalGitAdapter(repo_path)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("The 'learn' command must be run inside a git repository.", err=True)
        sys.exit(1)

    progress.info(f"Analyzing git history for the last {days} days...")

    # Initialize LLM adapter
    try:
        llm = AzureAdapter(
            api_key=get_settings().AZURE_OPENAI_API_KEY,
            endpoint=get_settings().AZURE_OPENAI_ENDPOINT,
            deployment_name=get_settings().AZURE_DEPLOYMENT_NAME,
            api_version=get_settings().AZURE_OPENAI_API_VERSION,
        )
    except Exception as e:
        click.echo(f"Error initializing LLM: {e}", err=True)
        sys.exit(1)

    # Initialize Langfuse if configured
    langfuse = None
    if get_settings().LANGFUSE_SECRET_KEY and get_settings().LANGFUSE_PUBLIC_KEY:
        from langfuse import Langfuse

        langfuse = Langfuse(
            secret_key=get_settings().LANGFUSE_SECRET_KEY,
            public_key=get_settings().LANGFUSE_PUBLIC_KEY,
            host=get_settings().LANGFUSE_HOST,
        )

    # Read existing guidelines if project.yaml exists
    codeyak_dir = repo_path / ".codeyak"
    output_path = codeyak_dir / "project.yaml"
    existing_guidelines = None

    if output_path.exists():
        try:
            parsed = yaml.safe_load(output_path.read_text())
            if parsed and isinstance(parsed.get("guidelines"), list):
                existing_guidelines = parsed["guidelines"]
                progress.info(f"Found {len(existing_guidelines)} existing guidelines.")
        except Exception:
            progress.warning("Could not parse existing project.yaml, will overwrite.")

    # Generate guidelines
    generator = GuidelinesGenerator(
        vcs=vcs, llm=llm, langfuse=langfuse, progress=progress
    )
    yaml_output = generator.generate_from_history(
        since_days=days, existing_guidelines=existing_guidelines
    )

    # Create .codeyak/ directory if it doesn't exist
    codeyak_dir.mkdir(exist_ok=True)

    if existing_guidelines is not None:
        # Check if generator returned anything new
        parsed_new = yaml.safe_load(yaml_output)
        new_guidelines = parsed_new.get("guidelines", []) if parsed_new else []

        if not new_guidelines:
            progress.success(
                "No new guidelines to add — existing guidelines are comprehensive."
            )
        else:
            # Append new guideline entries to the existing file
            new_yaml_lines = generator.format_guidelines_as_yaml_entries(new_guidelines)
            existing_content = output_path.read_text()
            # Ensure there's a newline before appending
            if not existing_content.endswith("\n"):
                existing_content += "\n"
            output_path.write_text(existing_content + new_yaml_lines)
            progress.success(
                f"Appended {len(new_guidelines)} new guidelines to {output_path}"
            )
            progress.info("Review and customize the new guidelines.")
    else:
        # Fresh write
        output_path.write_text(yaml_output)
        progress.success(f"Guidelines written to {output_path}")
        progress.info(
            "Review and customize the generated guidelines before using them."
        )

    # Flush Langfuse traces
    if langfuse:
        langfuse.flush()

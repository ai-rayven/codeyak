"""
CLI for CodeYak - Local and MR code review.

Usage:
    yak review              # Review local uncommitted changes
    yak mr <MR_ID> [PROJECT_ID]  # Review GitLab MR
"""

import os
import sys
from pathlib import Path

import click

from ... import __version__
from ...config import (
    get_settings,
    is_gitlab_configured,
    is_llm_configured,
    is_langfuse_configured,
    config_file_exists,
)
from .configure import run_full_init, run_gitlab_init, run_llm_init
from ...infrastructure import GitLabAdapter, LocalGitAdapter, AzureAdapter
from ...services import (
    CodeReviewer,
    GuidelinesProvider,
    CodeProvider,
    CodeReviewContextBuilder,
    MergeRequestFeedbackPublisher,
    ConsoleFeedbackPublisher,
    SummaryGenerator,
)


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
        click.echo()
        click.echo("LLM provider is not configured. Let's set it up!")
        run_llm_init()
        click.echo()
        click.echo("Continuing with your command...")
        click.echo()


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
        click.echo()
        click.echo("GitLab integration is not configured. Let's set it up!")
        run_gitlab_init()
        click.echo()
        click.echo("Continuing with your command...")
        click.echo()


@click.group()
@click.version_option(version=__version__, prog_name="yak")
def main():
    """CodeYak - AI-powered code review tool."""
    pass


@main.command()
@click.option(
    "--path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Path to git repository. Defaults to current directory."
)
def review(path: Path | None):
    """Review local uncommitted changes."""
    # Ensure LLM is configured before proceeding
    ensure_llm_configured()

    repo_path = path or Path.cwd()

    # Show observability status
    obs_status = "ON" if is_langfuse_configured() else "OFF"
    click.echo(f"Observability: {obs_status}")
    click.echo(f"Reviewing uncommitted changes in {repo_path}...")

    try:
        # Initialize adapters
        vcs = LocalGitAdapter(repo_path)
        llm = AzureAdapter(
            api_key=get_settings().AZURE_OPENAI_API_KEY,
            endpoint=get_settings().AZURE_OPENAI_ENDPOINT,
            deployment_name=get_settings().AZURE_DEPLOYMENT_NAME,
            api_version=get_settings().AZURE_OPENAI_API_VERSION
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error initializing: {e}", err=True)
        sys.exit(1)

    langfuse_enabled = bool(
        get_settings().LANGFUSE_SECRET_KEY and
        get_settings().LANGFUSE_PUBLIC_KEY
    )

    langfuse = None
    if langfuse_enabled:
        from langfuse import Langfuse
        langfuse = Langfuse(
            secret_key=get_settings().LANGFUSE_SECRET_KEY,
            public_key=get_settings().LANGFUSE_PUBLIC_KEY,
            host=get_settings().LANGFUSE_HOST
        )

    # Initialize services - CodeProvider handles all MergeRequest construction
    context = CodeReviewContextBuilder()
    guidelines = GuidelinesProvider(vcs)
    code = CodeProvider(vcs)
    feedback = ConsoleFeedbackPublisher()
    summary = SummaryGenerator(llm, langfuse=langfuse)

    bot = CodeReviewer(
        context=context,
        code=code,
        guidelines=guidelines,
        llm=llm,
        feedback=feedback,
        summary=summary,
        langfuse=langfuse
    )

    bot.review_local_changes()

    # Flush Langfuse traces
    if langfuse:
        langfuse.flush()


@main.command()
@click.argument("mr_id")
@click.argument("project_id", required=False)
def mr(mr_id: str, project_id: str | None):
    """Review a GitLab merge request.

    MR_ID is the merge request ID to review.
    PROJECT_ID is optional (uses CI_PROJECT_ID env var if not provided).
    """
    # Ensure both LLM and GitLab are configured before proceeding
    ensure_gitlab_configured()

    # Get project ID from argument or environment
    project_id = project_id or os.getenv("CI_PROJECT_ID")

    if not project_id:
        click.echo(
            "Error: Project ID is required. "
            "Pass it as the second argument or set CI_PROJECT_ID.",
            err=True
        )
        sys.exit(1)

    # Show observability status
    obs_status = "ON" if is_langfuse_configured() else "OFF"
    click.echo(f"Observability: {obs_status}")
    click.echo(f"Reviewing MR {mr_id} in project {project_id}...")

    # Initialize adapters
    try:
        vcs = GitLabAdapter(
            url=get_settings().GITLAB_URL,
            token=get_settings().GITLAB_TOKEN,
            project_id=project_id
        )

        llm = AzureAdapter(
            api_key=get_settings().AZURE_OPENAI_API_KEY,
            endpoint=get_settings().AZURE_OPENAI_ENDPOINT,
            deployment_name=get_settings().AZURE_DEPLOYMENT_NAME,
            api_version=get_settings().AZURE_OPENAI_API_VERSION
        )
    except Exception as e:
        click.echo(f"Configuration Error: {e}", err=True)
        sys.exit(1)

    # Initialize Langfuse if configured
    langfuse_enabled = bool(
        get_settings().LANGFUSE_SECRET_KEY and
        get_settings().LANGFUSE_PUBLIC_KEY
    )

    langfuse = None
    if langfuse_enabled:
        from langfuse import Langfuse
        langfuse = Langfuse(
            secret_key=get_settings().LANGFUSE_SECRET_KEY,
            public_key=get_settings().LANGFUSE_PUBLIC_KEY,
            host=get_settings().LANGFUSE_HOST
        )

    # Initialize services
    context = CodeReviewContextBuilder()
    guidelines = GuidelinesProvider(vcs)
    code = CodeProvider(vcs)
    feedback = MergeRequestFeedbackPublisher(vcs, mr_id)
    summary = SummaryGenerator(llm, langfuse)

    # Create reviewer and run
    bot = CodeReviewer(
        context=context,
        guidelines=guidelines,
        code=code,
        feedback=feedback,
        llm=llm,
        summary=summary,
        langfuse=langfuse,
    )

    bot.review_merge_request(mr_id)

    # Flush Langfuse traces
    if langfuse:
        langfuse.flush()

    click.echo("Review complete.")


if __name__ == "__main__":
    main()

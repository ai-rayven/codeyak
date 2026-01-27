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
    GuidelinesGenerator,
    CodeProvider,
    CodeReviewContextBuilder,
    MergeRequestFeedbackPublisher,
    ConsoleFeedbackPublisher,
    SummaryGenerator,
)
from ...ui import console, RichProgressReporter, CIProgressReporter


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
        console.print("[info]GitLab integration is not configured. Let's set it up![/info]")
        run_gitlab_init()
        console.print()
        console.print("[info]Continuing with your command...[/info]")
        console.print()


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
    # Show banner first
    progress = RichProgressReporter()
    progress.banner("Codeyak", __version__)

    # Ensure LLM is configured before proceeding
    ensure_llm_configured()

    repo_path = path or Path.cwd()

    # Show observability status
    obs_status = "ON" if is_langfuse_configured() else "OFF"
    progress.info(f"Observability: {obs_status}")
    progress.info(f"Reviewing uncommitted changes in {repo_path}...")

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
        langfuse=langfuse,
        progress=progress,
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
    obs_status = "[success]ON[/success]" if is_langfuse_configured() else "[muted]OFF[/muted]"
    console.print(f"Observability: {obs_status}")
    console.print(f"[info]Reviewing MR {mr_id} in project {project_id}...[/info]")

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
    progress = CIProgressReporter()

    # Create reviewer and run
    bot = CodeReviewer(
        context=context,
        guidelines=guidelines,
        code=code,
        feedback=feedback,
        llm=llm,
        summary=summary,
        langfuse=langfuse,
        progress=progress,
    )

    bot.review_merge_request(mr_id)

    # Flush Langfuse traces
    if langfuse:
        langfuse.flush()

    progress.success("Review complete.")


@main.command()
@click.option(
    "--days",
    type=int,
    default=365,
    help="Number of days of history to analyze (default: 365)"
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
            api_version=get_settings().AZURE_OPENAI_API_VERSION
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
            host=get_settings().LANGFUSE_HOST
        )

    # Generate guidelines
    generator = GuidelinesGenerator(vcs=vcs, llm=llm, langfuse=langfuse, progress=progress)
    yaml_output = generator.generate_from_history(since_days=days)

    # Create .codeyak/ directory if it doesn't exist
    codeyak_dir = repo_path / ".codeyak"
    codeyak_dir.mkdir(exist_ok=True)

    # Write output to project.yaml
    output_path = codeyak_dir / "project.yaml"
    output_path.write_text(yaml_output)

    progress.success(f"Guidelines written to {output_path}")
    progress.info("Review and customize the generated guidelines before using them.")

    # Flush Langfuse traces
    if langfuse:
        langfuse.flush()


if __name__ == "__main__":
    main()

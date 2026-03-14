import sys
from pathlib import Path

import click

from .... import __version__
from ....config import get_settings, is_langfuse_configured
from ....infrastructure import LocalGitAdapter, AzureAdapter
from ....services import (
    CodeReviewer,
    GuidelinesProvider,
    CodeProvider,
    CodeReviewContextBuilder,
    ConsoleFeedbackPublisher,
    SummaryGenerator,
)
from ....ui import RichProgressReporter
from ..helpers import ensure_llm_configured


@click.command()
@click.option(
    "--path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Path to git repository. Defaults to current directory.",
)
@click.option(
    "--exclude",
    "exclude_patterns",
    multiple=True,
    help="Glob pattern to exclude files from review (repeatable). "
         "e.g. --exclude '*Tests.cs' --exclude 'tests/'",
)
def review(path: Path | None, exclude_patterns: tuple[str, ...]):
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
            api_version=get_settings().AZURE_OPENAI_API_VERSION,
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error initializing: {e}", err=True)
        sys.exit(1)

    langfuse_enabled = bool(
        get_settings().LANGFUSE_SECRET_KEY and get_settings().LANGFUSE_PUBLIC_KEY
    )

    langfuse = None
    if langfuse_enabled:
        from langfuse import Langfuse

        langfuse = Langfuse(
            secret_key=get_settings().LANGFUSE_SECRET_KEY,
            public_key=get_settings().LANGFUSE_PUBLIC_KEY,
            host=get_settings().LANGFUSE_HOST,
        )

    # Initialize services - CodeProvider handles all MergeRequest construction
    context = CodeReviewContextBuilder(
        llm_client=llm,
        repo_path=repo_path,
        use_smart_context=True,
        progress=progress,
    )
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

    bot.review_local_changes(exclude_patterns=list(exclude_patterns) if exclude_patterns else None)

    # Flush Langfuse traces
    if langfuse:
        langfuse.flush()

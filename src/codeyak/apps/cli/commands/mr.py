import os
import sys
from pathlib import Path

import click

from ....config import get_settings, is_langfuse_configured
from ....infrastructure import GitLabAdapter, AzureAdapter
from ....services import (
    CodeReviewer,
    GuidelinesProvider,
    CodeProvider,
    CodeReviewContextBuilder,
    MergeRequestFeedbackPublisher,
    SummaryGenerator,
)
from ....ui import console, CIProgressReporter
from ..helpers import ensure_gitlab_configured


@click.command()
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
            err=True,
        )
        sys.exit(1)

    # Show observability status
    obs_status = (
        "[success]ON[/success]" if is_langfuse_configured() else "[muted]OFF[/muted]"
    )
    console.print(f"Observability: {obs_status}")
    console.print(f"[info]Reviewing MR {mr_id} in project {project_id}...[/info]")

    # Initialize adapters
    try:
        vcs = GitLabAdapter(
            url=get_settings().GITLAB_URL,
            token=get_settings().GITLAB_TOKEN,
            project_id=project_id,
        )

        llm = AzureAdapter(
            api_key=get_settings().AZURE_OPENAI_API_KEY,
            endpoint=get_settings().AZURE_OPENAI_ENDPOINT,
            deployment_name=get_settings().AZURE_DEPLOYMENT_NAME,
            api_version=get_settings().AZURE_OPENAI_API_VERSION,
        )
    except Exception as e:
        click.echo(f"Configuration Error: {e}", err=True)
        sys.exit(1)

    # Initialize Langfuse if configured
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

    # Initialize services
    progress = CIProgressReporter()
    context = CodeReviewContextBuilder(
        llm_client=llm,
        repo_path=Path.cwd(),
        use_smart_context=True,
        progress=progress,
    )
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
        progress=progress,
    )

    bot.review_merge_request(mr_id)

    # Flush Langfuse traces
    if langfuse:
        langfuse.flush()

    progress.success("Review complete.")

import os
import sys
from pathlib import Path

import click
import yaml

from .... import __version__
from ....config import get_settings, is_langfuse_configured, is_gitlab_configured
from ....infrastructure import LocalGitAdapter, GitLabAdapter, AzureAdapter
from ....services import GuidelinesGenerator, PRReviewGuidelinesGenerator
from ....ui import RichProgressReporter
from ..helpers import ensure_llm_configured, ensure_gitlab_configured as ensure_gitlab_configured_interactive


@click.command()
@click.option(
    "--days",
    type=int,
    default=365,
    help="Number of days of history to analyze (default: 365)",
)
@click.option(
    "--source",
    type=click.Choice(["commits", "prs"], case_sensitive=False),
    default="commits",
    help="Source to analyze: commits (default) or prs (merge request reviews)",
)
@click.option(
    "--mr",
    type=str,
    default=None,
    help="Specific MR IID to analyze (used with --source prs)",
)
@click.option(
    "--project-id",
    type=str,
    default=None,
    help="GitLab project ID or path (e.g., 'group/project'). Auto-detected from git remote if omitted.",
)
def learn(days: int, source: str, mr: str | None, project_id: str | None):
    """Generate guidelines from git history or MR review analysis.

    Analyzes commits or merge request review comments to identify patterns
    of mistakes and problematic areas, then generates codeyak guidelines.

    For commits: output is written to .codeyak/project.yaml
    For PRs: suggested guidelines are printed to stdout
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
            progress.warning("Could not parse existing project.yaml.")

    if source == "prs":
        _run_pr_analysis(
            vcs=vcs,
            llm=llm,
            langfuse=langfuse,
            progress=progress,
            days=days,
            mr_iid=mr,
            project_id_opt=project_id,
            existing_guidelines=existing_guidelines,
        )
    else:
        _run_commit_analysis(
            vcs=vcs,
            llm=llm,
            langfuse=langfuse,
            progress=progress,
            days=days,
            existing_guidelines=existing_guidelines,
            codeyak_dir=codeyak_dir,
            output_path=output_path,
        )

    # Flush Langfuse traces
    if langfuse:
        langfuse.flush()


def _run_commit_analysis(
    vcs: LocalGitAdapter,
    llm: AzureAdapter,
    langfuse,
    progress: RichProgressReporter,
    days: int,
    existing_guidelines: list[dict] | None,
    codeyak_dir: Path,
    output_path: Path,
):
    """Run the existing commit-based analysis pipeline."""
    progress.info(f"Analyzing git history for the last {days} days...")

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


def _run_pr_analysis(
    vcs: LocalGitAdapter,
    llm: AzureAdapter,
    langfuse,
    progress: RichProgressReporter,
    days: int,
    mr_iid: str | None,
    project_id_opt: str | None,
    existing_guidelines: list[dict] | None,
):
    """Run the PR review comment analysis pipeline."""
    # Ensure GitLab is configured
    ensure_gitlab_configured_interactive()

    # Resolve project ID
    resolved_project_id = (
        project_id_opt
        or vcs.get_gitlab_project_path()
        or os.getenv("CI_PROJECT_ID")
    )

    if not resolved_project_id:
        click.echo(
            "Error: Could not determine GitLab project ID.\n"
            "Provide it with --project-id, set CI_PROJECT_ID, "
            "or ensure a GitLab remote is configured.",
            err=True,
        )
        sys.exit(1)

    progress.info(f"Using GitLab project: {resolved_project_id}")

    # Initialize GitLab adapter
    try:
        gitlab_vcs = GitLabAdapter(
            url=get_settings().GITLAB_URL,
            token=get_settings().GITLAB_TOKEN,
            project_id=resolved_project_id,
        )
    except Exception as e:
        click.echo(f"Error connecting to GitLab: {e}", err=True)
        sys.exit(1)

    # Create PR review generator
    pr_generator = PRReviewGuidelinesGenerator(
        gitlab_vcs=gitlab_vcs,
        llm=llm,
        langfuse=langfuse,
        progress=progress,
    )

    # Run analysis
    if mr_iid:
        progress.info(f"Analyzing review comments on MR !{mr_iid}...")
        yaml_output = pr_generator.generate_from_mr(
            mr_iid=mr_iid,
            existing_guidelines=existing_guidelines,
        )
    else:
        progress.info(f"Analyzing merged MRs from the last {days} days...")
        yaml_output = pr_generator.generate_from_mrs(
            since_days=days,
            existing_guidelines=existing_guidelines,
        )

    # Print suggested guidelines to stdout
    click.echo("\n" + yaml_output)

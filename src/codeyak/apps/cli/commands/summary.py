import os
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import List

import click
from rich.console import Console
from rich.markdown import Markdown

from .... import __version__
from ....config import get_settings, is_langfuse_configured
from ....domain.constants import CODE_FILE_EXTENSIONS
from ....domain.models import FileDiff, MergeRequest
from ....infrastructure import GitLabAdapter, LocalGitAdapter, AzureAdapter
from ....services import CodeProvider, SummaryGenerator
from ....ui import RichProgressReporter
from ..helpers import ensure_llm_configured, ensure_gitlab_configured


@click.command()
@click.option(
    "--mr",
    "mr_id",
    type=str,
    default=None,
    help="GitLab merge request ID to summarize.",
)
@click.option(
    "--project",
    type=str,
    default=None,
    help="GitLab project ID or path (e.g., 12345 or mygroup/myproject)." 
)
@click.option(
    "--commits",
    "num_commits",
    type=int,
    default=None,
    help="Summarize the last N commits.",
)
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
    help="Glob pattern to exclude files from summary (repeatable). "
         "e.g. --exclude '*Tests.cs' --exclude 'tests/'",
)
def summary(mr_id: str | None, project: str | None, num_commits: int | None, path: Path | None, exclude_patterns: tuple[str, ...]):
    """Generate a summary of code changes."""
    # Validate mutual exclusivity
    if mr_id and num_commits:
        click.echo("Error: --mr and --commits are mutually exclusive.", err=True)
        sys.exit(1)

    progress = RichProgressReporter()
    progress.banner("Codeyak", __version__)

    ensure_llm_configured()

    obs_status = "ON" if is_langfuse_configured() else "OFF"
    progress.info(f"Observability: {obs_status}")

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

    langfuse = None
    if get_settings().LANGFUSE_SECRET_KEY and get_settings().LANGFUSE_PUBLIC_KEY:
        from langfuse import Langfuse
        langfuse = Langfuse(
            secret_key=get_settings().LANGFUSE_SECRET_KEY,
            public_key=get_settings().LANGFUSE_PUBLIC_KEY,
            host=get_settings().LANGFUSE_HOST,
        )

    summary_gen = SummaryGenerator(llm, langfuse=langfuse)

    patterns = list(exclude_patterns) if exclude_patterns else None

    if mr_id:
        merge_request = _summarize_mr(mr_id, project, progress, patterns)
    elif num_commits:
        merge_request = _summarize_commits(num_commits, path, progress, patterns)
    else:
        merge_request = _summarize_local(path, progress, patterns)

    if not merge_request.file_diffs:
        progress.warning("No changes found.")
        sys.exit(0)

    progress.info(f"Summarizing {len(merge_request.file_diffs)} file(s)...")

    # Create Langfuse trace if configured
    trace = None
    if langfuse:
        trace = langfuse.start_span(
            name="generate_summary",
            input={
                "mode": "mr" if mr_id else ("commits" if num_commits else "local"),
                "file_count": len(merge_request.file_diffs),
                "commit_count": len(merge_request.commits),
            },
            metadata={"merge_request_id": merge_request.id},
        )

    result = summary_gen.generate_summary(merge_request, trace)

    if trace:
        trace.update(output=result)
        trace.end()

    console = Console()
    console.print()
    console.print(Markdown(result.summary))

    if langfuse:
        langfuse.flush()


def _summarize_local(path: Path | None, progress: RichProgressReporter, exclude_patterns: List[str] | None = None) -> MergeRequest:
    """Summarize local uncommitted changes."""
    repo_path = path or Path.cwd()
    progress.info(f"Summarizing uncommitted changes in {repo_path}...")

    try:
        vcs = LocalGitAdapter(repo_path)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    code = CodeProvider(vcs)
    return code.get_merge_request("local", CODE_FILE_EXTENSIONS, exclude_patterns=exclude_patterns)


def _summarize_mr(mr_id: str, project: str | None, progress: RichProgressReporter, exclude_patterns: List[str] | None = None) -> MergeRequest:
    """Summarize a GitLab merge request."""
    ensure_gitlab_configured()

    project_id = project
    if not project_id:
        click.echo(
            "Error: --project is required for MR mode. ",
            err=True,
        )
        sys.exit(1)

    progress.info(f"Summarizing MR {mr_id} in project {project_id}...")

    try:
        vcs = GitLabAdapter(
            url=get_settings().GITLAB_URL,
            token=get_settings().GITLAB_TOKEN,
            project_id=project_id,
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    code = CodeProvider(vcs)
    return code.get_merge_request(mr_id, CODE_FILE_EXTENSIONS, exclude_patterns=exclude_patterns)


def _filter_by_exclusion(diffs: List[FileDiff], exclude_patterns: List[str]) -> List[FileDiff]:
    """Filter out file diffs matching any exclusion pattern."""
    def is_excluded(file_path: str) -> bool:
        basename = os.path.basename(file_path)
        for pattern in exclude_patterns:
            if pattern.endswith("/"):
                if file_path.startswith(pattern) or f"/{pattern}" in f"/{file_path}":
                    return True
            else:
                if fnmatch(file_path, pattern) or fnmatch(basename, pattern):
                    return True
        return False

    return [diff for diff in diffs if not is_excluded(diff.file_path)]


def _summarize_commits(num_commits: int, path: Path | None, progress: RichProgressReporter, exclude_patterns: List[str] | None = None) -> MergeRequest:
    """Summarize the last N commits."""
    repo_path = path or Path.cwd()
    progress.info(f"Summarizing last {num_commits} commit(s) in {repo_path}...")

    try:
        vcs = LocalGitAdapter(repo_path)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        start_ref = f"HEAD~{num_commits}"
        end_ref = "HEAD"
        file_diffs = vcs.get_commit_range_diff(start_ref, end_ref)
        commits = vcs.get_commit_range_commits(start_ref, end_ref)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Filter to code files
    file_diffs = [
        d for d in file_diffs
        if any(d.file_path.endswith(ext) for ext in CODE_FILE_EXTENSIONS)
    ]

    # Apply exclusion patterns
    if exclude_patterns:
        file_diffs = _filter_by_exclusion(file_diffs, exclude_patterns)

    return MergeRequest(
        id="local",
        project_name=vcs.get_project_name(),
        author=vcs.get_username(),
        file_diffs=file_diffs,
        commits=commits,
    )

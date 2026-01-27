"""
Local git adapter for reviewing uncommitted changes.

Implements VCSClient protocol for local git operations using GitPython.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional

from git import Repo
from git.exc import InvalidGitRepositoryError

from ...protocols import VCSClient
from ...domain.models import FileDiff, GuidelineViolation, MRComment, Commit, HistoricalCommit
from .diff_parser import UnifiedDiffParser


class LocalGitAdapter(VCSClient):
    """
    VCS adapter for local git operations.

    Uses GitPython to get diff of uncommitted changes and reads
    files from the local filesystem.
    """

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize the local git adapter.

        Args:
            repo_path: Path to the git repository. Defaults to current working directory.

        Raises:
            ValueError: If the path is not a valid git repository.
        """
        path = repo_path or Path.cwd()
        try:
            self.repo = Repo(path, search_parent_directories=True)
        except InvalidGitRepositoryError:
            raise ValueError(f"Not a git repository: {path}")

        self.repo_path = Path(self.repo.working_dir)

    def get_project_name(self) -> str:
        """Get the project name from the git remote or directory name."""
        try:
            # Try to get from remote origin
            remote_url = self.repo.remotes.origin.url
            # Extract project name from URL (handles both HTTPS and SSH)
            if remote_url.endswith(".git"):
                remote_url = remote_url[:-4]
            return remote_url.split("/")[-1]
        except (AttributeError, IndexError):
            # Fall back to directory name
            return self.repo_path.name

    def get_mr_author(self, mr_id: str) -> str:
        v = self.get_username()
        return v
        
    def get_username(self) -> str:
        """Get the current git user as the author."""
        try:
            reader = self.repo.config_reader()
            return reader.get_value("user", "name", default="local-user")
        except Exception:
            return "local-user"

    def get_diff(self, mr_id: str) -> List[FileDiff]:
        """
        Get diff of uncommitted changes (both staged and unstaged).

        Args:
            mr_id: Ignored for local git (kept for protocol compatibility)

        Returns:
            List of FileDiff objects for changed files
        """
        # Get diff between HEAD and working tree (includes both staged and unstaged)
        # create_patch=True gives us the actual diff content
        head_commit = self.repo.head.commit
        diffs = head_commit.diff(None, create_patch=True)

        if not diffs:
            return []

        return self._parse_git_diffs(diffs)

    def _parse_git_diffs(self, diffs) -> List[FileDiff]:
        """Parse GitPython diff objects into FileDiff objects."""
        parser = UnifiedDiffParser()
        file_diffs = []

        for diff in diffs:
            # Skip deleted files
            if diff.deleted_file:
                continue

            # Get file path (use b_path for new/modified files)
            file_path = diff.b_path or diff.a_path

            # Get the diff patch content
            raw_diff = ""
            if diff.diff:
                # diff.diff is bytes, decode to string
                raw_diff = diff.diff.decode("utf-8", errors="replace")

            # Parse the diff hunks
            hunks = parser.parse(raw_diff)

            # Get full file content
            full_content = self.get_file_content("", file_path)

            file_diffs.append(FileDiff(
                file_path=file_path,
                hunks=hunks,
                full_content=full_content,
                raw_diff=raw_diff
            ))

        return file_diffs

    def get_file_content(self, mr_id: str, file_path: str) -> Optional[str]:
        """
        Read file content from the local filesystem.

        Args:
            mr_id: Ignored for local git
            file_path: Path to the file relative to repo root

        Returns:
            File content as string, or None if file doesn't exist
        """
        full_path = self.repo_path / file_path
        if not full_path.exists():
            return None

        try:
            return full_path.read_text()
        except Exception:
            return None

    def get_codeyak_files(self, mr_id: str) -> Dict[str, str]:
        """
        Read YAML files from local .codeyak/ directory.

        Args:
            mr_id: Ignored for local git

        Returns:
            Dict mapping filename to content
        """
        codeyak_dir = self.repo_path / ".codeyak"

        if not codeyak_dir.exists() or not codeyak_dir.is_dir():
            return {}

        yaml_files = {}
        for yaml_file in sorted(list(codeyak_dir.glob("*.yaml")) + list(codeyak_dir.glob("*.yml"))):
            try:
                yaml_files[yaml_file.name] = yaml_file.read_text()
            except Exception:
                continue

        return yaml_files

    def get_comments(self, mr_id: str) -> List[MRComment]:
        """
        Return empty list - no comments for local review.

        Args:
            mr_id: Ignored for local git

        Returns:
            Empty list (local reviews have no existing comments)
        """
        return []

    def get_commits(self, mr_id: str) -> List[Commit]:
        """
        Return empty list - no commits context for local diff review.

        Args:
            mr_id: Ignored for local git

        Returns:
            Empty list (local reviews focus on uncommitted changes)
        """
        return []

    def post_comment(self, mr_id: str, violation: GuidelineViolation) -> None:
        """
        No-op for local git - comments are printed to console instead.

        Args:
            mr_id: Ignored
            violation: Ignored
        """
        pass

    def post_general_comment(self, mr_id: str, message: str) -> None:
        """
        No-op for local git - messages are printed to console instead.

        Args:
            mr_id: Ignored
            message: Ignored
        """
        pass

    def get_historical_commits(
        self,
        since_days: int = 365,
        max_commits: int = 1000
    ) -> List[HistoricalCommit]:
        """
        Fetch commits from git history.

        Args:
            since_days: Number of days of history to analyze
            max_commits: Maximum number of commits to return

        Returns:
            List of HistoricalCommit objects
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=since_days)

        commits = []
        for commit in self.repo.iter_commits(max_count=max_commits):
            # Skip commits older than since_date
            commit_date = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)
            if commit_date < since_date:
                break

            # Get list of changed files
            files_changed = []
            if commit.parents:
                # Compare with parent to get changed files
                diff_index = commit.parents[0].diff(commit)
                for diff_item in diff_index:
                    file_path = diff_item.b_path or diff_item.a_path
                    if file_path:
                        files_changed.append(file_path)
            else:
                # Initial commit - list all files
                for item in commit.tree.traverse():
                    if item.type == 'blob':
                        files_changed.append(item.path)

            commits.append(HistoricalCommit(
                sha=commit.hexsha,
                message=commit.message.strip(),
                author=commit.author.name or "unknown",
                date=commit_date.isoformat(),
                files_changed=files_changed,
                diff_summary=""  # Will be populated separately if needed
            ))

        return commits

    def get_commit_diff(self, commit_sha: str, max_lines: int = 100) -> str:
        """
        Get truncated diff for a specific commit.

        Args:
            commit_sha: The commit SHA to get diff for
            max_lines: Maximum number of lines to return

        Returns:
            Truncated diff as string
        """
        try:
            commit = self.repo.commit(commit_sha)

            if not commit.parents:
                # Initial commit - show all files as additions
                diff_text = commit.diff(None, create_patch=True)
            else:
                # Compare with parent
                diff_text = commit.parents[0].diff(commit, create_patch=True)

            # Build diff string
            lines = []
            for diff_item in diff_text:
                if diff_item.diff:
                    decoded = diff_item.diff.decode("utf-8", errors="replace")
                    lines.extend(decoded.split("\n"))

                if len(lines) >= max_lines:
                    break

            # Truncate and add indicator
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                lines.append("\n... (truncated)")

            return "\n".join(lines)

        except Exception:
            return ""

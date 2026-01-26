"""
Local git adapter for reviewing uncommitted changes.

Implements VCSClient protocol for local git operations using GitPython.
"""

from pathlib import Path
from typing import List, Dict, Optional

from git import Repo
from git.exc import InvalidGitRepositoryError

from ...protocols import VCSClient
from ...domain.models import FileDiff, GuidelineViolation, MRComment, Commit
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

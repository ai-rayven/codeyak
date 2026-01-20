"""
Code service for retrieving merge request data.

Provides high-level interface for fetching merge requests with filtering capabilities.
"""

from typing import List
from ..protocols import VCSClient
from ..domain.models import MergeRequest, FileDiff


class CodeProvider:
    """
    Service for retrieving and filtering merge request code.

    Args:
        vcs_client: The VCS client implementation to use for fetching data
    """

    def __init__(self, vcs_client: VCSClient):
        self.vcs_client = vcs_client

    def get_merge_request(
        self,
        merge_request_id: str,
        extension_filters: List[str]
    ) -> MergeRequest:
        """
        Fetch a merge request with its file diffs, comments, and commits.

        Args:
            merge_request_id: The ID of the merge request to fetch
            extension_filters: List of file extensions to include (e.g., ['.py', '.js'])
                             If empty, all files are included

        Returns:
            MergeRequest object containing filtered file diffs, all comments, and commits
        """
        # Fetch all file diffs from VCS
        all_diffs = self.vcs_client.get_diff(merge_request_id)

        # Apply extension filters if provided
        filtered_diffs = self._filter_by_extension(all_diffs, extension_filters)

        # Fetch all comments
        comments = self.vcs_client.get_comments(merge_request_id)

        # Fetch all commits
        commits = self.vcs_client.get_commits(merge_request_id)

        # Get project name and author
        project_name = self.vcs_client.get_project_name()
        author = self.vcs_client.get_mr_author(merge_request_id)

        # Build and return MergeRequest
        return MergeRequest(
            id=merge_request_id,
            project_name=project_name,
            author=author,
            file_diffs=filtered_diffs,
            comments=comments,
            commits=commits
        )

    def _filter_by_extension(
        self,
        diffs: List[FileDiff],
        extensions: List[str]
    ) -> List[FileDiff]:
        """
        Filter file diffs by their file extensions.

        Args:
            diffs: List of all file diffs
            extensions: List of extensions to include (e.g., ['.py', '.js'])

        Returns:
            Filtered list of file diffs
        """
        if not extensions:
            return diffs

        # Normalize extensions to ensure they start with a dot
        normalized_extensions = [
            ext if ext.startswith('.') else f'.{ext}'
            for ext in extensions
        ]

        return [
            diff for diff in diffs
            if any(diff.file_path.endswith(ext) for ext in normalized_extensions)
        ]

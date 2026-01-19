"""
Port interfaces (protocols) for external dependencies.

These define the contracts that adapters must implement.
"""

from typing import List, Type, TypeVar, Any, Dict, Protocol
from pydantic import BaseModel
from ..domain.models import FileDiff, GuidelineViolation, MRComment, LLMResponse, Commit

# "T" means "Any Pydantic Model"
T = TypeVar("T", bound=BaseModel)


class VCSClient(Protocol):
    def get_diff(self, mr_id: str) -> List[FileDiff]:
        ...

    def post_comment(self, mr_id: str, violation: GuidelineViolation) -> None:
        ...

    def post_general_comment(self, mr_id: str, message: str) -> None:
        """Post a general comment on the MR (not tied to a specific line)."""
        ...

    def get_comments(self, mr_id: str) -> List[MRComment]:
        """
        Retrieve all comments from the MR (both inline and general).

        Returns:
            List of MRComment objects, sorted by creation date (oldest first)

        Raises:
            VCSFetchCommentsError: When fetching comments fails
        """
        ...

    def get_commits(self, mr_id: str) -> List[Commit]:
        """
        Fetch all commits from the merge request.

        Args:
            mr_id: Merge request ID

        Returns:
            List of Commit objects with sha, message, author, and created_at

        Raises:
            VCSFetchCommentsError: When fetching commits fails
        """
        ...

    def get_codeyak_files(self, mr_id: str) -> Dict[str, str]:
        """
        Fetch YAML files from .codeyak/ directory in the MR's source branch.

        Returns:
            Dict[str, str]: Map of filename to file content. Empty dict if no .codeyak/ directory.
        """
        ...

    def get_file_content(self, mr_id: str, file_path: str) -> Any:
        """
        Fetch the full content of a file from the MR's source branch.

        Args:
            mr_id: Merge request ID
            file_path: Path to the file

        Returns:
            File content as string, or None if file doesn't exist (e.g., newly added file)
        """
        ...


class LLMClient(Protocol):
    def generate(self, messages: List[dict], response_model: Type[T]) -> LLMResponse[T]:
        """
        Generic gateway to the LLM.
        Args:
            messages: Standard OpenAI format [{"role": "user", "content": "..."}]
            response_model: The Pydantic class to validate the output against.
        Returns:
            An LLMResponse containing the parsed result and metadata (token usage, model, provider, latency).
        """
        ...

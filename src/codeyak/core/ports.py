from abc import ABC, abstractmethod
from typing import List, Type, TypeVar, Any, Dict
from pydantic import BaseModel
from .models import FileDiff, GuidelineViolation, MRComment

# "T" means "Any Pydantic Model"
T = TypeVar("T", bound=BaseModel)

class VCSClient(ABC):
    @abstractmethod
    def get_diff(self, mr_id: str) -> List[FileDiff]:
        pass

    @abstractmethod
    def post_comment(self, mr_id: str, violation: GuidelineViolation) -> None:
        pass

    @abstractmethod
    def post_general_comment(self, mr_id: str, message: str) -> None:
        """Post a general comment on the MR (not tied to a specific line)."""
        pass

    @abstractmethod
    def get_comments(self, mr_id: str) -> List[MRComment]:
        """
        Retrieve all comments from the MR (both inline and general).

        Returns:
            List of MRComment objects, sorted by creation date (oldest first)

        Raises:
            VCSFetchCommentsError: When fetching comments fails
        """
        pass

    @abstractmethod
    def get_codeyak_files(self, mr_id: str) -> Dict[str, str]:
        """
        Fetch YAML files from .codeyak/ directory in the MR's source branch.

        Returns:
            Dict[str, str]: Map of filename to file content. Empty dict if no .codeyak/ directory.
        """
        pass

    @abstractmethod
    def get_file_content(self, mr_id: str, file_path: str) -> Any:
        """
        Fetch the full content of a file from the MR's source branch.

        Args:
            mr_id: Merge request ID
            file_path: Path to the file

        Returns:
            File content as string, or None if file doesn't exist (e.g., newly added file)
        """
        pass

class LLMClient(ABC):
    @abstractmethod
    def generate(self, messages: List[dict], response_model: Type[T]) -> T:
        """
        Generic gateway to the LLM.
        Args:
            messages: Standard OpenAI format [{"role": "user", "content": "..."}]
            response_model: The Pydantic class to validate the output against.
        Returns:
            An instance of response_model.
        """
        pass
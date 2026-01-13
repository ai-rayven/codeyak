from abc import ABC, abstractmethod
from typing import List, Type, TypeVar, Any
from pydantic import BaseModel
from .models import FileDiff, GuidelineViolation

# "T" means "Any Pydantic Model"
T = TypeVar("T", bound=BaseModel)

class VCSClient(ABC):
    @abstractmethod
    def get_diff(self, mr_id: str) -> List[FileDiff]:
        pass

    @abstractmethod
    def post_comment(self, mr_id: str, violation: GuidelineViolation) -> None:
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
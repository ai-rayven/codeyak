import instructor
from openai import AzureOpenAI
from typing import List, Type, TypeVar
from pydantic import BaseModel

from ...config import settings
from ...core.ports import LLMClient

T = TypeVar("T", bound=BaseModel)

class AzureAdapter(LLMClient):
    def __init__(self):
        # Initialize standard client
        client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        
        # Patch with Instructor for structured outputs
        self.client = instructor.from_provider(client)
        self.deployment = settings.AZURE_DEPLOYMENT_NAME

    def generate(self, messages: List[dict], response_model: Type[T]) -> T:
        return self.client.chat.completions.create(
            model=self.deployment,
            response_model=response_model,
            messages=messages,
            temperature=0.0, # Keep it deterministic
        )
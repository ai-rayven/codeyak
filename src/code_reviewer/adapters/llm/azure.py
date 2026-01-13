import instructor
from openai import AzureOpenAI
from typing import List, Type, TypeVar
from pydantic import BaseModel

from ...core.ports import LLMClient

T = TypeVar("T", bound=BaseModel)

class AzureAdapter(LLMClient):
    def __init__(self, api_key: str, endpoint: str, deployment_name: str, api_version: str="2025-04-01-preview"):
        # Initialize standard client
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        
        # Patch with Instructor for structured outputs
        self.client = instructor.from_openai(client)
        self.deployment = deployment_name 

    def generate(self, messages: List[dict], response_model: Type[T]) -> T:
        return self.client.chat.completions.create(
            model=self.deployment,
            response_model=response_model,
            messages=messages,
            temperature=0.0, # Keep it deterministic
        )
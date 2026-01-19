import instructor
from openai import AzureOpenAI
from typing import List, Type, TypeVar
from pydantic import BaseModel
import time

from ...protocols import LLMClient
from ...domain.models import LLMResponse, TokenUsage

T = TypeVar("T", bound=BaseModel)

class AzureAdapter(LLMClient):
    def __init__(self, api_key: str, endpoint: str, deployment_name: str, api_version: str="2025-04-01-preview"):
        # Remove trailing slash from endpoint if present
        endpoint = endpoint.rstrip('/')

        # Initialize standard client
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        
        # Patch with Instructor for structured outputs
        self.client = instructor.from_openai(client)
        self.deployment = deployment_name 

    def generate(self, messages: List[dict], response_model: Type[T]) -> LLMResponse[T]:
        # Track timing
        start_time = time.time()

        # Make the API call with instructor
        # Use create_with_completion to get both the parsed result and raw completion
        result, completion = self.client.chat.completions.create_with_completion(
            model=self.deployment,
            response_model=response_model,
            messages=messages
        )

        # Calculate latency
        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000

        # Extract token usage from completion
        usage = completion.usage
        token_usage = TokenUsage(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens
        )

        # Return wrapped response with metadata
        return LLMResponse(
            result=result,
            token_usage=token_usage,
            model=self.deployment,
            provider="azure",
            latency_ms=latency_ms
        )
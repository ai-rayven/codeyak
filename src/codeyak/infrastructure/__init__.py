"""
Infrastructure layer for CodeYak.

Contains adapter implementations for external services (VCS, LLM).
"""

from .vcs.gitlab import GitLabAdapter
from .llm.azure import AzureAdapter

__all__ = [
    # VCS Adapters
    "GitLabAdapter",
    # LLM Adapters
    "AzureAdapter",
]

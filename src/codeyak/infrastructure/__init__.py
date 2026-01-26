"""
Infrastructure layer for CodeYak.

Contains adapter implementations for external services (VCS, LLM).
"""

from .vcs.gitlab import GitLabAdapter
from .vcs.local_git import LocalGitAdapter
from .llm.azure import AzureAdapter

__all__ = [
    # VCS Adapters
    "GitLabAdapter",
    "LocalGitAdapter",
    # LLM Adapters
    "AzureAdapter",
]

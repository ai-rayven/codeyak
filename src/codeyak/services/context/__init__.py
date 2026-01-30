"""
Context building services for LLM-guided code review.

This module provides:
- Symbol indexing via tree-sitter parsing
- Skeleton generation (signature-only views of code)
- LLM-guided context planning
- Context rendering for review
"""

from .symbol_index import SymbolIndex, SymbolLocation, SymbolKind
from .skeleton import SkeletonGenerator
from .planner import ContextPlanner, ContextPlan, DiffFileContext, SymbolRequest
from .renderer import ContextRenderer

__all__ = [
    "SymbolIndex",
    "SymbolLocation",
    "SymbolKind",
    "SkeletonGenerator",
    "ContextPlanner",
    "ContextPlan",
    "DiffFileContext",
    "SymbolRequest",
    "ContextRenderer",
]

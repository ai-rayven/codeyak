"""
Domain layer for CodeYak.

Contains all domain models and port interfaces with no external dependencies.
"""

from .models import (
    Guideline,
    GuidelineSetInfo,
    FileDiff,
    MRComment,
    GuidelineViolation,
    ReviewResult,
)
from .exceptions import (
    LineNotInDiffError,
    VCSCommentError,
    VCSFetchCommentsError,
    GuidelinesLoadError,
    BuiltinGuidelineNotFoundError,
    GuidelineIncludeError,
)

__all__ = [
    # Models
    "Guideline",
    "GuidelineSetInfo",
    "FileDiff",
    "MRComment",
    "GuidelineViolation",
    "ReviewResult",
    # Exceptions
    "LineNotInDiffError",
    "VCSCommentError",
    "VCSFetchCommentsError",
    "GuidelinesLoadError",
    "BuiltinGuidelineNotFoundError",
    "GuidelineIncludeError",
]

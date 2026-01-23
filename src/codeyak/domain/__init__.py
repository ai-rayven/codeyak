"""
Domain layer for CodeYak.

Contains all domain models and port interfaces with no external dependencies.
"""

from .models import (
    DiffHunk,
    DiffLine,
    DiffLineType,
    Guideline,
    GuidelineSetInfo,
    FileDiff,
    MRComment,
    GuidelineViolation,
    ReviewResult,
    ChangeSummary,
    ChangeSummaryStructuredOutput,
    MergeRequest
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
    "DiffHunk",
    "DiffLine",
    "DiffLineType",
    "Guideline",
    "GuidelineSetInfo",
    "FileDiff",
    "MRComment",
    "MergeRequest",
    "GuidelineViolation",
    "ReviewResult",
    "ChangeSummary",
    "ChangeSummaryStructuredOutput",

    # Exceptions
    "LineNotInDiffError",
    "VCSCommentError",
    "VCSFetchCommentsError",
    "GuidelinesLoadError",
    "BuiltinGuidelineNotFoundError",
    "GuidelineIncludeError",
]

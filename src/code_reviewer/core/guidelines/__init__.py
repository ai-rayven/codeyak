"""
Guidelines package for code review.

This package provides guideline management and parsing functionality for the code reviewer.
The main entry point is the GuidelinesManager class which handles loading and validating
guideline sets from both built-in and project-specific sources.

Public API:
    GuidelinesManager: Main class for managing guideline sets
    GuidelinesParser: Parser for YAML guideline files (typically used internally)
    Guideline: Model representing a single guideline definition

    Exceptions:
        GuidelinesLoadError: Base exception for guideline loading errors
        BuiltinGuidelineNotFoundError: Raised when built-in guideline not found
        GuidelineIncludeError: Raised when include directive processing fails
"""

from .manager import GuidelinesManager
from .parser import GuidelinesParser
from .models import Guideline
from .exceptions import (
    GuidelinesLoadError,
    BuiltinGuidelineNotFoundError,
    GuidelineIncludeError
)

__all__ = [
    'GuidelinesManager',
    'GuidelinesParser',
    'Guideline',
    'GuidelinesLoadError',
    'BuiltinGuidelineNotFoundError',
    'GuidelineIncludeError',
]

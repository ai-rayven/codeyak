"""
Guidelines package for code review.

This package provides guideline management and parsing functionality for the code reviewer.
The main entry point is the GuidelinesProvider class which handles loading and validating
guideline sets from both built-in and project-specific sources.

Public API:
    GuidelinesProvider: Main class for managing guideline sets
    GuidelinesParser: Parser for YAML guideline files (typically used internally)
    GuidelinesGenerator: Generator for creating guidelines from git history

    Exceptions:
        GuidelinesLoadError: Base exception for guideline loading errors
        BuiltinGuidelineNotFoundError: Raised when built-in guideline not found
        GuidelineIncludeError: Raised when include directive processing fails
"""

from .provider import GuidelinesProvider
from .parser import GuidelinesParser
from .generator import GuidelinesGenerator

__all__ = [
    'GuidelinesProvider',
    'GuidelinesParser',
    'GuidelinesGenerator',
    'GuidelinesLoadError',
    'BuiltinGuidelineNotFoundError',
    'GuidelineIncludeError',
]

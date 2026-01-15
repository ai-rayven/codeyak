"""
Guidelines-specific exceptions.

These exceptions are raised during guideline loading, parsing, and validation.
"""


class GuidelinesLoadError(Exception):
    """
    Raised when guidelines file exists but cannot be loaded.

    This indicates issues such as:
    - Invalid YAML syntax
    - Missing required structure (e.g., 'guidelines' key)
    - Invalid guideline format or validation errors
    - File specified but not found
    """
    pass


class BuiltinGuidelineNotFoundError(GuidelinesLoadError):
    """Raised when a referenced built-in guideline does not exist."""
    pass


class GuidelineIncludeError(GuidelinesLoadError):
    """Raised when there's an error processing an 'includes' directive."""
    pass

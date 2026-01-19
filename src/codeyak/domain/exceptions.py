"""
Core exceptions for the code review system.

These are cross-cutting exceptions used by multiple modules, primarily
for VCS operations and general system errors.
"""


class LineNotInDiffError(Exception):
    """
    Raised when attempting to comment on a line that is not part of the diff.

    This typically happens when a violation is detected on an unchanged line
    that is near the actual changes but not included in the diff itself.
    """
    pass


class VCSCommentError(Exception):
    """
    General error when posting a comment to the VCS fails for reasons
    other than the line not being in the diff.
    """
    pass


class VCSFetchCommentsError(Exception):
    """
    Raised when fetching comments from the VCS fails.

    This is separate from VCSCommentError which is used for posting comments.
    """
    pass

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

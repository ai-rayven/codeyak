"""
Domain-specific exceptions for the code review system.
These provide abstraction from VCS-specific error types.
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

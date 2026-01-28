"""
Feedback publishing service for posting review results to VCS.
"""

from ...domain.models import ReviewResult
from ...domain.exceptions import LineNotInDiffError, VCSCommentError
from ...protocols import VCSClient, FeedbackPublisher
from ...ui import console


class MergeRequestFeedbackPublisher(FeedbackPublisher):
    """
    Publishes review results by posting violations as comments to the VCS.
    """

    def __init__(self, vcs_client: VCSClient, merge_request_id: str):
        """
        Initialize the feedback publisher.

        Args:
            vcs_client: VCS client for posting comments
            merge_request_id: Merge request ID to post comments to
        """
        self.vcs_client = vcs_client
        self.merge_request_id = merge_request_id

    def post_feedback(self, review_result: ReviewResult) -> int:
        """
        Post all violations from a review result as comments on the merge request.

        Filters out low and medium confidence violations and only posts high confidence ones.
        Also filters out false positives (where reasoning indicates no actual violation).
        If posting an inline comment fails due to the line not being in the diff, the comment
        is skipped (only inline comments on actual diff lines are posted).

        Args:
            review_result: Review result containing violations to post

        Returns:
            Number of successfully posted violations
        """
        posted_count = 0
        for violation in review_result.violations:
            # Filter false positives (reasoning indicates no actual violation)
            if violation.is_false_positive():
                console.print(f"     [warning]Skipping false positive:[/warning] [guideline]{violation.guideline_id}[/guideline] in [filepath]{violation.file_path}[/filepath]")
                continue

            # Filter low-confidence violations
            if violation.confidence == "low" or violation.confidence == "medium":
                console.print(f"     [warning]Skipping {violation.confidence}-confidence:[/warning] [guideline]{violation.guideline_id}[/guideline] in [filepath]{violation.file_path}[/filepath]")
                continue

            console.print(f"     [info]Found[/info] [guideline]{violation.guideline_id}[/guideline] in [filepath]{violation.file_path}[/filepath] [muted](confidence: {violation.confidence})[/muted]")
            try:
                self.vcs_client.post_comment(self.merge_request_id, violation)
                posted_count += 1
            except LineNotInDiffError:
                # Line not in diff - skip this comment (only post inline comments)
                console.print(f"[warning]Skipping comment (line not in diff):[/warning] [filepath]{violation.file_path}:{violation.line_number}[/filepath]")
            except VCSCommentError as e:
                # Other VCS error - report it but continue
                console.print(f"[error]Failed to post comment:[/error] {e}")
        return posted_count

    def post_review_summary(
        self,
        total_original_violations: int,
        total_filtered_violations: int
    ) -> None:
        """
        Post a summary message about the review results.

        Posts a success message if no violations were found, or an informational
        message if all violations were filtered as duplicates.

        Args:
            total_original_violations: Total number of violations before filtering duplicates
            total_filtered_violations: Total number of violations after filtering duplicates
        """
        if total_filtered_violations > 0:
            return

        if total_original_violations == 0:
            message = "Nothing major found. Code looks good."
        elif total_filtered_violations == 0:
            message = "No major violations found or were already reported in previous comments."

        try:
            self.vcs_client.post_general_comment(self.merge_request_id, message)
        except VCSCommentError as e:
            console.print(f"[warning]Could not post success comment:[/warning] {e}")

    def post_general_comment(self, message: str) -> None:
        """Post a general comment on the merge request."""
        self.vcs_client.post_general_comment(self.merge_request_id, message)

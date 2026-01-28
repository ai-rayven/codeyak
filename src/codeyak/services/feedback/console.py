"""
Console feedback publisher for outputting review results to the terminal.
"""

from collections import defaultdict
from typing import Dict, List

from ...domain.models import ReviewResult, GuidelineViolation
from ...protocols import FeedbackPublisher
from ...ui import console


class ConsoleFeedbackPublisher(FeedbackPublisher):
    """
    Publishes review results by printing violations to the console.

    Groups violations by file and displays them with line numbers,
    guideline IDs, confidence levels, and reasoning.
    """

    def __init__(self):
        """Initialize the console feedback publisher."""
        self._violations_by_file: Dict[str, List[GuidelineViolation]] = defaultdict(list)
        self._total_posted = 0

    def post_feedback(self, review_result: ReviewResult) -> int:
        """
        Print all violations from a review result to the console.

        Filters out low and medium confidence violations and only shows high confidence ones.

        Args:
            review_result: Review result containing violations to display

        Returns:
            Number of high-confidence violations displayed
        """
        posted_count = 0

        for violation in review_result.violations:
            # Filter low-confidence violations
            if violation.confidence in ("low", "medium"):
                continue

            # Group by file for later display
            self._violations_by_file[violation.file_path].append(violation)
            posted_count += 1

        self._total_posted += posted_count
        return posted_count

    def post_review_summary(
        self,
        total_original_violations: int,
        total_filtered_violations: int
    ) -> None:
        """
        Print a summary of the review results to the console.

        Args:
            total_original_violations: Total number of violations before filtering duplicates
            total_filtered_violations: Total number of violations after filtering duplicates
        """
        console.print()

        if not self._violations_by_file:
            console.print("[success]No high-confidence violations found. Code looks good.[/success]")
        else:
            # Print violations grouped by file
            for file_path in sorted(self._violations_by_file.keys()):
                violations = self._violations_by_file[file_path]
                console.print(f"[filepath]{file_path}[/filepath]")

                # Sort violations by line number
                for violation in sorted(violations, key=lambda v: v.line_number):
                    console.print(
                        f"  [line_number]Line {violation.line_number}[/line_number]: "
                        f"[guideline][{violation.guideline_id}][/guideline] "
                        f"[muted]({violation.confidence})[/muted]"
                    )
                    console.print(f"    {violation.reasoning}")
                console.print()

    def post_general_comment(self, message: str) -> None:
        """No-op for console output - general comments are not printed."""
        pass

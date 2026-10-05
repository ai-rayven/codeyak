"""
JSON feedback publisher for outputting review results as structured JSON.

Used by the --json flag on `yak review` to produce machine-readable output
for integration with Claude Code skills and other tools.
"""

import json
import sys
from collections import defaultdict
from typing import Dict, List

from ...domain.models import ReviewResult, GuidelineViolation
from ...protocols import FeedbackPublisher


class JsonFeedbackPublisher(FeedbackPublisher):
    """
    Publishes review results as a single JSON object to stdout.

    Collects all violations across guideline sets, then dumps them
    as JSON when post_review_summary() is called.
    """

    def __init__(self):
        self._violations: List[GuidelineViolation] = []
        self._total_posted = 0

    def post_feedback(self, review_result: ReviewResult) -> int:
        """
        Collect all violations from a review result.

        Unlike ConsoleFeedbackPublisher, this collects ALL violations
        (including low/medium confidence) for complete stats tracking.

        Returns:
            Number of violations collected
        """
        count = len(review_result.violations)
        self._violations.extend(review_result.violations)
        self._total_posted += count
        return count

    def post_review_summary(
        self,
        total_original_violations: int,
        total_filtered_violations: int,
    ) -> None:
        """
        Dump all collected violations as JSON to stdout.
        """
        output = {
            "violations": [v.model_dump(exclude_none=True) for v in self._violations],
            "total_original": total_original_violations,
            "total_filtered": total_filtered_violations,
        }
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")

    def post_general_comment(self, message: str) -> None:
        """No-op for JSON output."""
        pass

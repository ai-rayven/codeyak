from typing import List
from .ports import VCSClient, LLMClient
from .models import ReviewResult, MRComment
from .grouping import create_file_groups
from .prompts import build_review_messages
from .guidelines import GuidelinesManager
from .exceptions import (
    LineNotInDiffError,
    VCSCommentError,
    VCSFetchCommentsError
)

class ReviewEngine:
    def __init__(
        self,
        vcs: VCSClient,
        llm: LLMClient,
        guidelines: GuidelinesManager
    ):
        self.vcs = vcs
        self.llm = llm
        self.guidelines_manager = guidelines

    def run(self, mr_id: str):
        print(f"Starting review for MR {mr_id}...")

        # 1. Fetch diffs
        diffs = self.vcs.get_diff(mr_id)
        if not diffs:
            print("No changes found.")
            return

        # 1b. Fetch existing comments (non-blocking)
        try:
            existing_comments = self.vcs.get_comments(mr_id)
            print(f"Found {len(existing_comments)} existing comments.")
        except VCSFetchCommentsError as e:
            print(f"⚠️  Could not fetch existing comments: {e}")
            print("Continuing without comment context...")
            existing_comments = []

        # 2. Prepare chunks (once for all guideline sets)
        groups = create_file_groups(diffs)
        print(f"Split {len(diffs)} files into {len(groups)} analysis groups.")

        # 3. Load guideline sets (one per file)
        guideline_sets = self.guidelines_manager.load_guideline_sets()

        # 4. Run focused review for each guideline set
        total_original_violations = 0
        total_filtered_violations = 0

        for filename, guidelines in guideline_sets.items():
            print(f"\n{'='*80}")
            print(f"🔍 Running focused review with {filename} ({len(guidelines)} guidelines)")
            print(f"{'='*80}")

            # Analyze each file group with this guideline set
            for group in groups:
                print(f"   Processing Group {group.group_id} ({len(group.files)} files)...")

                # Build messages with comment context
                messages = build_review_messages(group.files, guidelines, existing_comments)

                result = self.llm.generate(messages, response_model=ReviewResult)

                # Filter duplicates and track both counts
                filtered_result, original_count = self._filter_existing_violations(result, existing_comments)
                total_original_violations += original_count

                violations_count = self._process_results(mr_id, filtered_result)
                total_filtered_violations += violations_count

                print(f" {filtered_result.model_dump_json()}")

        # 5. Post success comment if no violations were detected across all guideline sets
        print(f"\n{'='*80}")
        if total_original_violations == 0:
            success_message = "✅ Code review completed successfully! No guideline violations found."
            try:
                self.vcs.post_general_comment(mr_id, success_message)
                print("No violations found - posted success comment.")
            except VCSCommentError as e:
                print(f"⚠️  Could not post success comment: {e}")
        elif total_filtered_violations == 0:
            print("ℹ️  All detected violations were already reported in existing comments.")

        print("✅ Review complete.")

    def _process_results(self, mr_id: str, result: ReviewResult) -> int:
        """Iterates through findings and posts them to the VCS. Returns count of violations."""
        for violation in result.violations:
            print(f"     found {violation.guideline_id} in {violation.file_path}")
            try:
                self.vcs.post_comment(mr_id, violation)
            except LineNotInDiffError:
                # Line not in diff - post as general comment instead
                try:
                    self.vcs.post_general_comment(mr_id, violation.to_general_comment())
                    print(f"⚠️  Posted as general comment (line not in diff): {violation.file_path}:{violation.line_number}")
                except VCSCommentError as e:
                    print(f"❌ Failed to post general comment: {e}")
            except VCSCommentError as e:
                # Other VCS error - report it but continue
                print(f"❌ Failed to post comment: {e}")
        return len(result.violations)

    def _filter_existing_violations(
        self,
        result: ReviewResult,
        existing_comments: List[MRComment]
    ) -> tuple[ReviewResult, int]:
        """
        Filter out violations that overlap with existing comments.

        Returns:
            tuple: (filtered_result, original_count)
                - filtered_result: ReviewResult with duplicates removed
                - original_count: Number of violations before filtering
        """
        original_count = len(result.violations)

        if not existing_comments:
            return result, original_count

        filtered_violations = []
        filtered_count = 0

        for violation in result.violations:
            is_duplicate = any(
                comment.overlaps_with_violation(violation)
                for comment in existing_comments
            )

            if is_duplicate:
                print(f"     ⏭️  Skipping duplicate: {violation.guideline_id} at {violation.file_path}:{violation.line_number}")
                filtered_count += 1
            else:
                filtered_violations.append(violation)

        if filtered_count > 0:
            print(f"     Filtered {filtered_count} duplicate violations")

        return ReviewResult(violations=filtered_violations), original_count

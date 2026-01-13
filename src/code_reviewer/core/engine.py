from typing import List
import json
from .ports import VCSClient, LLMClient
from .models import Guideline, ReviewResult, MRComment
from .grouping import create_file_groups
from .prompts import build_review_messages
from .exceptions import LineNotInDiffError, VCSCommentError, VCSFetchCommentsError

class ReviewEngine:
    def __init__(self, vcs: VCSClient, llm: LLMClient):
        self.vcs = vcs
        self.llm = llm

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

        # 2. Prepare chunks
        groups = create_file_groups(diffs)
        guidelines = self._load_guidelines()
        print(f"Split {len(diffs)} files into {len(groups)} analysis groups.")

        # 3. Analyze each group
        total_violations = 0
        for group in groups:
            print(f"   Processing Group {group.group_id} ({len(group.files)} files)...")

            # Build messages with comment context
            messages = build_review_messages(group.files, guidelines, existing_comments)

            result = self.llm.generate(messages, response_model=ReviewResult)

            # Filter duplicates
            filtered_result = self._filter_existing_violations(result, existing_comments)

            violations_count = self._process_results(mr_id, filtered_result)
            total_violations += violations_count

            print(f" {filtered_result.model_dump_json()}")

        # 4. Post success if no violations
        if total_violations == 0:
            success_message = "✅ Code review completed successfully! No guideline violations found."
            try:
                self.vcs.post_general_comment(mr_id, success_message)
                print("No violations found - posted success comment.")
            except VCSCommentError as e:
                print(f"⚠️  Could not post success comment: {e}")

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
    ) -> ReviewResult:
        """Filter out violations that overlap with existing comments."""
        if not existing_comments:
            return result

        filtered_violations = []
        filtered_count = 0

        for violation in result.violations:
            is_duplicate = any(
                comment.overlaps_with_violation(violation)
                for comment in existing_comments
            )

            if is_duplicate:
                print(f"     ⏭️  Skipping duplicate: {violation.file_path}:{violation.line_number}")
                filtered_count += 1
            else:
                filtered_violations.append(violation)

        if filtered_count > 0:
            print(f"     Filtered {filtered_count} duplicate violations")

        return ReviewResult(violations=filtered_violations)

    def _load_guidelines(self) -> List[Guideline]:
        """
        V1: Hardcoded rules.
        V2: Load from guidelines.md or a database.
        """
        return [
            Guideline(
                id="SEC-01",
                description="Avoid hardcoded secrets, API keys, or passwords."
            ),
            Guideline(
                id="STYLE-01",
                description="No long functions."
            ),
            Guideline(
                id="STYLE-02",
                description="The code must be very easy to read and understand."
            ),
            Guideline(
                id="STYLE-03",
                description="No long functions and no God services."
            ),
            Guideline(
                id="ERR-01",
                description="Do not catch exceptions unless you are handling them. Let them bubble up.",
            ),
        ]
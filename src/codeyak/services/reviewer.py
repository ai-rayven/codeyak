from typing import Any, ContextManager, Dict, List, Tuple
from contextlib import nullcontext
from codeyak.protocols import LLMClient, FeedbackPublisher
from codeyak.domain.models import ChangeSummary, Guideline, MergeRequest, ReviewResult, MRComment
from codeyak.domain.constants import CODE_FILE_EXTENSIONS
from langfuse import propagate_attributes

from .guidelines import GuidelinesProvider
from .context import CodeReviewContextBuilder
from .code import CodeProvider
from .summary import SummaryGenerator


class CodeReviewer:
    def __init__(
        self,
        context: CodeReviewContextBuilder,
        code: CodeProvider,
        guidelines: GuidelinesProvider,
        llm: LLMClient,
        feedback: FeedbackPublisher,
        summary: SummaryGenerator,
        langfuse=None,
    ):
        self.context = context
        self.code = code
        self.llm = llm
        self.guidelines = guidelines
        self.feedback = feedback
        self.summary = summary
        self.langfuse = langfuse

    def _start_trace(self, merge_request: MergeRequest) -> Tuple[Any, ContextManager]:
        """Start Langfuse trace and return (trace, propagate_context)."""
        if not self.langfuse:
            return None, nullcontext()

        # Build detailed file info for trace
        files_info = []
        for diff in merge_request.file_diffs:
            file_info = {
                "file_path": diff.file_path,
                "full_file_lines": len(diff.full_content.splitlines()) if diff.full_content else 0,
                "diff_lines": len(diff.format_with_line_numbers().splitlines()) if diff.hunks else 0,
            }
            files_info.append(file_info)

        trace = self.langfuse.start_span(
            name="review_code",
            input={
                "file_count": len(merge_request.file_diffs),
                "files": files_info,
            },
            metadata={"merge_request_id": merge_request.id},
        )
        context = propagate_attributes(
            user_id=merge_request.author or "local",
            session_id=merge_request.id
        )
        return trace, context

    def review_merge_request(self, merge_request_id: str):
        print(f"Starting review for MR {merge_request_id}...")

        # Load data first
        guideline_sets = self.guidelines.load_guidelines_from_vcs(
            merge_request_id=merge_request_id
        )

        merge_request = self.code.get_merge_request(
            merge_request_id=merge_request_id,
            extension_filters=CODE_FILE_EXTENSIONS
        )

        # Start trace
        trace, propagate_context = self._start_trace(merge_request)

        with propagate_context:
            self._run_review(
                merge_request=merge_request,
                guideline_sets=guideline_sets,
                trace=trace,
                generate_summary=True,
            )

        print("✅ Review complete.")

    def _get_review_result_traced(
        self,
        merge_request: MergeRequest,
        change_summary: ChangeSummary,
        guidelines_filename: str,
        guidelines: List[Guideline],
        trace
    ) -> ReviewResult:
        """
        Generate review result using LLM with Langfuse tracing.

        Args:
            merge_request: The merge request containing file diffs and comments
            guidelines: List of guidelines to apply during review
            trace: Langfuse trace object (None if tracing disabled)

        Returns:
            ReviewResult: The generated review result from the LLM
        """
        # Build messages with full context
        messages = self.context.build_review_messages(
            merge_request,
            change_summary,
            guidelines
        )

        # Start generation span if tracing enabled
        generation = None
        if trace:
            generation = trace.start_generation(
                name=f"generate_guideline_violations::{guidelines_filename}",
                input=messages,  # Full ChatML format
            )

        # Call LLM
        output = self.llm.generate(messages, response_model=ReviewResult)

        # End generation with output
        if generation:
            generation.update(
                model=output.model,
                output=output.result.model_dump_json(),
                usage_details={
                    "input": output.token_usage.prompt_tokens,
                    "output": output.token_usage.completion_tokens,
                }
            )
            generation.end()

        return output.result

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

    def _generate_and_post_summary(self, merge_request: MergeRequest, trace=None):
        """
        Generate and post MR summary.

        Args:
            merge_request: MergeRequest object with diffs, commits, and id
            trace: Langfuse trace object (None if tracing disabled)
        """
        print(f"\n{'='*80}")
        print("📋 Generating MR summary...")
        print(f"{'='*80}")

        # Generate summary using LLM (with tracing)
        summary = self.summary.generate_summary(merge_request, trace)

        # Format and post as general comment
        print(f"Summary: {summary.summary}")

        self.feedback.post_general_comment(summary.summary)
        print("✅ Summary posted")

        return summary

    def _run_review(
        self,
        merge_request: MergeRequest,
        guideline_sets: Dict[str, List[Guideline]],
        trace=None,
        generate_summary: bool = True,
        is_local: bool = False
    ) -> None:
        """
        Core review loop: generate summary (optional), loop guideline sets,
        call LLM, filter duplicates, and post feedback.

        Args:
            merge_request: The merge request containing file diffs and comments
            guideline_sets: Dictionary mapping filename to list of guidelines
            trace: Langfuse trace object (None if tracing disabled)
            generate_summary: Whether to generate and post a summary
        """
        # Generate and post summary if requested
        summary = None
        if generate_summary:
            summary = self._generate_and_post_summary(merge_request, trace)

        # Run focused review for each guideline set
        total_original_violations = 0
        total_filtered_violations = 0

        for filename, guidelines in guideline_sets.items():
            print(f"\n{'='*80}")
            print(f"🔍 Running focused review with {filename} ({len(guidelines)} guidelines)")
            print(f"{'='*80}")

            result = self._get_review_result_traced(merge_request, summary, filename, guidelines, trace)
            print(result.model_dump_json())

            # Filter duplicates and track both counts
            filtered_result, original_count = self._filter_existing_violations(
                result,
                merge_request.comments
            )
            total_original_violations += original_count

            violations_count = self.feedback.post_feedback(filtered_result)
            total_filtered_violations += violations_count

        # Update trace with results
        if trace:
            tags = [merge_request.project_name or "local"]
            if summary:
                tags.extend([summary.scope.type.value, summary.scope.size.value])
            if total_filtered_violations == 0:
                tags.append("no_violations")
            if is_local:
                tags.append("local")
            else:
                tags.append("remote")
            trace.update_trace(output={"violation_count": total_filtered_violations}, tags=tags)
            trace.end()

        # Post review summary
        print(f"\n{'='*80}")
        self.feedback.post_review_summary(
            total_original_violations,
            total_filtered_violations
        )

    def review_local_changes(self) -> None:
        """
        Review local uncommitted changes.

        Uses CodeProvider to get filtered diffs as a MergeRequest,
        loads guidelines locally, and runs the review without summary generation.
        """
        print("Starting review of local changes...")

        # Get merge request with filtered diffs
        merge_request = self.code.get_merge_request(
            merge_request_id="local",
            extension_filters=CODE_FILE_EXTENSIONS
        )

        # Check for empty diff
        if not merge_request.file_diffs:
            print("No code file changes found.")
            return

        print(f"Found changes in {len(merge_request.file_diffs)} code file(s).")

        # Load guidelines locally
        guideline_sets = self.guidelines.load_guidelines_local()

        # Start trace (now enabled for local reviews)
        trace, propagate_context = self._start_trace(merge_request)

        with propagate_context:
            self._run_review(
                merge_request=merge_request,
                guideline_sets=guideline_sets,
                trace=trace,
                generate_summary=False,
                is_local=True
            )

        print("✅ Review complete.")

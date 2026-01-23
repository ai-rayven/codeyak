from typing import List
from contextlib import nullcontext
from codeyak.protocols import LLMClient
from codeyak.domain.models import ChangeSummary, Guideline, MergeRequest, ReviewResult, MRComment
from langfuse import propagate_attributes

from .guidelines import GuidelinesProvider
from .context import CodeReviewContextBuilder
from .code import CodeProvider
from .feedback import FeedbackPublisher
from .summary import SummaryGenerator

# Known code file extensions to filter in merge requests
CODE_FILE_EXTENSIONS = [
    '.py',      # Python
    '.js',      # JavaScript
    '.ts',      # TypeScript
    '.jsx',     # React JavaScript
    '.tsx',     # React TypeScript
    '.java',    # Java
    '.kt',      # Kotlin
    '.go',      # Go
    '.rs',      # Rust
    '.c',       # C
    '.cpp',     # C++
    '.cc',      # C++
    '.h',       # C/C++ header
    '.hpp',     # C++ header
    '.cs',      # C#
    '.rb',      # Ruby
    '.php',     # PHP
    '.swift',   # Swift
    '.m',       # Objective-C
    '.scala',   # Scala
    '.sh',      # Shell script
    '.bash',    # Bash script
    '.yaml',    # YAML
    '.yml',     # YAML
    '.json',    # JSON
    '.xml',     # XML
    '.sql',     # SQL
    '.html',    # HTML
    '.css',     # CSS
    '.scss',    # SCSS
    '.sass',    # Sass
    '.vue',     # Vue
]


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

        # Start Langfuse trace if enabled
        trace = None
        if self.langfuse:
            trace = self.langfuse.start_span(
                name="review_code",
                input={"file_count": len(merge_request.file_diffs)},
                metadata={"merge_request_id": merge_request.id},
            )

        # Use propagate_attributes to propagate user_id, session_id, and tags to all child observations
        propagate_context = (
            propagate_attributes(
                user_id=merge_request.author,
                session_id=merge_request.id
            ) if trace else nullcontext()
        )

        with propagate_context:
            # Generate and post summary BEFORE reviews
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

                violations_count = self.feedback.post_feedback(
                    merge_request_id,
                    filtered_result
                )
                total_filtered_violations += violations_count

            # Update trace with results
            if trace:
                # Add no_violations tag if applicable
                tags = [summary.scope.type.value, summary.scope.size.value, merge_request.project_name]
                if total_filtered_violations == 0:
                    tags.append("no_violations")
                # Set output and tags on trace
                trace.update_trace(output={"violation_count": total_filtered_violations}, tags=tags)
                trace.end()

        # Post review summary
        print(f"\n{'='*80}")
        self.feedback.post_review_summary(
            merge_request_id,
            total_original_violations,
            total_filtered_violations
        )
        print("✅ Review complete.")

    def _get_review_result(self, merge_request: MergeRequest, guidelines: List[Guideline]) -> ReviewResult:
        """
        Generate review result using LLM for the given guidelines.

        Args:
            merge_request: The merge request containing file diffs and comments
            guidelines: List of guidelines to apply during review

        Returns:
            ReviewResult: The generated review result from the LLM
        """
        # Build messages with comment context
        messages = self.context.build_review_messages(merge_request.file_diffs, guidelines, merge_request.comments)

        output = self.llm.generate(messages, response_model=ReviewResult)

        return output.result

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

        self.feedback.vcs_client.post_general_comment(merge_request.id, summary.summary)
        print("✅ Summary posted")

        return summary

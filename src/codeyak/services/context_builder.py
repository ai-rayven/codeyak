import logging
import time
from pathlib import Path
from typing import List, Optional

from codeyak.domain.models import (
    ChangeSummary,
    FileDiff,
    Guideline,
    MRComment,
    MergeRequest
)
from codeyak.protocols import LLMClient, ProgressReporter
from codeyak.ui import NullProgressReporter
from codeyak.ui.progress import format_duration
from codeyak.services.context.symbol_index import SymbolIndex
from codeyak.services.context.skeleton import SkeletonGenerator
from codeyak.services.context.planner import ContextPlanner
from codeyak.services.context.renderer import ContextRenderer

logger = logging.getLogger(__name__)


class CodeReviewContextBuilder:
    """Builder for constructing code review context messages for LLM analysis."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        repo_path: Path | None = None,
        use_smart_context: bool = True,
        progress: ProgressReporter | None = None,
    ) -> None:
        """
        Initialize the context builder.
        
        Args:
            llm_client: LLM client for context planning (required if use_smart_context=True)
            repo_path: Repository root path (required if use_smart_context=True)
            use_smart_context: Whether to use LLM-guided context planning
            progress: Progress reporter for displaying status and timing
        """
        self.llm_client = llm_client
        self.repo_path = repo_path
        self.use_smart_context = use_smart_context
        self.progress = progress or NullProgressReporter()

    def build_smart_context(self, diffs: List[FileDiff], trace=None) -> str | None:
        """
        Build smart context for the given diffs.
        
        Shows progress spinner and timing. Call this once before reviewing
        multiple guideline sets to avoid rebuilding context.
        
        Args:
            diffs: List of file diffs to analyze
            trace: Langfuse trace/span object for tracing (optional)
        
        Returns:
            Smart context string, or None if not enabled/available
        """
        if not (self.use_smart_context and self.llm_client and self.repo_path and diffs):
            return None
        
        start_time = time.monotonic()
        self.progress.start_status("Building context...")
        
        try:
            result = self._build_smart_context_internal(diffs, trace=trace)
            elapsed = time.monotonic() - start_time
            self.progress.stop_status()
            self.progress.success(f"Context built in {format_duration(elapsed)}")
            return result
        except Exception:
            logger.exception("Failed to build smart context")
            elapsed = time.monotonic() - start_time
            self.progress.stop_status()
            self.progress.warning(f"Context building failed after {format_duration(elapsed)}")
            return None

    def build_review_messages(
        self,
        merge_request: MergeRequest,
        change_summary: Optional[ChangeSummary],
        guidelines: List[Guideline],
        trace=None,
        smart_context: str | None = None,
    ) -> List[dict]:
        """
        Build structured messages for code review analysis.

        Args:
            merge_request: MergeRequest containing file diffs and comments
            change_summary: Optional summary of changes (can be None for local reviews)
            guidelines: List of guidelines to check against
            trace: Langfuse trace/span object for tracing (optional)
            smart_context: Pre-built smart context string (from build_smart_context())

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        existing_comments = merge_request.comments
        diffs = merge_request.file_diffs

        messages = []

        # System message with guidelines
        system_content = self._build_system_prompt(guidelines, existing_comments)
        messages.append({"role": "system", "content": system_content})

        # TODO: Look for README.md, AGENTS.md or CLAUDE.md to get context for the project and add also

        # Use pre-built smart context if provided
        if smart_context:
            messages.append({"role": "user", "content": smart_context})

        # Change summary (if available)
        if change_summary:
            summary_content = self._format_change_summary(change_summary)
            messages.append({"role": "user", "content": summary_content})

        # Separate user message(s) for existing comments
        if existing_comments:
            comments_content = self._format_existing_comments(existing_comments)
            messages.append({"role": "user", "content": comments_content})

        # Separate user message for each file + diff
        for diff in diffs:
            file_content = self._format_file_diff(diff)
            messages.append({"role": "user", "content": file_content})

        # Final user message
        messages.append({"role": "user", "content": "Review the provided file changes"})

        return messages

    def _build_system_prompt(
        self,
        guidelines: List[Guideline],
        existing_comments: Optional[List[MRComment]] = None
    ) -> str:
        """Build the system prompt defining persona and rules."""
        content = (
            "You are an automated code review agent. "
            "Your task is to contextually evaluate code changes against the provided guidelines.\n\n"
            "Provide your findings in an easy to understand fashion with analogies if relevant to help developers understand the impact of the change.\n\n"
            "REMEMBER to ALWAYS provide accurate line numbers from the diff\n\n"
            "Guidelines:\n"
        )

        for g in guidelines:
            content += f"- [{g.id}] {g.description}\n"

        content += (
            "\nInstructions:\n"
            "1. Only report ACTUAL violations of the specific guidelines listed above.\n"
            "2. DO NOT include entries where no violation was found - only report real problems.\n"
            "3. Evaluate the code changes shown in the diff carefully.\n"
            "4. Distinguish between test code and production code.\n"
            "5. Look for project-specific patterns and conventions that may address concerns.\n"
            "6. Set confidence to 'low' if you're uncertain due to missing context.\n"
            "7. Set confidence to 'high' only for clear, unambiguous violations.\n"
            "8. Ignore general best practices not in the list.\n"
            "9. If there are no violations, return an empty list - do not add positive comments.\n"
        )

        if existing_comments:
            content += (
                "10. You have access to existing review comments below. "
                "Use them as context but still report any violations you find. "
                "The system will deduplicate overlapping comments.\n"
            )

        content += (
            "\nCode Suggestions:\n"
            "When you find a violation, you may optionally provide a `suggested_code` fix. "
            "This will be rendered as an applicable GitLab suggestion that reviewers can accept with one click.\n\n"
            "DO provide a suggestion when:\n"
            "- The fix is mechanical and unambiguous (wrong name, missing check, incorrect import, hardcoded value)\n"
            "- There is only one reasonable way to fix it\n"
            "- The scope is small (1-5 lines)\n\n"
            "DO NOT provide a suggestion when:\n"
            "- The violation is architectural or design-level (e.g., class has too many responsibilities)\n"
            "- Multiple valid fixes exist and the choice is ambiguous\n"
            "- The fix requires changes across multiple locations\n"
            "- Your confidence is low or medium\n"
            "- The violation is about missing functionality rather than incorrect code\n\n"
            "When providing a suggestion:\n"
            "- `suggested_code` must be the complete replacement text for the affected line range\n"
            "- Preserve the original indentation style exactly\n"
            "- Use `suggestion_lines_above` and `suggestion_lines_below` (default 0) for multi-line replacements "
            "that span beyond the single `line_number`\n"
        )

        return content

    def _format_existing_comments(self, comments: List[MRComment]) -> str:
        """Format existing comments for context."""
        inline_comments = [c for c in comments if c.is_inline]
        general_comments = [c for c in comments if not c.is_inline]

        if not (inline_comments or general_comments):
            return ""

        content = "=== EXISTING REVIEW COMMENTS ===\n\n"

        if inline_comments:
            content += "Inline Comments:\n"
            for comment in inline_comments:
                content += (
                    f"- [{comment.author}] {comment.file_path}:{comment.line_number}\n"
                    f"  {comment.body}\n\n"
                )

        if general_comments:
            content += "General Comments:\n"
            for comment in general_comments:
                content += f"- [{comment.author}] {comment.body}\n\n"

        content += "=== END EXISTING COMMENTS ===\n\n"
        return content

    def _format_file_diff(self, diff: FileDiff) -> str:
        """Format a single file diff with line numbers."""
        content = f"--- FILE: {diff.file_path} ---\n"

        # For new files, only show full content with line numbers (diff would be redundant)
        if diff.is_new_file:
            content += "NEW FILE:\n"
            content += diff.format_content_with_line_numbers()
            content += "\n"
            return content

        # Include diff with line numbers (shows what changed)
        content += "CHANGES (what was modified):\n"
        content += diff.format_with_line_numbers()
        content += "\n"

        return content

    def _format_change_summary(self, change_summary: ChangeSummary) -> str:
        """Format the change summary for the LLM."""
        content = "=== CHANGE SUMMARY ===\n\n"
        content += f"**Scope**: {change_summary.scope}\n\n"
        content += f"**Summary**:\n{change_summary.summary}\n\n"
        content += "Use this high-level context to understand the purpose of the changes "
        content += "you are reviewing. The detailed file diffs follow below.\n\n"
        content += "=== END CHANGE SUMMARY ===\n\n"
        return content

    def _build_smart_context_internal(self, diffs: List[FileDiff], trace=None) -> str:
        """
        Internal method to build smart context using LLM-guided planning.
        
        This method:
        1. Builds a symbol index of the codebase using tree-sitter
        2. Asks the LLM what context is needed based on the diff
        3. Renders skeleton views with expanded regions around changes
        4. Includes related symbols from other files
        
        Note: Use build_smart_context() for the public API with progress reporting.
        
        Args:
            diffs: List of file diffs to analyze
            trace: Langfuse trace/span object for tracing (optional)
        
        Returns:
            Formatted context string, or empty string if building fails
        """
        if not self.llm_client or not self.repo_path:
            return ""
        
        # Start build_context span if tracing enabled
        span = None
        if trace:
            span = trace.start_span(
                name="build_context",
                input={"file_count": len(diffs)},
            )
        
        try:
            # Build symbol index
            index = SymbolIndex.build(self.repo_path)
            
            # Create context plan via LLM (pass span so generation is a child)
            planner = ContextPlanner(self.llm_client)
            plan = planner.plan_from_file_diffs(diffs, trace=span)
            
            # Render context
            skeleton = SkeletonGenerator()
            renderer = ContextRenderer(index, skeleton, self.repo_path)
            
            result = renderer.render(plan, diffs)
            
            # End span with output metadata and rendered content
            if span:
                total_context_lines = sum(
                    f.lines_before + f.lines_after for f in plan.diff_files
                )
                span.update(
                    output={
                        "symbols_requested": len(plan.related_symbols),
                        "total_context_lines": total_context_lines,
                        "diff_files_count": len(plan.diff_files),
                        "rendered_context": result,
                    }
                )
                span.end()
            
            return result
        except Exception:
            if span:
                span.end()
            raise

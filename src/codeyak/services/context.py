from typing import List, Optional
from codeyak.domain.models import (
    ChangeSummary,
    FileDiff,
    Guideline,
    MRComment,
    MergeRequest
)


class CodeReviewContextBuilder:
    """Builder for constructing code review context messages for LLM analysis."""

    def build_review_messages(
        self,
        merge_request: MergeRequest,
        change_summary: ChangeSummary,
        guidelines: List[Guideline],
    ) -> List[dict]:
        """
        Build structured messages for code review analysis.

        Args:
            diffs: List of file diffs to review
            guidelines: List of guidelines to check against
            existing_comments: Optional list of existing MR comments for context

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

        # Change summary
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
            "Provide your findings in an easy to understand fashion with analogies if relevant to help developers understand the impact of the change."
            "Guidelines:\n"
        )

        for g in guidelines:
            content += f"- [{g.id}] {g.description}\n"

        content += (
            "\nInstructions:\n"
            "1. Only report violations of the specific guidelines listed above.\n"
            "2. Consider the full file context when evaluating changes - not just the diff.\n"
            "3. Distinguish between test code and production code.\n"
            "4. Look for project-specific patterns and conventions that may address concerns.\n"
            "5. Set confidence to 'low' if you're uncertain due to missing context.\n"
            "6. Set confidence to 'high' only for clear, unambiguous violations.\n"
            "7. Ignore general best practices not in the list.\n"
        )

        if existing_comments:
            content += (
                "8. You have access to existing review comments below. "
                "Use them as context but still report any violations you find. "
                "The system will deduplicate overlapping comments.\n"
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

        # Include full file if available (for context)
        if diff.full_content:
            content += "FULL FILE CONTENT (for context):\n```\n"
            content += diff.full_content
            content += "\n```\n\n"

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

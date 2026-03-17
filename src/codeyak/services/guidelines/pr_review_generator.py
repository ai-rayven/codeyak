"""
Guidelines generator from MR review comment analysis.

Analyzes reviewer comments on merged merge requests to identify patterns
of issues that reviewers repeatedly catch, then generates guidelines to
help prevent those recurring mistakes.
"""

import re
from contextlib import nullcontext
from typing import List, Optional

from langfuse import propagate_attributes

from codeyak.protocols import LLMClient, ProgressReporter
from codeyak.infrastructure.vcs.gitlab import GitLabAdapter
from codeyak.domain.models import (
    MRComment,
    MRSummary,
    ReviewLesson,
    ReviewLessonExtractionResult,
    GeneratedGuideline,
    GuidelineGenerationResult,
    ConsolidatedGuidelines,
)
from codeyak.ui import NullProgressReporter


# Patterns for trivial/noise comments
TRIVIAL_PATTERNS = re.compile(
    r'^(\s*('
    r'lgtm|looks good|approved|\+1|ship it|nice|great|thanks|thank you'
    r'|nit|minor|typo|:[\w+-]+:'  # emoji shortcodes
    r')\s*[.!]?\s*)$',
    re.IGNORECASE,
)

# GitLab system note patterns
SYSTEM_NOTE_PATTERNS = re.compile(
    r'^(merged|approved this merge request|assigned to|unassigned|'
    r'changed the description|added \d+ commit|mentioned in|'
    r'marked this merge request as|closed via|reopened)',
    re.IGNORECASE,
)

BOT_PATTERNS = re.compile(r'bot|ci[-_]?bot|automation|jenkins|gitlab', re.IGNORECASE)


class PRReviewGuidelinesGenerator:
    """
    Generates code review guidelines from MR review comment analysis.

    Analyzes reviewer feedback on merged merge requests to identify recurring
    patterns that reviewers catch, then synthesizes actionable guidelines.
    """

    COMMENT_BATCH_SIZE = 20
    MAX_DIFF_LINES = 150
    MAX_FINAL_GUIDELINES = 20

    def __init__(
        self,
        gitlab_vcs: GitLabAdapter,
        llm: LLMClient,
        langfuse=None,
        progress: ProgressReporter | None = None,
    ):
        self.gitlab_vcs = gitlab_vcs
        self.llm = llm
        self.langfuse = langfuse
        self.progress = progress or NullProgressReporter()

    def generate_from_mr(
        self,
        mr_iid: str,
        existing_guidelines: list[dict] | None = None,
    ) -> str | None:
        """
        Generate guidelines from a single MR's review comments.

        Args:
            mr_iid: MR internal ID
            existing_guidelines: Optional existing guidelines to deduplicate against

        Returns:
            YAML string of suggested guidelines
        """
        project_name = self.gitlab_vcs.get_project_name()
        trace, propagate_context = self._start_trace(project_name, f"mr_{mr_iid}")

        with propagate_context:
            return self._generate_from_mr_traced(
                mr_iid=mr_iid,
                project_name=project_name,
                trace=trace,
                existing_guidelines=existing_guidelines,
            )

    def generate_from_mrs(
        self,
        since_days: int = 365,
        existing_guidelines: list[dict] | None = None,
    ) -> str | None:
        """
        Generate guidelines from all merged MRs in a date range.

        Args:
            since_days: Analyze MRs merged within this many days
            existing_guidelines: Optional existing guidelines to deduplicate against

        Returns:
            YAML string of suggested guidelines
        """
        project_name = self.gitlab_vcs.get_project_name()
        trace, propagate_context = self._start_trace(project_name, f"mrs_{since_days}d")

        with propagate_context:
            return self._generate_from_mrs_traced(
                since_days=since_days,
                project_name=project_name,
                trace=trace,
                existing_guidelines=existing_guidelines,
            )

    # --- Traced pipelines ---

    def _generate_from_mr_traced(
        self,
        mr_iid: str,
        project_name: str,
        trace,
        existing_guidelines: list[dict] | None = None,
    ) -> str:
        """Single-MR pipeline."""
        # Fetch MR author and comments
        mr_author = self.gitlab_vcs.get_mr_author(mr_iid)
        comments = self.gitlab_vcs.get_comments(mr_iid)
        self.progress.info(f"Fetched {len(comments)} comments from MR !{mr_iid}.")

        # Filter to substantive reviewer feedback
        filtered = self._filter_review_comments(comments, mr_author)
        self.progress.info(f"Filtered to {len(filtered)} substantive reviewer comments.")

        if not filtered:
            self.progress.warning("No substantive reviewer comments found.")
            self._end_trace(trace, 0, project_name, "no_comments")
            return self._format_empty_yaml()

        # Fetch diff summary for context
        diff_summary = self.gitlab_vcs.get_mr_diff_summary(mr_iid, max_lines=self.MAX_DIFF_LINES)

        # Extract lessons
        self.progress.start_status("Extracting lessons...")
        try:
            lessons = self._extract_review_lessons(
                comments=filtered,
                mr_id=mr_iid,
                diff_summary=diff_summary,
                trace=trace,
            )
        finally:
            self.progress.stop_status()

        self.progress.info(f"Extracted {len(lessons)} lessons.")

        if not lessons:
            self.progress.warning("No lessons extracted from reviewer comments.")
            self._end_trace(trace, 0, project_name, "no_lessons")
            return self._format_empty_yaml()

        return self._synthesize_and_format(
            lessons=lessons,
            trace=trace,
            project_name=project_name,
            existing_guidelines=existing_guidelines,
        )

    def _generate_from_mrs_traced(
        self,
        since_days: int,
        project_name: str,
        trace,
        existing_guidelines: list[dict] | None = None,
    ) -> str:
        """Multi-MR pipeline."""
        self.progress.info(f"Fetching merged MRs from the last {since_days} days...")
        mrs = self.gitlab_vcs.list_merged_mrs(since_days=since_days)

        if not mrs:
            self.progress.warning("No merged MRs found in the specified time range.")
            self._end_trace(trace, 0, project_name, "no_mrs")
            return self._format_empty_yaml()

        self.progress.info(f"Found {len(mrs)} merged MRs.")

        # Extract lessons from each MR
        all_lessons: List[ReviewLesson] = []

        task = self.progress.start_progress("Analyzing MR reviews...", total=len(mrs))
        try:
            for mr_summary in mrs:
                self.progress.update_progress(
                    task,
                    f"Analyzing MR !{mr_summary.iid}: {mr_summary.title[:40]}"
                )

                mr_lessons = self._process_single_mr(mr_summary, trace=trace)
                all_lessons.extend(mr_lessons)
                self.progress.advance_progress(task)
        finally:
            self.progress.stop_progress()

        self.progress.info(f"Extracted {len(all_lessons)} lessons from {len(mrs)} MRs.")

        if not all_lessons:
            self.progress.warning("No lessons extracted from any MR review comments.")
            self._end_trace(trace, 0, project_name, "no_lessons")
            return self._format_empty_yaml()

        return self._synthesize_and_format(
            lessons=all_lessons,
            trace=trace,
            project_name=project_name,
            existing_guidelines=existing_guidelines,
        )

    def _process_single_mr(
        self,
        mr_summary: MRSummary,
        trace=None,
    ) -> List[ReviewLesson]:
        """Fetch and process review comments for a single MR."""
        try:
            mr_author = self.gitlab_vcs.get_mr_author(mr_summary.iid)
            comments = self.gitlab_vcs.get_comments(mr_summary.iid)
        except Exception:
            return []

        filtered = self._filter_review_comments(comments, mr_author)
        if not filtered:
            return []

        diff_summary = self.gitlab_vcs.get_mr_diff_summary(
            mr_summary.iid, max_lines=self.MAX_DIFF_LINES
        )

        return self._extract_review_lessons(
            comments=filtered,
            mr_id=mr_summary.iid,
            diff_summary=diff_summary,
            trace=trace,
        )

    # --- Comment Filtering ---

    def _filter_review_comments(
        self,
        comments: List[MRComment],
        mr_author: str,
    ) -> List[MRComment]:
        """Filter MR comments to only substantive reviewer feedback."""
        filtered = []
        for comment in comments:
            # Skip MR author's own comments
#            if comment.author == mr_author:
                #continue

            # Skip bot comments
            if BOT_PATTERNS.search(comment.author):
                continue

            # Skip CodeYak-generated comments
            if comment.is_codeyak_summary() or comment.guideline_id:
                continue

            # Skip very short comments
            body = comment.body.strip()
            if len(body) < 20:
                continue

            # Skip trivial comments (LGTM, +1, etc.)
            if TRIVIAL_PATTERNS.match(body):
                continue

            # Skip GitLab system notes
            if SYSTEM_NOTE_PATTERNS.match(body):
                continue

            filtered.append(comment)

        return filtered

    # --- Lesson Extraction ---

    def _extract_review_lessons(
        self,
        comments: List[MRComment],
        mr_id: str,
        diff_summary: str,
        trace=None,
    ) -> List[ReviewLesson]:
        """Extract lessons from review comments using LLM."""
        messages = self._build_review_lesson_extraction_messages(comments, mr_id, diff_summary)

        generation = None
        if trace:
            generation = trace.start_generation(
                name=f"extract_review_lessons_mr_{mr_id}",
                input=messages,
            )

        response = self.llm.generate(messages, response_model=ReviewLessonExtractionResult)

        if generation:
            generation.update(
                model=response.model,
                output=response.result.model_dump_json(),
                usage_details={
                    "input": response.token_usage.prompt_tokens,
                    "output": response.token_usage.completion_tokens,
                }
            )
            generation.end()

        return response.result.lessons

    def _build_review_lesson_extraction_messages(
        self,
        comments: List[MRComment],
        mr_id: str,
        diff_summary: str,
    ) -> List[dict]:
        """Build LLM prompt for extracting lessons from reviewer comments."""
        system_prompt = """You are analyzing code review comments from merged merge requests to identify what reviewers repeatedly catch.

For each substantive review comment, extract:
- **what_was_caught**: What specific issue the reviewer identified in the code
- **root_cause**: Why the author made this mistake (e.g., unfamiliar with API, forgot edge case, copy-paste error, missing context about system behavior)
- **prevention_principle**: A general actionable rule to prevent this CLASS of mistake in the future

IMPORTANT:
- Focus on comments that reveal actual code quality issues, bugs, or anti-patterns
- Skip comments that are questions, clarifications, or positive feedback
- Skip comments about trivial formatting or naming unless they represent a recurring pattern
- A good prevention_principle is actionable and testable by reading a code diff
- If a comment is too vague or context-free to extract a meaningful lesson, skip it

For each lesson, include the mr_id, comment_id, reviewer username, and file_path (if available)."""

        comments_text = []
        for comment in comments:
            location = ""
            if comment.is_inline and comment.file_path:
                location = f" (inline: {comment.file_path}"
                if comment.line_number:
                    location += f":{comment.line_number}"
                location += ")"

            comments_text.append(f"""
---
**Comment ID:** {comment.id}
**Reviewer:** {comment.author}{location}
**Comment:**
{comment.body[:1500]}
""")

        diff_context = ""
        if diff_summary:
            diff_context = f"""

## MR Diff Context (truncated)
```
{diff_summary[:3000]}
```
"""

        user_prompt = f"""Extract lessons from the following reviewer comments on MR !{mr_id}:
{diff_context}
## Reviewer Comments
{"".join(comments_text)}

For each comment that reveals a meaningful code quality issue or mistake, provide a lesson with mr_id, comment_id, reviewer, file_path (if inline), what_was_caught, root_cause, and prevention_principle."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # --- Guideline Synthesis ---

    def _synthesize_and_format(
        self,
        lessons: List[ReviewLesson],
        trace,
        project_name: str,
        existing_guidelines: list[dict] | None = None,
    ) -> str | None:
        """Synthesize guidelines from lessons, consolidate, and format."""
        self.progress.start_status("Synthesizing guidelines...")
        try:
            guidelines_result = self._synthesize_guidelines(lessons, trace=trace)
        finally:
            self.progress.stop_status()

        self.progress.info(f"Synthesized {len(guidelines_result.guidelines)} guidelines.")

        if not guidelines_result.guidelines:
            self.progress.warning("No guidelines synthesized from review lessons.")
            self._end_trace(trace, 0, project_name, "no_guidelines")
            return self._format_empty_yaml()

        # Consolidate against existing guidelines
        if existing_guidelines:
            self.progress.start_status("Consolidating guidelines...")
            try:
                consolidated = self._consolidate_guidelines(
                    guidelines_result.guidelines,
                    trace=trace,
                    existing_guidelines=existing_guidelines,
                )
            finally:
                self.progress.stop_status()
        else:
            consolidated = ConsolidatedGuidelines(guidelines=guidelines_result.guidelines)

        self.progress.success(f"Final suggested guidelines: {len(consolidated.guidelines)}")
        self._end_trace(trace, len(consolidated.guidelines), project_name)

        return self._format_as_yaml(consolidated)

    def _synthesize_guidelines(
        self,
        lessons: List[ReviewLesson],
        trace=None,
    ) -> GuidelineGenerationResult:
        """Synthesize guidelines from review lessons."""
        messages = self._build_synthesis_messages(lessons)

        generation = None
        if trace:
            generation = trace.start_generation(
                name="synthesize_review_guidelines",
                input=messages,
            )

        response = self.llm.generate(messages, response_model=GuidelineGenerationResult)

        if generation:
            generation.update(
                model=response.model,
                output=response.result.model_dump_json(),
                usage_details={
                    "input": response.token_usage.prompt_tokens,
                    "output": response.token_usage.completion_tokens,
                }
            )
            generation.end()

        return response.result

    def _build_synthesis_messages(self, lessons: List[ReviewLesson]) -> List[dict]:
        """Build LLM prompt for synthesizing guidelines from review lessons."""
        system_prompt = """You are synthesizing code review guidelines from lessons extracted from reviewer feedback on merged merge requests.

These lessons represent issues that reviewers repeatedly catch during code review. Guidelines derived from these are especially valuable because they address mistakes that keep slipping into merge requests.

Group lessons with similar root causes or prevention principles. For each group, write one guideline.

WHAT MAKES A GOOD GUIDELINE:
- Specific enough to be actionable: "Validate external API response payloads contain expected fields before accessing" NOT "Validate inputs"
- General enough to apply broadly: "Wrap external HTTP calls in timeout + retry" NOT "Add timeout to PaymentService.charge()"
- Testable by a code reviewer reading a diff
- Focused on prevention, not detection

Prefer guidelines that reference a specific category of mistake and can be verified by reading a code diff.
Avoid guidelines so generic they could appear in any "coding best practices" blog post unchanged.

GUIDELINE FORMAT:
- **label**: Short kebab-case identifier (e.g., 'validate-external-responses')
- **description**: Clear, actionable instruction (1-3 sentences)
- **reasoning**: Brief explanation referencing the reviewer feedback patterns that led to this guideline
- **confidence**: high/medium/low based on how many lessons support it
- **occurrence_count**: Number of lessons that contributed to this guideline

Return 5-15 guidelines depending on how many distinct patterns exist."""

        lessons_text = []
        for i, lesson in enumerate(lessons, 1):
            file_info = f" ({lesson.file_path})" if lesson.file_path else ""
            lessons_text.append(f"""
{i}. [MR !{lesson.mr_id}, reviewer: {lesson.reviewer}{file_info}]
   **What was caught:** {lesson.what_was_caught}
   **Root cause:** {lesson.root_cause}
   **Prevention principle:** {lesson.prevention_principle}""")

        user_prompt = f"""Synthesize guidelines from these {len(lessons)} lessons extracted from reviewer feedback on merged MRs:

{"".join(lessons_text)}

Group lessons with similar root causes, then produce high-quality, actionable guidelines."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _consolidate_guidelines(
        self,
        guidelines: List[GeneratedGuideline],
        trace=None,
        existing_guidelines: list[dict] | None = None,
    ) -> ConsolidatedGuidelines:
        """Deduplicate new guidelines against existing ones."""
        if not existing_guidelines:
            return ConsolidatedGuidelines(guidelines=guidelines)

        messages = self._build_consolidation_messages(guidelines, existing_guidelines)

        generation = None
        if trace:
            generation = trace.start_generation(
                name="consolidate_review_guidelines",
                input=messages,
            )

        response = self.llm.generate(messages, response_model=ConsolidatedGuidelines)

        if generation:
            generation.update(
                model=response.model,
                output=response.result.model_dump_json(),
                usage_details={
                    "input": response.token_usage.prompt_tokens,
                    "output": response.token_usage.completion_tokens,
                }
            )
            generation.end()

        return response.result

    def _build_consolidation_messages(
        self,
        guidelines: List[GeneratedGuideline],
        existing_guidelines: list[dict],
    ) -> List[dict]:
        """Build prompt for deduplicating against existing guidelines."""
        existing_text = []
        for i, g in enumerate(existing_guidelines, 1):
            existing_text.append(
                f"{i}. **{g.get('label', 'unknown')}**: {g.get('description', '')}"
            )

        candidates_text = []
        for i, g in enumerate(guidelines, 1):
            candidates_text.append(f"""
---
{i}. **{g.label}** (confidence: {g.confidence}, occurrences: {g.occurrence_count})
Description: {g.description}
Reasoning: {g.reasoning}
""")

        system_prompt = """You are consolidating code review guidelines incrementally.

You will be given:
1. **EXISTING GUIDELINES** - already in use. Do NOT repeat these.
2. **NEW CANDIDATES** - generated from reviewer feedback analysis.

Return only candidates that add genuine value not already covered by existing guidelines.

RULES:
- If a candidate covers the same principle as an existing one (even differently worded), discard it.
- If a candidate is a more specific version of an existing one, discard it.
- Merge similar candidates together.
- Remove generic advice.
- If nothing new, return an empty list.

Each kept guideline needs: label, description, reasoning, confidence, occurrence_count."""

        user_prompt = f"""## EXISTING GUIDELINES

{chr(10).join(existing_text)}

## NEW CANDIDATES

{"".join(candidates_text)}

Return only genuinely new guidelines not already covered above."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # --- Formatting ---

    def _format_as_yaml(self, consolidated: ConsolidatedGuidelines) -> str:
        """Format consolidated guidelines as YAML."""
        lines = [
            "# Suggested Code Review Guidelines",
            "# Generated by CodeYak from MR review comment analysis",
            "# Review and add to your .codeyak/project.yaml as needed",
            "",
            "guidelines:",
        ]

        for guideline in consolidated.guidelines:
            lines.append(f"  - label: {guideline.label}")
            lines.append(self._format_yaml_block("description", guideline.description, indent=4))
            lines.append(f"    # Confidence: {guideline.confidence}")
            reasoning_lines = guideline.reasoning.split('\n')
            lines.append(f"    # Reasoning: {reasoning_lines[0]}")
            for extra_line in reasoning_lines[1:]:
                lines.append(f"    #   {extra_line}")
            lines.append("")

        return "\n".join(lines)

    def _format_yaml_block(self, key: str, value: str, indent: int = 0) -> str:
        """Format a value as YAML block scalar if multiline, otherwise inline."""
        prefix = " " * indent
        if '\n' in value or len(value) > 80:
            block_lines = [f"{prefix}{key}: |"]
            for line in value.split('\n'):
                block_lines.append(f"{prefix}  {line}")
            return '\n'.join(block_lines)
        else:
            needs_quoting = (
                ':' in value or '#' in value
                or value[0:1] in ('{', '[', '>', '|', '*', '&', '!', '?', '-', "'", '"', '@', '`', '%')
            )
            if needs_quoting:
                escaped = value.replace('"', '\\"')
                return f'{prefix}{key}: "{escaped}"'
            return f"{prefix}{key}: {value}"

    def _format_empty_yaml(self) -> None:
        """Return None to indicate no guidelines were learned."""
        return None

    # --- Tracing ---

    def _start_trace(self, project_name: str, context: str):
        """Start Langfuse trace and return (trace, propagate_context)."""
        if not self.langfuse:
            return None, nullcontext()

        trace = self.langfuse.start_span(
            name="learn_from_reviews",
            input={"context": context},
            metadata={"project_name": project_name},
        )
        propagate_context = propagate_attributes(
            user_id=project_name
        )
        return trace, propagate_context

    def _end_trace(self, trace, guideline_count: int, project_name: str, tag: str | None = None):
        """End a Langfuse trace."""
        if trace:
            tags = [project_name]
            if tag:
                tags.append(tag)
            trace.update_trace(
                output={"guideline_count": guideline_count},
                tags=tags,
            )
            trace.end()

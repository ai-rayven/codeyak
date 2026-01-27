"""
Guidelines generator from git history analysis.

Analyzes historical commits to identify patterns, mistakes, and problematic
areas, then generates codeyak guidelines to help avoid future issues.
"""

from contextlib import nullcontext
from typing import List

from langfuse import propagate_attributes

from codeyak.protocols import LLMClient
from codeyak.infrastructure.vcs.local_git import LocalGitAdapter
from codeyak.domain.models import (
    HistoricalCommit,
    CommitBatch,
    GeneratedGuideline,
    GuidelineGenerationResult,
    ConsolidatedGuidelines,
)
from codeyak.domain.constants import CODE_FILE_EXTENSIONS


class GuidelinesGenerator:
    """
    Generates code review guidelines from git history analysis.

    Uses LLM to analyze commit patterns and identify recurring issues,
    then consolidates and formats them as codeyak guidelines.
    """

    BATCH_SIZE = 50
    MAX_DIFF_LINES = 100
    MAX_GUIDELINES_PER_BATCH = 10
    MAX_FINAL_GUIDELINES = 20

    def __init__(self, vcs: LocalGitAdapter, llm: LLMClient, langfuse=None):
        """
        Initialize the guidelines generator.

        Args:
            vcs: Local git adapter for accessing commit history
            llm: LLM client for analysis
            langfuse: Optional Langfuse client for tracing
        """
        self.vcs = vcs
        self.llm = llm
        self.langfuse = langfuse

    def generate_from_history(self, since_days: int = 365) -> str:
        """
        Generate guidelines from git history.

        Args:
            since_days: Number of days of history to analyze

        Returns:
            YAML string containing generated guidelines
        """
        project_name = self.vcs.get_project_name()

        # Start trace if Langfuse enabled
        trace, propagate_context = self._start_trace(project_name, since_days)

        with propagate_context:
            return self._generate_from_history_traced(
                since_days=since_days,
                project_name=project_name,
                trace=trace
            )

    def _start_trace(self, project_name: str, since_days: int):
        """Start Langfuse trace and return (trace, propagate_context)."""
        if not self.langfuse:
            return None, nullcontext()

        trace = self.langfuse.start_span(
            name="learn_guidelines",
            input={"since_days": since_days},
            metadata={"project_name": project_name},
        )
        context = propagate_attributes(
            user_id=self.vcs.get_username()
        )
        return trace, context

    def _generate_from_history_traced(
        self,
        since_days: int,
        project_name: str,
        trace
    ) -> str:
        """Internal method that runs within the trace context."""
        # 1. Fetch commits
        print(f"Fetching commits from the last {since_days} days...")
        commits = self.vcs.get_historical_commits(since_days=since_days)

        if not commits:
            print("No commits found in the specified time range.")
            if trace:
                trace.update_trace(output={"guideline_count": 0}, tags=[project_name, "no_commits"])
                trace.end()
            return self._format_empty_yaml()

        # 2. Filter to code files only
        commits = self._filter_code_commits(commits)
        print(f"Found {len(commits)} commits with code changes.")

        if not commits:
            print("No code-related commits found.")
            if trace:
                trace.update_trace(output={"guideline_count": 0}, tags=[project_name, "no_commits"])
                trace.end()
            return self._format_empty_yaml()

        # 3. Add diff summaries
        print("Fetching diff summaries...")
        commits = self._enrich_with_diffs(commits)

        # 4. Batch commits
        batches = self._batch_commits(commits)
        print(f"Created {len(batches)} batches for analysis.")

        # 5. Analyze each batch
        all_guidelines: List[GeneratedGuideline] = []
        for batch in batches:
            print(f"Analyzing batch {batch.batch_number}/{batch.total_batches}...")
            result = self._analyze_batch(batch, trace=trace)
            all_guidelines.extend(result.guidelines)
            print(f"  Found {len(result.guidelines)} potential guidelines.")

        if not all_guidelines:
            print("No patterns identified in commit history.")
            if trace:
                trace.update_trace(output={"guideline_count": 0}, tags=[project_name, "no_guidelines"])
                trace.end()
            return self._format_empty_yaml()

        # 6. Consolidate guidelines
        print(f"Consolidating {len(all_guidelines)} guidelines...")
        consolidated = self._consolidate_guidelines(all_guidelines, trace=trace)
        print(f"Final guidelines: {len(consolidated.guidelines)}")

        # End trace with output
        if trace:
            trace.update_trace(
                output={"guideline_count": len(consolidated.guidelines)},
                tags=[project_name]
            )
            trace.end()

        # 7. Format as YAML
        return self._format_as_yaml(consolidated)

    def _filter_code_commits(self, commits: List[HistoricalCommit]) -> List[HistoricalCommit]:
        """Filter commits to only those with code file changes."""
        filtered = []
        for commit in commits:
            code_files = [
                f for f in commit.files_changed
                if any(f.endswith(ext) for ext in CODE_FILE_EXTENSIONS)
            ]
            if code_files:
                filtered.append(HistoricalCommit(
                    sha=commit.sha,
                    message=commit.message,
                    author=commit.author,
                    date=commit.date,
                    files_changed=code_files,
                    diff_summary=commit.diff_summary,
                ))
        return filtered

    def _enrich_with_diffs(self, commits: List[HistoricalCommit]) -> List[HistoricalCommit]:
        """Add truncated diff summaries to commits."""
        enriched = []
        for commit in commits:
            diff_summary = self.vcs.get_commit_diff(
                commit.sha,
                max_lines=self.MAX_DIFF_LINES
            )
            enriched.append(HistoricalCommit(
                sha=commit.sha,
                message=commit.message,
                author=commit.author,
                date=commit.date,
                files_changed=commit.files_changed,
                diff_summary=diff_summary,
            ))
        return enriched

    def _batch_commits(self, commits: List[HistoricalCommit]) -> List[CommitBatch]:
        """Split commits into batches for LLM analysis."""
        batches = []
        total_batches = (len(commits) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        for i in range(0, len(commits), self.BATCH_SIZE):
            batch_commits = commits[i:i + self.BATCH_SIZE]
            batch_number = (i // self.BATCH_SIZE) + 1
            batches.append(CommitBatch(
                commits=batch_commits,
                batch_number=batch_number,
                total_batches=total_batches,
            ))

        return batches

    def _analyze_batch(self, batch: CommitBatch, trace=None) -> GuidelineGenerationResult:
        """Analyze a batch of commits with LLM."""
        messages = self._build_analysis_messages(batch)

        # Start generation if tracing
        generation = None
        if trace:
            generation = trace.start_generation(
                name=f"analyze_batch_{batch.batch_number}",
                input=messages,
            )

        response = self.llm.generate(messages, response_model=GuidelineGenerationResult)

        # End generation with output
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

    def _build_analysis_messages(self, batch: CommitBatch) -> List[dict]:
        """Construct LLM prompts for batch analysis."""
        system_prompt = """You are an expert code reviewer analyzing git commit history to identify general principles and patterns.

Your goal is to extract guidelines that capture broadly applicable principles - patterns that would help any similar project, not just this specific codebase.

## WHAT TO LOOK FOR

1. **General principles** - Extract the underlying pattern, not the specific implementation
2. **Recurring bug categories** - Classes of issues that appear across projects (e.g., input validation, async error handling)
3. **Architectural patterns** - Broadly applicable approaches for common problems

## GUIDELINE FORMAT

Each guideline needs:
- **label**: Short kebab-case identifier (e.g., 'responsive-layouts', 'validate-external-inputs')
- **description**: Clear, actionable instruction explaining the general principle

## DESCRIPTION QUALITY

Write descriptions that capture the GENERAL principle, not project-specific details:
- GOOD: "Use responsive layouts instead of fixed pixel dimensions"
- BAD: "Use flex-based layouts in web/PWA flows" (too specific to one context)

- GOOD: "Validate external inputs before processing"
- BAD: "Validate API responses from the PaymentService" (too specific)

- GOOD: "Handle async errors explicitly rather than silently failing"
- BAD: "Add try-catch in fetchUserData calls" (too specific)

## WHAT TO EXCLUDE

Skip guidelines about:
- Universal best practices any developer knows (e.g., "use version control")
- Generic style/formatting rules
- Standard tooling configurations
- Project-specific file names, APIs, or module references

## OUTPUT

Return 3-6 guidelines per batch. Focus on extracting general principles that would apply across similar projects."""

        # Format commits for analysis
        commits_text = []
        for commit in batch.commits:
            files_str = ", ".join(commit.files_changed[:10])
            if len(commit.files_changed) > 10:
                files_str += f" (+{len(commit.files_changed) - 10} more)"

            commit_text = f"""
### Commit {commit.sha[:8]}
**Author:** {commit.author}
**Date:** {commit.date}
**Message:** {commit.message}
**Files:** {files_str}

**Diff excerpt:**
```
{commit.diff_summary[:2000] if commit.diff_summary else "(no diff available)"}
```
"""
            commits_text.append(commit_text)

        user_prompt = f"""Analyze the following {len(batch.commits)} commits (batch {batch.batch_number}/{batch.total_batches}) and identify patterns that should become code review guidelines:

{"".join(commits_text)}

Based on these commits, what guidelines would help prevent similar issues in future code reviews?"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _consolidate_guidelines(
        self,
        all_guidelines: List[GeneratedGuideline],
        trace=None
    ) -> ConsolidatedGuidelines:
        """Deduplicate and consolidate guidelines across batches."""
        if len(all_guidelines) <= self.MAX_FINAL_GUIDELINES:
            return ConsolidatedGuidelines(guidelines=all_guidelines)

        messages = self._build_consolidation_messages(all_guidelines)

        # Start generation if tracing
        generation = None
        if trace:
            generation = trace.start_generation(
                name="consolidate_guidelines",
                input=messages,
            )

        response = self.llm.generate(messages, response_model=ConsolidatedGuidelines)

        # End generation with output
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
        guidelines: List[GeneratedGuideline]
    ) -> List[dict]:
        """Construct LLM prompts for guideline consolidation."""
        system_prompt = """You are consolidating code review guidelines into a final, high-quality set of general principles.

## YOUR TASK

1. **GENERALIZE** - Convert specific guidelines into broadly applicable principles
2. **MERGE** similar guidelines - combine those covering the same underlying principle
3. **REMOVE** generic guidelines that any developer would know
4. **ENHANCE** descriptions to be clear, actionable, and general
5. **LIMIT** to 10-15 of the most valuable guidelines

## GENERALIZATION STRATEGY

When a guideline is too specific, extract the underlying principle:
- "Use flex layouts in PWA flows" → "Use responsive layouts instead of fixed dimensions"
- "Validate PaymentService responses" → "Validate external API responses before processing"
- "Add retry logic to fetchUserData" → "Handle transient failures with appropriate retry strategies"

## MERGING STRATEGY

When merging similar guidelines:
- Extract the common underlying principle
- Use a general label that captures the pattern
- Combine descriptions to be broadly applicable
- Sum occurrence counts
- Keep the highest confidence level

## WHAT TO REMOVE

Delete any guideline about:
- Generic best practices any developer knows
- Universal style rules (naming, formatting)
- Standard tooling configurations
- Vague advice without specific guidance
- Specific file names, APIs, or module references that won't apply broadly

## OUTPUT FORMAT

Each final guideline needs only:
- **label**: Short kebab-case identifier (general, not project-specific)
- **description**: Clear, actionable principle (1-3 sentences, no project-specific references)
- **reasoning**: Brief explanation of why this matters
- **confidence**: high/medium/low
- **occurrence_count**: How many times the pattern was observed"""

        guidelines_text = []
        for i, g in enumerate(guidelines, 1):
            guidelines_text.append(f"""
---
{i}. **{g.label}** (confidence: {g.confidence}, occurrences: {g.occurrence_count})
Description: {g.description}
Reasoning: {g.reasoning}
""")

        user_prompt = f"""Consolidate these {len(guidelines)} guidelines into 10-15 final guidelines.

Focus on:
- Generalizing specific guidelines into broadly applicable principles
- Merging duplicates and similar guidelines
- Removing generic advice everyone knows
- Ensuring guidelines read like principles, not implementation details

Input guidelines:
{"".join(guidelines_text)}

Return only the highest-quality, most broadly applicable guidelines."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _format_as_yaml(self, consolidated: ConsolidatedGuidelines) -> str:
        """Format consolidated guidelines as codeyak YAML."""
        lines = [
            "# Generated Code Review Guidelines",
            "# Auto-generated by CodeYak from git history analysis",
            "# Review and customize before using",
            "",
            "guidelines:",
        ]

        for guideline in consolidated.guidelines:
            lines.append(f"  - label: {guideline.label}")
            lines.append(self._format_yaml_block("description", guideline.description, indent=4))

            # Add metadata as comments
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
        # Check if value needs block scalar (multiline or long)
        if '\n' in value or len(value) > 80:
            # Use block scalar style (|)
            block_lines = [f"{prefix}{key}: |"]
            for line in value.split('\n'):
                block_lines.append(f"{prefix}  {line}")
            return '\n'.join(block_lines)
        else:
            # Simple inline, but escape if needed
            if ':' in value or '#' in value or value.startswith('{') or value.startswith('['):
                # Quote the value
                escaped = value.replace('"', '\\"')
                return f'{prefix}{key}: "{escaped}"'
            return f"{prefix}{key}: {value}"

    def _format_empty_yaml(self) -> str:
        """Return empty YAML template."""
        return """# Generated Code Review Guidelines
# Auto-generated by CodeYak from git history analysis
# No patterns were identified - add guidelines manually

guidelines: []
"""

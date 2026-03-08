"""
Guidelines generator from git history analysis.

Analyzes historical commits to identify patterns, mistakes, and problematic
areas, then generates codeyak guidelines to help avoid future issues.
"""

from contextlib import nullcontext
from typing import List

from langfuse import propagate_attributes

from codeyak.protocols import LLMClient, ProgressReporter
from codeyak.infrastructure.vcs.local_git import LocalGitAdapter
from codeyak.domain.models import (
    HistoricalCommit,
    CommitBatch,
    CommitLesson,
    LessonExtractionResult,
    GeneratedGuideline,
    GuidelineGenerationResult,
    ConsolidatedGuidelines,
    CommitSignal,
    CommitClassificationBatch,
)
from codeyak.domain.constants import CODE_FILE_EXTENSIONS
from codeyak.ui import NullProgressReporter


# High-signal commit types that have learning potential
HIGH_SIGNAL_TYPES = {
    CommitSignal.BUG_FIX,
    CommitSignal.REVERT,
    CommitSignal.REFACTOR,
    CommitSignal.SECURITY_FIX,
}


class GuidelinesGenerator:
    """
    Generates code review guidelines from git history analysis.

    Uses LLM to analyze commit patterns and identify recurring issues,
    then consolidates and formats them as codeyak guidelines.
    """

    BATCH_SIZE = 10
    CLASSIFICATION_BATCH_SIZE = 25
    MAX_DIFF_LINES = 100
    MAX_GUIDELINES_PER_BATCH = 10
    MAX_FINAL_GUIDELINES = 20

    def __init__(
        self,
        vcs: LocalGitAdapter,
        llm: LLMClient,
        langfuse=None,
        progress: ProgressReporter | None = None
    ):
        """
        Initialize the guidelines generator.

        Args:
            vcs: Local git adapter for accessing commit history
            llm: LLM client for analysis
            langfuse: Optional Langfuse client for tracing
            progress: Optional progress reporter for UI feedback
        """
        self.vcs = vcs
        self.llm = llm
        self.langfuse = langfuse
        self.progress = progress or NullProgressReporter()

    def generate_from_history(
        self,
        since_days: int = 365,
        existing_guidelines: list[dict] | None = None,
    ) -> str:
        """
        Generate guidelines from git history.

        Args:
            since_days: Number of days of history to analyze
            existing_guidelines: Optional list of existing guideline dicts
                ({label, description}) to avoid duplicating

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
                trace=trace,
                existing_guidelines=existing_guidelines,
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
        trace,
        existing_guidelines: list[dict] | None = None,
    ) -> str:
        """Internal method that runs within the trace context."""
        # 1. Fetch commits
        self.progress.info(f"Fetching commits from the last {since_days} days...")
        commits = self.vcs.get_historical_commits(since_days=since_days)

        if not commits:
            self.progress.warning("No commits found in the specified time range.")
            if trace:
                trace.update_trace(output={"guideline_count": 0}, tags=[project_name, "no_commits"])
                trace.end()
            return self._format_empty_yaml()

        # 2. Filter to code files only
        commits = self._filter_code_commits(commits)
        self.progress.info(f"Found {len(commits)} commits with code changes.")

        if not commits:
            self.progress.warning("No code-related commits found.")
            if trace:
                trace.update_trace(output={"guideline_count": 0}, tags=[project_name, "no_commits"])
                trace.end()
            return self._format_empty_yaml()

        # 3. Add diff summaries with progress
        self.progress.info("Fetching diff summaries...")
        commits = self._enrich_with_diffs(commits)

        # 4. Classify commits and filter to high-signal
        commits = self._classify_commits(commits, trace=trace)
        commits = self._filter_high_signal_commits(commits)

        if not commits:
            self.progress.warning("No high-signal commits found after classification.")
            if trace:
                trace.update_trace(output={"guideline_count": 0}, tags=[project_name, "no_high_signal"])
                trace.end()
            return self._format_empty_yaml()

        # 5. Extract lessons (batched)
        batches = self._batch_commits(commits)
        self.progress.info(f"Created {len(batches)} batches for lesson extraction.")

        all_lessons: List[CommitLesson] = []

        task = self.progress.start_progress("Extracting lessons...", total=len(batches))
        try:
            for batch in batches:
                self.progress.update_progress(
                    task,
                    f"Extracting lessons from batch {batch.batch_number}/{batch.total_batches}"
                )
                result = self._extract_lessons(batch, trace=trace)
                all_lessons.extend(result.lessons)
                self.progress.advance_progress(task)
        finally:
            self.progress.stop_progress()

        self.progress.info(f"Extracted {len(all_lessons)} lessons.")

        if not all_lessons:
            self.progress.warning("No lessons extracted from commit history.")
            if trace:
                trace.update_trace(output={"guideline_count": 0}, tags=[project_name, "no_lessons"])
                trace.end()
            return self._format_empty_yaml()

        # 6. Synthesize guidelines from lessons
        self.progress.info("Synthesizing guidelines from lessons...")
        self.progress.start_status("Synthesizing guidelines...")
        try:
            guidelines_result = self._synthesize_guidelines(all_lessons, trace=trace)
        finally:
            self.progress.stop_status()

        self.progress.info(f"Synthesized {len(guidelines_result.guidelines)} guidelines.")

        if not guidelines_result.guidelines:
            self.progress.warning("No guidelines synthesized from lessons.")
            if trace:
                trace.update_trace(output={"guideline_count": 0}, tags=[project_name, "no_guidelines"])
                trace.end()
            return self._format_empty_yaml()

        # 7. Consolidate (only needed for incremental mode with existing guidelines)
        if existing_guidelines:
            self.progress.info("Consolidating with existing guidelines...")
            self.progress.start_status("Consolidating guidelines...")
            try:
                consolidated = self._consolidate_guidelines(
                    guidelines_result.guidelines, trace=trace, existing_guidelines=existing_guidelines
                )
            finally:
                self.progress.stop_status()
        else:
            consolidated = ConsolidatedGuidelines(guidelines=guidelines_result.guidelines)

        self.progress.success(f"Final guidelines: {len(consolidated.guidelines)}")

        # End trace with output
        if trace:
            trace.update_trace(
                output={"guideline_count": len(consolidated.guidelines)},
                tags=[project_name]
            )
            trace.end()

        # 8. Format as YAML
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

    def _classify_commits(
        self,
        commits: List[HistoricalCommit],
        trace=None
    ) -> List[HistoricalCommit]:
        """Classify commits by their learning potential using LLM."""
        if not commits:
            return commits

        self.progress.info(f"Classifying {len(commits)} commits...")
        classified = []
        total_batches = (len(commits) + self.CLASSIFICATION_BATCH_SIZE - 1) // self.CLASSIFICATION_BATCH_SIZE

        task = self.progress.start_progress("Classifying commits...", total=total_batches)
        try:
            for i in range(0, len(commits), self.CLASSIFICATION_BATCH_SIZE):
                batch = commits[i:i + self.CLASSIFICATION_BATCH_SIZE]
                batch_num = (i // self.CLASSIFICATION_BATCH_SIZE) + 1

                self.progress.update_progress(
                    task,
                    f"Classifying batch {batch_num}/{total_batches}"
                )

                messages = self._build_classification_messages(batch)

                # Start generation if tracing
                generation = None
                if trace:
                    generation = trace.start_generation(
                        name=f"classify_batch_{batch_num}",
                        input=messages,
                    )

                response = self.llm.generate(messages, response_model=CommitClassificationBatch)

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

                # Map classifications back to commits
                classifications_by_sha = {
                    c.sha: c for c in response.result.classifications
                }

                for commit in batch:
                    sha_prefix = commit.sha[:8]
                    classification = classifications_by_sha.get(sha_prefix)

                    if classification:
                        classified.append(HistoricalCommit(
                            sha=commit.sha,
                            message=commit.message,
                            author=commit.author,
                            date=commit.date,
                            files_changed=commit.files_changed,
                            diff_summary=commit.diff_summary,
                            signal=classification.signal,
                            signal_confidence=classification.confidence,
                            signal_reasoning=classification.reasoning,
                        ))
                    else:
                        # If not classified, default to CHORE (low signal)
                        classified.append(HistoricalCommit(
                            sha=commit.sha,
                            message=commit.message,
                            author=commit.author,
                            date=commit.date,
                            files_changed=commit.files_changed,
                            diff_summary=commit.diff_summary,
                            signal=CommitSignal.CHORE,
                            signal_confidence="low",
                            signal_reasoning="Not classified by LLM",
                        ))

                self.progress.advance_progress(task)
        finally:
            self.progress.stop_progress()

        return classified

    def _build_classification_messages(self, commits: List[HistoricalCommit]) -> List[dict]:
        """Construct LLM prompts for commit classification."""
        system_prompt = """You are an expert at classifying git commits by their learning potential for code review guidelines.

## CLASSIFICATION CATEGORIES

**High-signal (valuable for learning):**
- `bug_fix` - Fixes a bug, reveals what went wrong
- `revert` - Reverts a change, indicates something was problematic
- `refactor` - Restructures code without changing behavior, shows improvement patterns
- `security_fix` - Addresses security vulnerabilities, critical learning opportunity

**Low-signal (less valuable for learning):**
- `feature` - New functionality, doesn't reveal mistakes
- `documentation` - Doc changes don't teach code patterns
- `chore` - Dependency updates, CI, config changes
- `merge` - Just integration points
- `style` - Formatting, whitespace, naming only

## CLASSIFICATION STRATEGY

1. **Look at commit message keywords:**
   - "fix", "bug", "issue", "error", "crash" → likely `bug_fix`
   - "revert" → `revert`
   - "refactor", "restructure", "reorganize", "cleanup" → `refactor`
   - "security", "vulnerability", "CVE", "XSS", "injection" → `security_fix`
   - "feat", "add", "implement", "new" → `feature`
   - "docs", "readme", "comment" → `documentation`
   - "chore", "deps", "ci", "build", "config" → `chore`
   - "merge" → `merge`
   - "style", "format", "lint" → `style`

2. **Examine the diff for patterns:**
   - Small, targeted changes often indicate bug fixes
   - Test additions with fixes suggest bug fixes
   - Pure whitespace/formatting → style
   - Large structural changes with same logic → refactor

3. **When uncertain, default to low-signal** (feature, chore, or style)

## OUTPUT

For each commit, provide:
- sha: First 8 characters of the commit SHA
- signal: One of the classification categories
- confidence: "low", "medium", or "high"
- reasoning: Brief explanation (1 sentence)"""

        commits_text = []
        for commit in commits:
            files_str = ", ".join(commit.files_changed[:5])
            if len(commit.files_changed) > 5:
                files_str += f" (+{len(commit.files_changed) - 5} more)"

            # Truncate message and diff for classification
            message = commit.message[:500]
            diff_excerpt = commit.diff_summary[:1000] if commit.diff_summary else "(no diff)"

            commits_text.append(f"""
---
**SHA:** {commit.sha[:8]}
**Message:** {message}
**Files:** {files_str}
**Diff excerpt:**
```
{diff_excerpt}
```
""")

        user_prompt = f"""Classify the following {len(commits)} commits by their learning potential:

{"".join(commits_text)}

Return a classification for each commit."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _filter_high_signal_commits(
        self,
        commits: List[HistoricalCommit]
    ) -> List[HistoricalCommit]:
        """Filter commits to only those with high learning potential."""
        high_signal = [c for c in commits if c.signal in HIGH_SIGNAL_TYPES]

        # Log classification summary
        signal_counts = {}
        for commit in commits:
            signal = commit.signal.value if commit.signal else "unknown"
            signal_counts[signal] = signal_counts.get(signal, 0) + 1

        self.progress.info(f"Classification summary: {signal_counts}")
        self.progress.info(f"Filtered to {len(high_signal)} high-signal commits (from {len(commits)} total).")

        return high_signal

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

    def _extract_lessons(self, batch: CommitBatch, trace=None) -> LessonExtractionResult:
        """Extract per-commit lessons from a batch of commits."""
        messages = self._build_lesson_extraction_messages(batch)

        generation = None
        if trace:
            generation = trace.start_generation(
                name=f"extract_lessons_{batch.batch_number}",
                input=messages,
            )

        response = self.llm.generate(messages, response_model=LessonExtractionResult)

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

    def _build_lesson_extraction_messages(self, batch: CommitBatch) -> List[dict]:
        """Construct LLM prompts for lesson extraction from commits."""
        system_prompt = """You are analyzing git commits to understand what went wrong and why.

For each commit, extract:
- **what_went_wrong**: The specific problem this commit fixes or improves
- **root_cause**: Why this happened (missing validation, wrong assumption, race condition, unclear API contract, etc.)
- **prevention_principle**: The general rule that prevents this CLASS of issue

Be specific about root causes. "Developer error" is not a root cause.
A good prevention_principle is actionable: "Validate that API response contains expected fields before destructuring" not "Validate inputs."

If a commit doesn't clearly fix a problem or improve something (e.g., pure feature addition with no lesson), skip it."""

        commits_text = []
        for commit in batch.commits:
            files_str = ", ".join(commit.files_changed[:10])
            if len(commit.files_changed) > 10:
                files_str += f" (+{len(commit.files_changed) - 10} more)"

            commit_text = f"""
---
**SHA:** {commit.sha[:8]}
**Message:** {commit.message}
**Signal:** {commit.signal.value if commit.signal else "unknown"}
**Files:** {files_str}

**Diff:**
```
{commit.diff_summary[:2000] if commit.diff_summary else "(no diff available)"}
```
"""
            commits_text.append(commit_text)

        user_prompt = f"""Extract lessons from the following {len(batch.commits)} commits:

{"".join(commits_text)}

For each commit that reveals a mistake or improvement opportunity, provide a lesson with sha, what_went_wrong, root_cause, and prevention_principle."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _synthesize_guidelines(self, lessons: List[CommitLesson], trace=None) -> GuidelineGenerationResult:
        """Synthesize guidelines from extracted lessons."""
        messages = self._build_synthesis_messages(lessons)

        generation = None
        if trace:
            generation = trace.start_generation(
                name="synthesize_guidelines",
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

    def _build_synthesis_messages(self, lessons: List[CommitLesson]) -> List[dict]:
        """Construct LLM prompts for guideline synthesis from lessons."""
        system_prompt = """You are synthesizing code review guidelines from lessons extracted from git history.

Group lessons with similar root causes or prevention principles. For each group, write one guideline.

WHAT MAKES A GOOD GUIDELINE:
- Specific enough to be actionable: "Validate external API response payloads contain expected fields before accessing" NOT "Validate inputs"
- General enough to apply broadly: "Wrap external HTTP calls in timeout + retry" NOT "Add timeout to PaymentService.charge()"
- Testable by a code reviewer reading a diff
- Focused on prevention, not detection

EXAMPLES:
BAD: "Write better error handling"
GOOD: "Catch specific exception types rather than bare except clauses. Log the original exception with traceback before re-raising."

BAD: "Be careful with async code"
GOOD: "Always await or properly handle the return value of async functions. Unawaited coroutines silently discard errors."

Prefer guidelines that reference a specific category of mistake and can be verified by reading a code diff.
Avoid guidelines so generic they could appear in any "coding best practices" blog post unchanged.

GUIDELINE FORMAT:
- **label**: Short kebab-case identifier (e.g., 'validate-external-responses', 'handle-async-errors')
- **description**: Clear, actionable instruction (1-3 sentences)
- **reasoning**: Brief explanation referencing the lessons that led to this guideline
- **confidence**: high/medium/low based on how many lessons support it
- **occurrence_count**: Number of lessons that contributed to this guideline

You MUST return 8-12 guidelines. Every lesson set contains valuable patterns — synthesize them."""

        # Format lessons grouped by prevention_principle for easy scanning
        lessons_text = []
        for i, lesson in enumerate(lessons, 1):
            lessons_text.append(f"""
{i}. [{lesson.sha}] **What went wrong:** {lesson.what_went_wrong}
   **Root cause:** {lesson.root_cause}
   **Prevention principle:** {lesson.prevention_principle}""")

        user_prompt = f"""Synthesize guidelines from these {len(lessons)} lessons extracted from git history:

{"".join(lessons_text)}

Group lessons with similar root causes, then produce 8-12 high-quality, actionable guidelines."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _consolidate_guidelines(
        self,
        all_guidelines: List[GeneratedGuideline],
        trace=None,
        existing_guidelines: list[dict] | None = None,
    ) -> ConsolidatedGuidelines:
        """Deduplicate new guidelines against existing ones (incremental mode only)."""
        if not existing_guidelines:
            return ConsolidatedGuidelines(guidelines=all_guidelines)

        messages = self._build_consolidation_messages(all_guidelines, existing_guidelines)

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
        guidelines: List[GeneratedGuideline],
        existing_guidelines: list[dict],
    ) -> List[dict]:
        """Construct LLM prompts for incremental guideline consolidation."""
        guidelines_text = []
        for i, g in enumerate(guidelines, 1):
            guidelines_text.append(f"""
---
{i}. **{g.label}** (confidence: {g.confidence}, occurrences: {g.occurrence_count})
Description: {g.description}
Reasoning: {g.reasoning}
""")

        return self._build_incremental_consolidation_messages(
            guidelines_text, existing_guidelines
        )

    def _build_incremental_consolidation_messages(
        self,
        candidate_guidelines_text: list[str],
        existing_guidelines: list[dict],
    ) -> list[dict]:
        """Build prompts for incremental consolidation against existing guidelines."""
        existing_text = []
        for i, g in enumerate(existing_guidelines, 1):
            existing_text.append(
                f"{i}. **{g.get('label', 'unknown')}**: {g.get('description', '')}"
            )

        system_prompt = """You are an expert at consolidating code review guidelines incrementally.

You will be given two lists:
1. **EXISTING GUIDELINES** — already saved in the project. Do NOT repeat or rephrase these.
2. **NEW CANDIDATES** — freshly generated from recent commit analysis.

## YOUR TASK

Return **only** guidelines from the new candidates that add genuine value not already covered by the existing guidelines.

## RULES

- If a new candidate covers the same principle as an existing guideline (even with different wording), **discard it**.
- If a new candidate is a more specific version of an existing guideline, **discard it** — the existing general version is sufficient.
- If a new candidate covers a genuinely new area or pattern, **keep it** and generalize it.
- Merge similar new candidates together before returning.
- Remove generic advice any developer would know.
- If nothing new is worth adding, return an **empty list** of guidelines.

## QUALITY GATE — Remove any new candidate that:
- Could appear in a generic "coding best practices" blog post unchanged
- Doesn't reference a specific category of mistake
- A senior developer would consider obvious
- Cannot be verified by reading a code diff

## OUTPUT FORMAT

Each guideline needs:
- **label**: Short kebab-case identifier (general, not project-specific)
- **description**: Clear, actionable principle (1-3 sentences, no project-specific references)
- **reasoning**: Brief explanation of why this matters
- **confidence**: high/medium/low
- **occurrence_count**: How many times the pattern was observed"""

        user_prompt = f"""## EXISTING GUIDELINES (already covered — do not repeat)

{chr(10).join(existing_text)}

## NEW CANDIDATES

{"".join(candidate_guidelines_text)}

Return only genuinely new guidelines that are not already covered above. If nothing new is worth adding, return an empty list."""

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

    def format_guidelines_as_yaml_entries(self, guidelines: list[dict]) -> str:
        """Format guideline dicts as YAML entries for appending to an existing file.

        Args:
            guidelines: List of guideline dicts with at least 'label' and 'description' keys.

        Returns:
            YAML-formatted string of guideline entries (without the 'guidelines:' key).
        """
        lines = []
        for g in guidelines:
            lines.append(f"  - label: {g['label']}")
            lines.append(self._format_yaml_block("description", g["description"], indent=4))
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
            # Quote if value contains YAML-special characters or patterns
            needs_quoting = (
                ':' in value or '#' in value
                or value[0:1] in ('{', '[', '>', '|', '*', '&', '!', '?', '-', "'", '"', '@', '`', '%')
            )
            if needs_quoting:
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

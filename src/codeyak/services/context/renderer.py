"""
Context renderer for code review.

Assembles the final context from a ContextPlan, combining:
- Skeleton views of diff files with expanded regions
- Related symbols from other files
"""

from pathlib import Path

from .planner import ContextPlan, DiffFileContext, SymbolRequest
from .symbol_index import SymbolIndex, SymbolLocation
from .skeleton import SkeletonGenerator
from ...domain.models import FileDiff


class ContextRenderer:
    """
    Renders the final context for code review based on a ContextPlan.
    """

    def __init__(
        self,
        symbol_index: SymbolIndex,
        skeleton_generator: SkeletonGenerator,
        repo_path: Path,
    ) -> None:
        """
        Initialize the context renderer.
        
        Args:
            symbol_index: Index of symbols in the codebase
            skeleton_generator: Generator for skeleton views
            repo_path: Root path of the repository
        """
        self.index = symbol_index
        self.skeleton = skeleton_generator
        self.repo_path = repo_path

    def render(
        self,
        plan: ContextPlan,
        file_diffs: list[FileDiff],
    ) -> str:
        """
        Render the complete context for code review.
        
        Args:
            plan: The context plan from the LLM
            file_diffs: The file diffs being reviewed
        
        Returns:
            Formatted context string for the review LLM
        """
        sections: list[str] = []

        # Render each diff file with its context
        for diff in file_diffs:
            file_context = self._find_file_context(plan, diff.file_path)
            section = self._render_diff_file(diff, file_context)
            sections.append(section)

        # Render related symbols
        if plan.related_symbols:
            related_section = self._render_related_symbols(plan.related_symbols)
            if related_section:
                sections.append(related_section)

        return "\n\n".join(sections)

    def _find_file_context(
        self, plan: ContextPlan, file_path: str
    ) -> DiffFileContext | None:
        """Find the context configuration for a file."""
        for fc in plan.diff_files:
            if fc.file_path == file_path:
                return fc
        return None

    def _render_diff_file(
        self, diff: FileDiff, context: DiffFileContext | None
    ) -> str:
        """
        Render a single diff file with skeleton and expanded regions.
        
        Args:
            diff: The file diff
            context: Context configuration (or None for defaults)
        
        Returns:
            Formatted file context string
        """
        lines_before = context.lines_before if context else 10
        lines_after = context.lines_after if context else 10
        full_functions = context.full_functions if context else []

        parts: list[str] = []
        parts.append(f"## File: {diff.file_path} {'(new)' if diff.is_new_file else '(modified)'}")
        parts.append("")

        # For new files, show the full content
        if diff.is_new_file:
            if diff.full_content:
                parts.append("```")
                parts.append(self._add_line_numbers(diff.full_content))
                parts.append("```")
            return "\n".join(parts)

        # For modified files, show skeleton with expanded diff regions
        if diff.full_content:
            # Calculate which lines to expand based on diff hunks
            expand_ranges = self._calculate_expand_ranges(diff, lines_before, lines_after)
            
            # Generate skeleton with expansions
            skeleton_content = self.skeleton.generate_with_expansion(
                diff.file_path,
                diff.full_content,
                expand_ranges=expand_ranges,
                expand_functions=full_functions,
            )
            
            parts.append("### File Context (skeleton with expanded changes)")
            parts.append("")
            parts.append("```")
            parts.append(self._add_line_numbers(skeleton_content))
            parts.append("```")
            parts.append("")

        # Always include the raw diff for precise change tracking
        parts.append("### Changes (diff)")
        parts.append("")
        parts.append("```diff")
        parts.append(diff.format_with_line_numbers())
        parts.append("```")

        return "\n".join(parts)

    def _calculate_expand_ranges(
        self, diff: FileDiff, lines_before: int, lines_after: int
    ) -> list[tuple[int, int]]:
        """
        Calculate line ranges to expand based on diff hunks.
        
        Returns:
            List of (start_line, end_line) tuples (1-indexed)
        """
        ranges: list[tuple[int, int]] = []
        
        for hunk in diff.hunks:
            # Find the range of changed lines in this hunk
            min_line = None
            max_line = None
            
            for line in hunk.lines:
                if line.line_number is not None:
                    if min_line is None or line.line_number < min_line:
                        min_line = line.line_number
                    if max_line is None or line.line_number > max_line:
                        max_line = line.line_number
            
            if min_line is not None and max_line is not None:
                # Expand range with before/after context
                start = max(1, min_line - lines_before)
                end = max_line + lines_after
                ranges.append((start, end))
        
        # Merge overlapping ranges
        return self._merge_ranges(ranges)

    def _merge_ranges(
        self, ranges: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        """Merge overlapping line ranges."""
        if not ranges:
            return []
        
        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        merged: list[tuple[int, int]] = [sorted_ranges[0]]
        
        for start, end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + 1:  # Overlapping or adjacent
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        
        return merged

    def _render_related_symbols(self, symbols: list[SymbolRequest]) -> str:
        """
        Render related symbols from other files.
        
        Args:
            symbols: List of symbol requests
        
        Returns:
            Formatted related symbols section
        """
        parts: list[str] = []
        parts.append("## Related Symbols")
        parts.append("")

        resolved_symbols: list[tuple[SymbolRequest, SymbolLocation]] = []
        
        for req in symbols:
            location = self.index.resolve(req.symbol_name, req.file_hint)
            if location:
                resolved_symbols.append((req, location))

        if not resolved_symbols:
            return ""

        # Group by file
        by_file: dict[str, list[tuple[SymbolRequest, SymbolLocation]]] = {}
        for req, loc in resolved_symbols:
            if loc.file_path not in by_file:
                by_file[loc.file_path] = []
            by_file[loc.file_path].append((req, loc))

        for file_path, symbol_list in by_file.items():
            parts.append(f"### From: {file_path}")
            parts.append("")

            # Read file content
            full_path = self.repo_path / file_path
            if not full_path.exists():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")
            except Exception:
                continue

            for req, loc in symbol_list:
                parts.append(f"#### {loc.kind.value}: {loc.name}")
                parts.append("")

                if req.full:
                    # Show full implementation
                    symbol_lines = lines[loc.start_line - 1:loc.end_line]
                    symbol_content = "\n".join(symbol_lines)
                else:
                    # Show skeleton only
                    symbol_lines = lines[loc.start_line - 1:loc.end_line]
                    symbol_content = "\n".join(symbol_lines)
                    symbol_content = self.skeleton.generate(file_path, symbol_content)

                parts.append("```")
                parts.append(self._add_line_numbers(symbol_content, loc.start_line))
                parts.append("```")
                parts.append("")

        return "\n".join(parts)

    def _add_line_numbers(self, content: str, start_line: int = 1) -> str:
        """Add line numbers to content."""
        lines = content.split("\n")
        max_num = start_line + len(lines) - 1
        width = len(str(max_num))
        
        numbered = []
        for i, line in enumerate(lines):
            line_num = start_line + i
            numbered.append(f"{str(line_num).rjust(width)} | {line}")
        
        return "\n".join(numbered)

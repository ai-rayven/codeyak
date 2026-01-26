"""
Unified diff parser for parsing git diff output.

Parses unified diff format into structured DiffHunk/DiffLine objects.
"""

import re
from typing import List, Optional

from ...domain.models import DiffHunk, DiffLine, DiffLineType


class UnifiedDiffParser:
    """Parses unified diff format into structured DiffHunk/DiffLine objects."""

    HUNK_HEADER_PATTERN = re.compile(
        r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$'
    )

    def parse(self, raw_diff: str) -> List[DiffHunk]:
        """Parse a unified diff string into a list of DiffHunk objects."""
        if not raw_diff:
            return []

        hunks = []
        lines = raw_diff.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]
            header_match = self._parse_hunk_header(line)

            if header_match:
                old_start, old_count, new_start, new_count, header = header_match
                i += 1

                # Collect lines until next hunk header or end
                hunk_lines = []
                while i < len(lines):
                    if self._parse_hunk_header(lines[i]):
                        break
                    hunk_lines.append(lines[i])
                    i += 1

                parsed_lines = self._parse_hunk_lines(hunk_lines, new_start)
                hunks.append(DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    header=header.strip() if header else None,
                    lines=parsed_lines
                ))
            else:
                i += 1

        return hunks

    def _parse_hunk_header(self, line: str) -> Optional[tuple]:
        """Extract old_start, old_count, new_start, new_count, header from @@ line."""
        match = self.HUNK_HEADER_PATTERN.match(line)
        if not match:
            return None

        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) else 1
        header = match.group(5)

        return old_start, old_count, new_start, new_count, header

    def _parse_hunk_lines(self, lines: List[str], new_start: int) -> List[DiffLine]:
        """Parse lines within a hunk, assigning line numbers."""
        parsed_lines = []
        new_line = new_start

        for line in lines:
            if not line:
                # Empty line at end of hunk
                continue

            prefix = line[0] if line else ' '
            content = line[1:] if len(line) > 1 else ''

            if prefix == '+':
                parsed_lines.append(DiffLine(
                    line_number=new_line,
                    type=DiffLineType.ADDITION,
                    content=content
                ))
                new_line += 1
            elif prefix == '-':
                parsed_lines.append(DiffLine(
                    line_number=None,
                    type=DiffLineType.DELETION,
                    content=content
                ))
            elif prefix == ' ' or prefix == '\\':
                # Context line or "\ No newline at end of file"
                if prefix == '\\':
                    continue  # Skip metadata lines
                parsed_lines.append(DiffLine(
                    line_number=new_line,
                    type=DiffLineType.CONTEXT,
                    content=content
                ))
                new_line += 1

        return parsed_lines

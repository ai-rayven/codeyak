from typing import List, Optional
from pydantic import BaseModel, Field
import re

# --- Inputs (What we give the Agent) ---

class Guideline(BaseModel):
    """
    A specific rule the agent must enforce.
    Examples:
    - "No print() statements in production code."
    - "All SQL queries must use parameterized binding."
    """
    id: str = Field(..., description="Unique ID (e.g., 'SEC-001', 'STY-005')")
    description: str = Field(..., description="The clear instruction for the AI.")

class FileDiff(BaseModel):
    """
    The raw code changes to check.
    """
    file_path: str
    diff_content: str

    # Simple token count for grouping (no logic needed yet)
    tokens: int = 0

class FileGroup(BaseModel):
    """
    A group of file diffs batched together for processing.
    """
    files: List['FileDiff']
    group_id: int
    total_tokens: int

class MRComment(BaseModel):
    """
    Represents a comment from a merge request (both inline and general).
    """
    id: str = Field(..., description="Unique comment ID")
    body: str = Field(..., description="The text content of the comment")
    author: str = Field(..., description="Username of the comment author")
    created_at: str = Field(..., description="Timestamp of comment creation")

    # Optional fields for inline comments (None for general comments)
    file_path: Optional[str] = Field(None, description="File path for inline comments")
    line_number: Optional[int] = Field(None, description="Line number for inline comments")
    guideline_id: Optional[str] = Field(None, description="Parsed guideline ID if comment is a violation")

    is_inline: bool = Field(..., description="True if inline comment, False if general")

    @staticmethod
    def parse_guideline_id(body: str) -> Optional[str]:
        """
        Extract guideline_id from comment body.
        Matches patterns like:
        - **Violation of STYLE-02**:
        - **STYLE-02**:
        - Violation at `file.cs:138`\n\n**STYLE-02**:
        """
        # Pattern 1: **Violation of GUIDELINE-ID**:
        match = re.search(r'\*\*Violation of ([A-Z]+-\d+)\*\*:', body)
        if match:
            return match.group(1)

        # Pattern 2: **GUIDELINE-ID**: (for general comments)
        match = re.search(r'\*\*([A-Z]+-\d+)\*\*:', body)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def parse_file_and_line(body: str) -> tuple[Optional[str], Optional[int]]:
        """
        Extract file_path and line_number from general comment body.
        Matches pattern: **Violation at `file_path:line_number`**
        Returns: (file_path, line_number) or (None, None)
        """
        match = re.search(r'\*\*Violation at `([^`]+):(\d+)`\*\*', body)
        if match:
            file_path = match.group(1)
            line_number = int(match.group(2))
            return file_path, line_number
        return None, None

    def overlaps_with_violation(self, violation: 'GuidelineViolation') -> bool:
        """
        Check if this comment overlaps with a violation.
        Requires:
        - Same file path
        - Same guideline_id (if available)
        - Within line tolerance (10 lines)
        """
        # Must have file_path and line_number to overlap
        if not self.file_path or self.line_number is None:
            return False

        # File path must match
        if self.file_path != violation.file_path:
            return False

        # Guideline ID must match (if we have it)
        if self.guideline_id and self.guideline_id != violation.guideline_id:
            return False

        # Line number must be within tolerance
        line_tolerance = 10
        return abs(self.line_number - violation.line_number) <= line_tolerance

# --- Outputs (What the Agent returns) ---

class GuidelineViolation(BaseModel):
    """
    A specific instance where code failed a Guideline.
    """
    file_path: str
    line_number: int
    guideline_id: str = Field(..., description="MUST match the ID of the provided Guideline.")
    reasoning: str = Field(..., description="Brief explanation of why this code violates the rule.")

    def to_comment(self) -> str:
        """Formats the output for GitLab inline comments"""
        return f"**Violation of {self.guideline_id}**: {self.reasoning}"

    def to_general_comment(self) -> str:
        """Formats the output for general GitLab comments (with file and line reference)"""
        return (
            f"**Violation at `{self.file_path}:{self.line_number}`**\n\n"
            f"**{self.guideline_id}**: {self.reasoning}"
        )

class ReviewResult(BaseModel):
    """
    The list of all violations found in a batch of files.
    """
    violations: List[GuidelineViolation] = Field(default_factory=list)
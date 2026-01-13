from typing import List, Optional
from pydantic import BaseModel, Field

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

    is_inline: bool = Field(..., description="True if inline comment, False if general")

    def overlaps_with_violation(self, violation: 'GuidelineViolation') -> bool:
        """
        Check if this comment overlaps with a violation (within 3-line tolerance).
        """
        if not self.is_inline or not self.file_path:
            return False
        if self.file_path != violation.file_path:
            return False
        if self.line_number is None:
            return False

        line_tolerance = 3
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
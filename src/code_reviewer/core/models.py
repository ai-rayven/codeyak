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
        """Formats the output for GitLab"""
        return f"**Violation of {self.guideline_id}**: {self.reasoning}"

class ReviewResult(BaseModel):
    """
    The list of all violations found in a batch of files.
    """
    violations: List[GuidelineViolation] = Field(default_factory=list)
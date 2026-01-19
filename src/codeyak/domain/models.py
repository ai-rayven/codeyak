"""
Domain models for CodeYak.

Contains all core data structures used across the application.
"""

from typing import List, Optional, TypeVar, Generic
from pydantic import BaseModel, Field, field_validator
from pathlib import Path
import re

T = TypeVar("T", bound=BaseModel)


# --- LLM Domain Models ---

class TokenUsage(BaseModel):
    """
    Token usage information from an LLM API call.
    """
    prompt_tokens: int = Field(..., description="Number of tokens in the prompt")
    completion_tokens: int = Field(..., description="Number of tokens in the completion")
    total_tokens: int = Field(..., description="Total number of tokens used")


class LLMResponse(BaseModel, Generic[T]):
    """
    Response from an LLM including both the parsed result and metadata.

    This wraps the structured output from the LLM with additional information
    about the API call, including token usage, model, provider, and latency.
    """
    result: T = Field(..., description="The parsed structured output")
    token_usage: TokenUsage = Field(..., description="Token usage statistics")
    model: str = Field(..., description="Model name/deployment used")
    provider: str = Field(..., description="LLM provider (e.g., 'azure', 'openai')")
    latency_ms: float = Field(..., description="Time taken for the API call in milliseconds")


# --- Guidelines Domain Models ---

class Guideline(BaseModel):
    """
    A specific rule the agent must enforce.

    Examples:
    - "No print() statements in production code."
    - "All SQL queries must use parameterized binding."
    """
    id: str = Field(..., description="Unique ID (e.g., 'security/sql-injection', 'readability/function-length')")
    description: str = Field(..., description="The clear instruction for the AI.")

    @field_validator('id')
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        """Ensure ID follows convention: prefix/label (e.g., security/sql-injection)"""
        if not v or not isinstance(v, str):
            raise ValueError("ID must be a non-empty string")

        if not re.match(r'^[a-z0-9-]+/[a-z0-9-]+$', v):
            raise ValueError(
                f"ID '{v}' must follow format prefix/label (e.g., 'security/sql-injection', 'readability/function-length')"
            )

        return v

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Ensure description is meaningful"""
        if not v or not isinstance(v, str) or len(v.strip()) < 10:
            raise ValueError("Description must be at least 10 characters")
        return v.strip()


class GuidelineSetInfo(BaseModel):
    """
    Metadata about a parsed guideline file.

    Contains information about the source file, local guidelines defined in the file,
    and paths to included files (without merging them).
    """
    source_file: Path
    local_guidelines: List[Guideline]
    included_files: List[Path]

    @property
    def has_local_guidelines(self) -> bool:
        """Returns True if this file defines any local guidelines."""
        return len(self.local_guidelines) > 0


# --- VCS Domain Models ---

class FileDiff(BaseModel):
    """
    The raw code changes to check.
    """
    file_path: str
    diff_content: str
    full_content: Optional[str] = None  # Full file content for context

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
        - **Violation of security/sql-injection**:
        - **readability/function-length**:
        - Violation at `file.cs:138`\n\n**maintainability/single-responsibility**:
        """
        # Pattern 1: **Violation of GUIDELINE-ID**:
        match = re.search(r'\*\*Violation of ([a-z0-9-]+/[a-z0-9-]+)\*\*:', body)
        if match:
            return match.group(1)

        # Pattern 2: **GUIDELINE-ID**: (for general comments)
        match = re.search(r'\*\*([a-z0-9-]+/[a-z0-9-]+)\*\*:', body)
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


class MergeRequest(BaseModel):
    """
    Represents a merge request with its file diffs and comments.
    """
    id: str = Field(..., description="Merge request ID")
    file_diffs: List[FileDiff] = Field(default_factory=list, description="List of file diffs in the MR")
    comments: List[MRComment] = Field(default_factory=list, description="List of comments on the MR")

# --- Review Results Domain Models ---

class GuidelineViolation(BaseModel):
    """
    A specific instance where code failed a Guideline.
    """
    file_path: str
    line_number: int
    guideline_id: str = Field(..., description="MUST match the ID of the provided Guideline.")
    reasoning: str = Field(..., description="Brief explanation of why this code violates the rule.")
    confidence: str = Field(
        default="medium",
        description="Confidence level: 'low', 'medium', or 'high'. Use 'low' when context is unclear."
    )

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

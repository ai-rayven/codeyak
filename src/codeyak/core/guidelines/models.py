"""
Guidelines domain models.

Contains the core data structures for representing guidelines.
"""

from pydantic import BaseModel, Field, field_validator
import re
from pathlib import Path
from typing import List


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

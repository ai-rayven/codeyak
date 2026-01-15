"""
Guidelines domain models.

Contains the core data structures for representing guidelines.
"""

from pydantic import BaseModel, Field, field_validator
import re


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

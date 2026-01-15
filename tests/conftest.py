"""Shared pytest fixtures for all tests."""

import tempfile
from pathlib import Path

import pytest

from code_reviewer.core.guidelines.manager import GuidelinesManager
from code_reviewer.core.guidelines.parser import GuidelinesParser


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with .code_review/ subdirectory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        code_review_dir = tmpdir_path / ".code_review"
        code_review_dir.mkdir()
        yield tmpdir_path


@pytest.fixture
def parser():
    """Create a GuidelinesParser instance."""
    return GuidelinesParser()


@pytest.fixture
def manager():
    """Create a GuidelinesManager instance."""
    return GuidelinesManager()


@pytest.fixture
def data_dir():
    """Get the path to the test data directory."""
    return Path(__file__).parent / "guidelines" / "data"


@pytest.fixture
def temp_yaml_file(tmp_path):
    """Create a temporary YAML file with a valid name (no underscores)."""
    def _create_file(content: str, prefix: str = "test"):
        """
        Create a temp YAML file with valid naming.

        Args:
            content: YAML content to write
            prefix: Filename prefix (must be valid: lowercase, numbers, hyphens only)

        Returns:
            Path to the created file
        """
        import random
        import string

        # Generate a random suffix using only valid characters
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        filename = f"{prefix}-{suffix}.yaml"
        filepath = tmp_path / filename
        filepath.write_text(content)
        return filepath

    return _create_file

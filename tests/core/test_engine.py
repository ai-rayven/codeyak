"""Tests for the ReviewEngine."""

import pytest
from unittest.mock import Mock, MagicMock, call

from codeyak.core.engine import ReviewEngine
from codeyak.core.models import FileDiff, ReviewResult, GuidelineViolation, MRComment
from codeyak.core.guidelines.models import Guideline


@pytest.fixture
def mock_vcs_adapter():
    """Mock VCS adapter that returns fake diffs and comments."""
    mock = Mock()

    # Return 2 file diffs (simpler model - just file_path and diff_content)
    mock.get_diff.return_value = [
        FileDiff(
            file_path="file1.py",
            diff_content="@@ -1,3 +1,3 @@\n-old line\n+new line\n context",
            tokens=100
        ),
        FileDiff(
            file_path="file2.py",
            diff_content="@@ -1,3 +1,3 @@\n-old line\n+new line\n context",
            tokens=100
        )
    ]

    # No existing comments
    mock.get_comments.return_value = []

    # Mock post methods
    mock.post_comment.return_value = None
    mock.post_general_comment.return_value = None

    return mock


@pytest.fixture
def mock_llm_adapter():
    """Mock LLM adapter that returns no violations."""
    mock = Mock()

    # Return empty review result (no violations)
    mock.generate.return_value = ReviewResult(violations=[])

    return mock


@pytest.fixture
def mock_guidelines_manager_single():
    """Mock guidelines manager that returns a single guideline set."""
    mock = Mock()

    mock.load_guideline_sets.return_value = {
        "project/test.yaml": [
            Guideline(
                id="test/rule-1",
                description="Test rule 1"
            ),
            Guideline(
                id="test/rule-2",
                description="Test rule 2"
            )
        ]
    }

    return mock


@pytest.fixture
def mock_guidelines_manager_multiple():
    """Mock guidelines manager that returns multiple guideline sets."""
    mock = Mock()

    mock.load_guideline_sets.return_value = {
        "builtin/default.yaml→security.yaml": [
            Guideline(
                id="security/sql-injection",
                description="Prevent SQL injection"
            ),
            Guideline(
                id="security/xss-prevention",
                description="Prevent XSS"
            )
        ],
        "builtin/default.yaml→readability.yaml": [
            Guideline(
                id="readability/function-length",
                description="No long functions"
            )
        ],
        "builtin/default.yaml→maintainability.yaml": [
            Guideline(
                id="maintainability/single-responsibility",
                description="Follow SRP"
            ),
            Guideline(
                id="maintainability/cyclomatic-complexity",
                description="Reduce complexity"
            )
        ]
    }

    return mock


class TestEngineSingleGuidelineSet:
    """Tests for engine processing with a single guideline set."""

    def test_engine_processes_single_guideline_set(
        self,
        mock_vcs_adapter,
        mock_llm_adapter,
        mock_guidelines_manager_single,
        capsys
    ):
        """Test that engine correctly processes a single guideline set."""
        # Create engine with mocks
        engine = ReviewEngine(
            vcs=mock_vcs_adapter,
            llm=mock_llm_adapter,
            guidelines=mock_guidelines_manager_single
        )

        # Run the engine
        engine.run("123")

        # Verify VCS methods called
        mock_vcs_adapter.get_diff.assert_called_once_with("123")
        mock_vcs_adapter.get_comments.assert_called_once_with("123")

        # Verify guidelines loaded
        mock_guidelines_manager_single.load_guideline_sets.assert_called_once()

        # Verify LLM called once (one set, one file group)
        # Files are grouped together, so just 1 call expected
        assert mock_llm_adapter.generate.call_count == 1

        # Verify success comment posted (no violations)
        mock_vcs_adapter.post_general_comment.assert_called_once()
        args = mock_vcs_adapter.post_general_comment.call_args
        assert args[0][0] == "123"
        assert "success" in args[0][1].lower() or "no" in args[0][1].lower()

        # Verify output mentions the guideline set
        captured = capsys.readouterr()
        assert "project/test.yaml" in captured.out
        assert "2 guidelines" in captured.out


class TestEngineMultipleGuidelineSets:
    """Tests for engine processing with multiple guideline sets."""

    def test_engine_processes_multiple_guideline_sets(
        self,
        mock_vcs_adapter,
        mock_llm_adapter,
        mock_guidelines_manager_multiple,
        capsys
    ):
        """Test that engine correctly processes multiple guideline sets."""
        # Create engine with mocks
        engine = ReviewEngine(
            vcs=mock_vcs_adapter,
            llm=mock_llm_adapter,
            guidelines=mock_guidelines_manager_multiple
        )

        # Run the engine
        engine.run("456")

        # Verify VCS methods called
        mock_vcs_adapter.get_diff.assert_called_once_with("456")
        mock_vcs_adapter.get_comments.assert_called_once_with("456")

        # Verify guidelines loaded
        mock_guidelines_manager_multiple.load_guideline_sets.assert_called_once()

        # Verify LLM called 3 times (3 sets, 1 file group each)
        # Files are grouped together, so 1 call per guideline set
        assert mock_llm_adapter.generate.call_count == 3

        # Verify each set's guidelines were passed to LLM
        # We can check the messages passed to generate() contain the right guidelines
        calls = mock_llm_adapter.generate.call_args_list
        assert len(calls) == 3

        # Verify success comment posted (no violations across all sets)
        mock_vcs_adapter.post_general_comment.assert_called_once()
        args = mock_vcs_adapter.post_general_comment.call_args
        assert args[0][0] == "456"

        # Verify output mentions all guideline sets
        captured = capsys.readouterr()
        assert "security.yaml" in captured.out
        assert "readability.yaml" in captured.out
        assert "maintainability.yaml" in captured.out

    def test_engine_aggregates_violations_across_sets(
        self,
        mock_vcs_adapter,
        mock_llm_adapter,
        mock_guidelines_manager_multiple
    ):
        """Test that violations from different sets are aggregated correctly."""
        # Configure LLM to return violations on second call
        violation = GuidelineViolation(
            guideline_id="security/sql-injection",
            file_path="file1.py",
            line_number=5,
            reasoning="Potential SQL injection vulnerability"
        )

        # First two calls: no violations, third call: one violation
        mock_llm_adapter.generate.side_effect = [
            ReviewResult(violations=[]),
            ReviewResult(violations=[]),
            ReviewResult(violations=[violation])
        ]

        # Create engine
        engine = ReviewEngine(
            vcs=mock_vcs_adapter,
            llm=mock_llm_adapter,
            guidelines=mock_guidelines_manager_multiple
        )

        # Run the engine
        engine.run("789")

        # Verify 3 LLM calls made
        assert mock_llm_adapter.generate.call_count == 3

        # Verify violation posted to VCS
        assert mock_vcs_adapter.post_comment.call_count == 1
        comment_args = mock_vcs_adapter.post_comment.call_args[0]
        assert comment_args[0] == "789"
        # Second arg is the violation object itself
        assert isinstance(comment_args[1], GuidelineViolation)
        assert comment_args[1].guideline_id == "security/sql-injection"

        # Verify NO success comment (violations found)
        mock_vcs_adapter.post_general_comment.assert_not_called()

    def test_engine_handles_empty_guideline_sets(
        self,
        mock_vcs_adapter,
        mock_llm_adapter
    ):
        """Test engine handles case with no guideline sets gracefully."""
        # Mock manager that returns empty dict
        mock_manager = Mock()
        mock_manager.load_guideline_sets.return_value = {}

        engine = ReviewEngine(
            vcs=mock_vcs_adapter,
            llm=mock_llm_adapter,
            guidelines=mock_manager
        )

        # This should likely raise an error, but let's verify current behavior
        # If implementation changes to validate, update this test
        engine.run("000")

        # LLM should not be called with no guideline sets
        mock_llm_adapter.generate.assert_not_called()

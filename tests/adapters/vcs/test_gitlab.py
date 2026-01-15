"""Tests for GitLab adapter."""

import pytest
from unittest.mock import Mock, MagicMock, patch
import base64
import gitlab

from codeyak.adapters.vcs.gitlab import GitLabAdapter
from codeyak.core.exceptions import VCSFetchCommentsError


@pytest.fixture
def mock_gitlab_client():
    """Mock GitLab client with project and MR."""
    mock = Mock()
    mock_project = Mock()
    mock.projects.get.return_value = mock_project
    return mock, mock_project


@pytest.fixture
def gitlab_adapter(mock_gitlab_client):
    """Create GitLabAdapter with mocked dependencies."""
    mock_client, mock_project = mock_gitlab_client

    with patch('codeyak.adapters.vcs.gitlab.gitlab.Gitlab') as mock_gitlab_class:
        mock_gitlab_class.return_value = mock_client
        adapter = GitLabAdapter(
            url="https://gitlab.com",
            token="fake-token",
            project_id="123"
        )
        adapter.project = mock_project
        return adapter, mock_project


class TestGetCodeyakFiles:
    """Tests for the get_codeyak_files method."""

    def test_get_codeyak_files_success(self, gitlab_adapter):
        """Test successfully fetching YAML files from .codeyak directory."""
        adapter, mock_project = gitlab_adapter

        # Mock MR
        mock_mr = Mock()
        mock_mr.source_branch = "feature-branch"
        adapter._mr_cache = {"123": mock_mr}

        # Mock repository_tree to return YAML files
        mock_project.repository_tree.return_value = [
            {"type": "blob", "name": "security.yaml"},
            {"type": "blob", "name": "style.yml"},
            {"type": "blob", "name": "README.md"},  # Should be ignored
            {"type": "tree", "name": "subdir"},     # Should be ignored
        ]

        # Mock file content
        def mock_file_get(file_path, ref):
            mock_file = Mock()
            if file_path == ".codeyak/security.yaml":
                content = "guidelines:\n  - label: test\n    description: Test guideline"
            else:  # style.yml
                content = "guidelines:\n  - label: style\n    description: Style guideline"

            # GitLab returns base64 encoded content
            mock_file.decode.return_value = content.encode('utf-8')
            return mock_file

        mock_project.files.get.side_effect = mock_file_get

        # Execute
        result = adapter.get_codeyak_files("123")

        # Assert
        assert len(result) == 2
        assert "security.yaml" in result
        assert "style.yml" in result
        assert "README.md" not in result
        assert "guidelines:" in result["security.yaml"]
        assert "Test guideline" in result["security.yaml"]

        # Verify API calls
        mock_project.repository_tree.assert_called_once_with(
            path='.codeyak',
            ref='feature-branch',
            get_all=True
        )
        assert mock_project.files.get.call_count == 2

    def test_get_codeyak_files_directory_not_found(self, gitlab_adapter):
        """Test handling when .codeyak directory doesn't exist."""
        adapter, mock_project = gitlab_adapter

        # Mock MR
        mock_mr = Mock()
        mock_mr.source_branch = "feature-branch"
        adapter._mr_cache = {"123": mock_mr}

        # Mock 404 error
        error = gitlab.exceptions.GitlabGetError()
        error.response_code = 404
        mock_project.repository_tree.side_effect = error

        # Execute
        result = adapter.get_codeyak_files("123")

        # Assert - should return empty dict, not raise
        assert result == {}

    def test_get_codeyak_files_empty_directory(self, gitlab_adapter):
        """Test handling when .codeyak directory exists but is empty."""
        adapter, mock_project = gitlab_adapter

        # Mock MR
        mock_mr = Mock()
        mock_mr.source_branch = "feature-branch"
        adapter._mr_cache = {"123": mock_mr}

        # Mock empty directory
        mock_project.repository_tree.return_value = []

        # Execute
        result = adapter.get_codeyak_files("123")

        # Assert
        assert result == {}

    def test_get_codeyak_files_only_yaml_files(self, gitlab_adapter):
        """Test that only .yaml and .yml files are processed."""
        adapter, mock_project = gitlab_adapter

        # Mock MR
        mock_mr = Mock()
        mock_mr.source_branch = "feature-branch"
        adapter._mr_cache = {"123": mock_mr}

        # Mock repository_tree with various file types
        mock_project.repository_tree.return_value = [
            {"type": "blob", "name": "config.yaml"},
            {"type": "blob", "name": "setup.yml"},
            {"type": "blob", "name": "README.md"},
            {"type": "blob", "name": "script.py"},
            {"type": "blob", "name": "data.json"},
            {"type": "tree", "name": "subdirectory"},
        ]

        # Mock file content
        def mock_file_get(file_path, ref):
            mock_file = Mock()
            mock_file.decode.return_value = b"content"
            return mock_file

        mock_project.files.get.side_effect = mock_file_get

        # Execute
        result = adapter.get_codeyak_files("123")

        # Assert - only YAML files should be fetched
        assert len(result) == 2
        assert "config.yaml" in result
        assert "setup.yml" in result
        assert "README.md" not in result
        assert "script.py" not in result

    def test_get_codeyak_files_gitlab_error(self, gitlab_adapter):
        """Test handling of non-404 GitLab errors."""
        adapter, mock_project = gitlab_adapter

        # Mock MR
        mock_mr = Mock()
        mock_mr.source_branch = "feature-branch"
        adapter._mr_cache = {"123": mock_mr}

        # Mock non-404 error
        error = gitlab.exceptions.GitlabGetError()
        error.response_code = 500
        mock_project.repository_tree.side_effect = error

        # Execute and assert
        with pytest.raises(VCSFetchCommentsError, match="Failed to fetch .codeyak files"):
            adapter.get_codeyak_files("123")

    def test_get_codeyak_files_unexpected_error(self, gitlab_adapter):
        """Test handling of unexpected errors."""
        adapter, mock_project = gitlab_adapter

        # Mock MR
        mock_mr = Mock()
        mock_mr.source_branch = "feature-branch"
        adapter._mr_cache = {"123": mock_mr}

        # Mock unexpected error
        mock_project.repository_tree.side_effect = Exception("Unexpected error")

        # Execute and assert
        with pytest.raises(VCSFetchCommentsError, match="Unexpected error fetching .codeyak files"):
            adapter.get_codeyak_files("123")

    def test_get_codeyak_files_caches_mr(self, gitlab_adapter):
        """Test that MR caching is used correctly."""
        adapter, mock_project = gitlab_adapter

        # Mock MR lookup
        mock_mr = Mock()
        mock_mr.source_branch = "feature-branch"
        mock_project.mergerequests.get.return_value = mock_mr

        # Mock empty directory
        mock_project.repository_tree.return_value = []

        # Execute twice with same MR ID
        adapter.get_codeyak_files("123")
        adapter.get_codeyak_files("123")

        # Assert - MR should only be fetched once (cached)
        mock_project.mergerequests.get.assert_called_once_with("123")

    def test_get_codeyak_files_uses_source_branch(self, gitlab_adapter):
        """Test that files are fetched from the correct source branch."""
        adapter, mock_project = gitlab_adapter

        # Mock MR with specific source branch
        mock_mr = Mock()
        mock_mr.source_branch = "my-feature-branch"
        adapter._mr_cache = {"123": mock_mr}

        # Mock empty directory
        mock_project.repository_tree.return_value = []

        # Execute
        adapter.get_codeyak_files("123")

        # Assert - should use the source branch from MR
        mock_project.repository_tree.assert_called_once_with(
            path='.codeyak',
            ref='my-feature-branch',
            get_all=True
        )

    def test_get_codeyak_files_multiple_files(self, gitlab_adapter):
        """Test that multiple files are returned correctly."""
        adapter, mock_project = gitlab_adapter

        # Mock MR
        mock_mr = Mock()
        mock_mr.source_branch = "feature-branch"
        adapter._mr_cache = {"123": mock_mr}

        # Mock repository_tree with multiple files
        mock_project.repository_tree.return_value = [
            {"type": "blob", "name": "z-config.yaml"},
            {"type": "blob", "name": "a-security.yaml"},
            {"type": "blob", "name": "m-style.yml"},
        ]

        # Mock file content
        def mock_file_get(file_path, ref):
            mock_file = Mock()
            mock_file.decode.return_value = b"content"
            return mock_file

        mock_project.files.get.side_effect = mock_file_get

        # Execute
        result = adapter.get_codeyak_files("123")

        # Assert - all files should be present
        assert len(result) == 3
        assert "z-config.yaml" in result
        assert "a-security.yaml" in result
        assert "m-style.yml" in result

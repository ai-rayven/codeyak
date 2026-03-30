"""Tests for GitLabAdapter.get_file_content, focusing on gzip-compressed responses."""
import gzip
from unittest.mock import MagicMock, patch

import pytest

from codeyak.infrastructure.vcs.gitlab import GitLabAdapter


def _make_adapter() -> GitLabAdapter:
    """Return a GitLabAdapter with all GitLab I/O mocked out."""
    with patch("codeyak.infrastructure.vcs.gitlab.gitlab.Gitlab") as mock_gl_cls:
        mock_project = MagicMock()
        mock_gl_cls.return_value.projects.get.return_value = mock_project
        adapter = GitLabAdapter(url="https://gitlab.example.com", token="tok", project_id="1")
    return adapter


def _stub_mr(adapter: GitLabAdapter, mr_id: str, source_branch: str) -> MagicMock:
    mr = MagicMock()
    mr.source_branch = source_branch
    adapter._mr_cache[mr_id] = mr
    return mr


# ---------------------------------------------------------------------------
# Regression test: plain UTF-8 file should decode normally
# ---------------------------------------------------------------------------

def test_get_file_content_plain_utf8():
    adapter = _make_adapter()
    _stub_mr(adapter, "42", "feature-branch")

    mock_file = MagicMock()
    mock_file.decode.return_value = b"hello world"
    adapter.project.files.get.return_value = mock_file

    result = adapter.get_file_content("42", "src/foo.py")

    assert result == "hello world"


# ---------------------------------------------------------------------------
# Regression test: gzip-compressed content previously raised UnicodeDecodeError
# ---------------------------------------------------------------------------

def test_get_file_content_gzip_compressed_raises_without_fix():
    """Demonstrate the original bug: raw gzip bytes can't be UTF-8 decoded."""
    compressed = gzip.compress(b"hello world")
    # The first two bytes of a gzip stream are always 0x1f 0x8b
    assert compressed[:2] == b"\x1f\x8b"

    with pytest.raises(UnicodeDecodeError):
        compressed.decode("utf-8")


def test_get_file_content_gzip_compressed_is_handled():
    """After the fix, gzip-compressed file content is transparently decompressed."""
    adapter = _make_adapter()
    _stub_mr(adapter, "42", "feature-branch")

    plain_text = "hello world\nline two\n"
    compressed = gzip.compress(plain_text.encode("utf-8"))

    mock_file = MagicMock()
    mock_file.decode.return_value = compressed
    adapter.project.files.get.return_value = mock_file

    result = adapter.get_file_content("42", "src/foo.py")

    assert result == plain_text


# ---------------------------------------------------------------------------
# Edge case: 404 still returns None
# ---------------------------------------------------------------------------

def test_get_file_content_returns_none_for_404():
    import gitlab as gitlab_module

    adapter = _make_adapter()
    _stub_mr(adapter, "42", "feature-branch")

    err = gitlab_module.exceptions.GitlabGetError("not found", response_code=404)
    adapter.project.files.get.side_effect = err

    result = adapter.get_file_content("42", "src/new_file.py")

    assert result is None

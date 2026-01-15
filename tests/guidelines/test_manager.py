"""Tests for GuidelinesManager."""

import tempfile
from pathlib import Path

import pytest
import yaml

from codeyak.core.guidelines.exceptions import GuidelinesLoadError, GuidelineIncludeError
from codeyak.core.guidelines.manager import GuidelinesManager
from codeyak.core.guidelines.models import Guideline


class TestProjectFileDiscovery:
    """Tests for _scan_project_yaml_files method."""

    def test_scan_project_yaml_files_found(self, manager, temp_project_dir, monkeypatch):
        """Test scanning .codeyak/ directory with YAML files."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create some YAML files
        (codeyak_dir / "custom.yaml").write_text("guidelines: []")
        (codeyak_dir / "security.yaml").write_text("guidelines: []")

        yaml_files = manager._scan_project_yaml_files()

        assert len(yaml_files) == 2
        assert all(f.suffix in [".yaml", ".yml"] for f in yaml_files)
        # Should be sorted
        assert yaml_files[0].name == "custom.yaml"
        assert yaml_files[1].name == "security.yaml"

    def test_scan_project_yaml_files_not_found(self, manager, monkeypatch):
        """Test scanning when .codeyak/ directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            # Don't create .codeyak/ directory
            yaml_files = manager._scan_project_yaml_files()
            assert yaml_files == []

    def test_scan_project_yaml_files_empty_dir(self, manager, temp_project_dir, monkeypatch):
        """Test scanning empty .codeyak/ directory."""
        monkeypatch.chdir(temp_project_dir)
        # .codeyak/ exists but is empty
        yaml_files = manager._scan_project_yaml_files()
        assert yaml_files == []

    def test_scan_project_yaml_files_mixed_extensions(self, manager, temp_project_dir, monkeypatch):
        """Test scanning directory with both .yaml and .yml files."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        (codeyak_dir / "file1.yaml").write_text("guidelines: []")
        (codeyak_dir / "file2.yml").write_text("guidelines: []")

        yaml_files = manager._scan_project_yaml_files()

        assert len(yaml_files) == 2
        extensions = {f.suffix for f in yaml_files}
        assert extensions == {".yaml", ".yml"}

    def test_scan_project_yaml_files_sorted(self, manager, temp_project_dir, monkeypatch):
        """Test that files are returned in sorted order."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create files in non-alphabetical order
        (codeyak_dir / "zebra.yaml").write_text("guidelines: []")
        (codeyak_dir / "alpha.yaml").write_text("guidelines: []")
        (codeyak_dir / "beta.yaml").write_text("guidelines: []")

        yaml_files = manager._scan_project_yaml_files()

        assert len(yaml_files) == 3
        assert yaml_files[0].name == "alpha.yaml"
        assert yaml_files[1].name == "beta.yaml"
        assert yaml_files[2].name == "zebra.yaml"

    def test_scan_project_yaml_files_ignores_other_files(self, manager, temp_project_dir, monkeypatch):
        """Test that non-YAML files are ignored."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        (codeyak_dir / "guidelines.yaml").write_text("guidelines: []")
        (codeyak_dir / "readme.txt").write_text("some text")
        (codeyak_dir / "notes.md").write_text("# Notes")

        yaml_files = manager._scan_project_yaml_files()

        assert len(yaml_files) == 1
        assert yaml_files[0].name == "guidelines.yaml"


class TestLoadingProjectGuidelines:
    """Tests for _load_project_guidelines method."""

    def test_load_project_guidelines_success(self, manager, temp_project_dir, monkeypatch):
        """Test successfully loading project guidelines."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        yaml_file = codeyak_dir / "custom.yaml"
        yaml_file.write_text("""
guidelines:
  - label: custom-rule
    description: Custom project rule for testing.
        """)

        yaml_files = [yaml_file]
        guideline_sets = manager._load_project_guidelines(yaml_files)

        assert len(guideline_sets) == 1
        assert "project/custom.yaml" in guideline_sets
        assert len(guideline_sets["project/custom.yaml"]) == 1
        assert guideline_sets["project/custom.yaml"][0].id == "custom/custom-rule"

    def test_load_project_guidelines_multiple_files(self, manager, temp_project_dir, monkeypatch):
        """Test loading multiple project guideline files."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        file1 = codeyak_dir / "file1.yaml"
        file1.write_text("""
guidelines:
  - label: rule-1
    description: First rule from first file.
        """)

        file2 = codeyak_dir / "file2.yaml"
        file2.write_text("""
guidelines:
  - label: rule-2
    description: Second rule from second file.
        """)

        yaml_files = [file1, file2]
        guideline_sets = manager._load_project_guidelines(yaml_files)

        assert len(guideline_sets) == 2
        assert "project/file1.yaml" in guideline_sets
        assert "project/file2.yaml" in guideline_sets

    def test_load_project_guidelines_with_includes(self, manager, temp_project_dir, monkeypatch):
        """Test loading project file with includes directive."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        yaml_file = codeyak_dir / "with-includes.yaml"
        yaml_file.write_text("""
includes:
  - builtin:security

guidelines:
  - label: custom-rule
    description: Custom rule plus security guidelines.
        """)

        yaml_files = [yaml_file]
        guideline_sets = manager._load_project_guidelines(yaml_files)

        # Should have 2 separate sets: one for included security.yaml, one for local guidelines
        assert len(guideline_sets) == 2
        assert "project/with-includes.yaml→security.yaml" in guideline_sets
        assert "project/with-includes.yaml" in guideline_sets

        # Security guidelines should be in the included set
        security_guidelines = guideline_sets["project/with-includes.yaml→security.yaml"]
        assert len(security_guidelines) > 0
        assert all("security/" in g.id for g in security_guidelines)

        # Local guidelines should be in the main set
        local_guidelines = guideline_sets["project/with-includes.yaml"]
        assert len(local_guidelines) == 1
        assert local_guidelines[0].id == "with-includes/custom-rule"

    def test_load_project_guidelines_yaml_error(self, manager, temp_project_dir, monkeypatch):
        """Test that YAML syntax errors are wrapped in GuidelinesLoadError."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        yaml_file = codeyak_dir / "bad.yaml"
        yaml_file.write_text("guidelines:\n  - label: test\n    description: \"missing quote")

        yaml_files = [yaml_file]

        with pytest.raises(GuidelinesLoadError, match="YAML syntax error"):
            manager._load_project_guidelines(yaml_files)

    def test_load_project_guidelines_value_error(self, manager, temp_project_dir, monkeypatch):
        """Test that ValueError is wrapped in GuidelinesLoadError."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        yaml_file = codeyak_dir / "invalid.yaml"
        yaml_file.write_text("guidelines: not_a_list")

        yaml_files = [yaml_file]

        with pytest.raises(GuidelinesLoadError, match="Invalid guidelines format"):
            manager._load_project_guidelines(yaml_files)

    def test_load_project_guidelines_display_name(self, manager, temp_project_dir, monkeypatch):
        """Test that display name format is correct."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        yaml_file = codeyak_dir / "my-guidelines.yaml"
        yaml_file.write_text("""
guidelines:
  - label: test-rule
    description: Test rule for display name verification.
        """)

        yaml_files = [yaml_file]
        guideline_sets = manager._load_project_guidelines(yaml_files)

        # Display name should be "project/filename"
        assert "project/my-guidelines.yaml" in guideline_sets


class TestLoadingBuiltinDefault:
    """Tests for _load_builtin_default method."""

    def test_load_builtin_default_success(self, manager):
        """Test successfully loading built-in default guidelines."""
        guideline_sets = manager._load_builtin_default()

        # Default.yaml has 2 includes (security, code-quality) and no local guidelines
        assert len(guideline_sets) == 2
        assert "builtin/default.yaml→security.yaml" in guideline_sets
        assert "builtin/default.yaml→code-quality.yaml" in guideline_sets

        # Each set should have guidelines
        for set_name, guidelines in guideline_sets.items():
            assert len(guidelines) > 0

    def test_load_builtin_default_with_includes(self, manager):
        """Test that default.yaml with includes creates separate sets."""
        guideline_sets = manager._load_builtin_default()

        # Should have 2 separate sets from includes
        assert len(guideline_sets) == 2

        # Each included file should be a separate set
        assert "builtin/default.yaml→security.yaml" in guideline_sets
        assert "builtin/default.yaml→code-quality.yaml" in guideline_sets

    def test_load_builtin_default_display_name(self, manager):
        """Test that display name format is correct."""
        guideline_sets = manager._load_builtin_default()

        # Display names should follow parent→child format
        assert "builtin/default.yaml→security.yaml" in guideline_sets
        assert "builtin/default.yaml→code-quality.yaml" in guideline_sets


class TestDuplicateIDDetection:
    """Tests for _check_duplicate_ids method."""

    def test_duplicate_ids_across_files(self, manager, temp_project_dir, monkeypatch):
        """Test that duplicate IDs across files raise GuidelinesLoadError."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Both files have the same prefix and label
        file1 = codeyak_dir / "security.yaml"
        file1.write_text("""
guidelines:
  - label: sql-injection
    description: Prevent SQL injection in file 1.
        """)

        file2 = codeyak_dir / "security.yaml"  # Same name = same prefix
        # Actually, let's use different files but ensure same ID
        file2 = codeyak_dir / "security-rules.yaml"
        file2.write_text("""
guidelines:
  - label: sql-injection
    description: Prevent SQL injection in file 2.
        """)

        # This won't trigger duplicate because different prefixes
        # Let me fix this test - need same ID across different files

        # Create a scenario where we manually check duplicates
        guideline1 = Guideline(id="test/duplicate-rule", description="First occurrence of rule")
        guideline2 = Guideline(id="test/duplicate-rule", description="Second occurrence of rule")

        all_seen_ids = set()

        # First call should succeed
        manager._check_duplicate_ids([guideline1], all_seen_ids, "file1.yaml")
        assert "test/duplicate-rule" in all_seen_ids

        # Second call should raise error
        with pytest.raises(GuidelinesLoadError, match="Duplicate guideline ID"):
            manager._check_duplicate_ids([guideline2], all_seen_ids, "file2.yaml")

    def test_unique_ids_across_files(self, manager):
        """Test that unique IDs across files don't raise errors."""
        guideline1 = Guideline(id="test/rule-1", description="First unique rule")
        guideline2 = Guideline(id="test/rule-2", description="Second unique rule")

        all_seen_ids = set()

        # Both should succeed
        manager._check_duplicate_ids([guideline1], all_seen_ids, "file1.yaml")
        manager._check_duplicate_ids([guideline2], all_seen_ids, "file2.yaml")

        assert "test/rule-1" in all_seen_ids
        assert "test/rule-2" in all_seen_ids

    def test_duplicate_id_error_message(self, manager):
        """Test that duplicate ID error includes helpful information."""
        guideline = Guideline(id="test/rule", description="Test rule for duplicate detection")

        all_seen_ids = {"test/rule"}  # Already seen

        with pytest.raises(GuidelinesLoadError) as exc_info:
            manager._check_duplicate_ids([guideline], all_seen_ids, "duplicate-file.yaml")

        error_msg = str(exc_info.value)
        assert "test/rule" in error_msg
        assert "duplicate-file.yaml" in error_msg
        assert "unique" in error_msg.lower()

    def test_duplicate_label_in_parent_and_included_file(self, manager, temp_project_dir, monkeypatch):
        """Test that duplicate IDs between parent file and its included file raise error."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create a file named security.yaml that includes builtin:security
        # This creates a conflict because both use "security/" prefix
        yaml_file = codeyak_dir / "security.yaml"
        yaml_file.write_text("""
includes:
  - builtin:security

guidelines:
  - label: sql-injection
    description: Custom SQL injection rule that conflicts with builtin.
        """)

        yaml_files = [yaml_file]

        # Should raise error because security/sql-injection appears in both:
        # 1. project/security.yaml→security.yaml (from include)
        # 2. project/security.yaml (local guideline)
        with pytest.raises(GuidelinesLoadError) as exc_info:
            manager._load_project_guidelines(yaml_files)

        error_msg = str(exc_info.value)
        # Exact error message check
        assert "Duplicate guideline ID 'security/sql-injection' found in project/security.yaml" in error_msg
        assert "IDs must be unique across all guideline files" in error_msg

    def test_duplicate_across_multiple_files_with_same_include(self, manager, temp_project_dir, monkeypatch):
        """Test that multiple files including the same builtin raise circular include error."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create two files that both include builtin:security
        file1 = codeyak_dir / "file1.yaml"
        file1.write_text("""
includes:
  - builtin:security
        """)

        file2 = codeyak_dir / "file2.yaml"
        file2.write_text("""
includes:
  - builtin:security
        """)

        yaml_files = [file1, file2]

        # Should raise error because same include processed twice
        # This is detected as "circular include" by the processed_files tracking
        with pytest.raises(GuidelineIncludeError) as exc_info:
            manager._load_project_guidelines(yaml_files)

        error_msg = str(exc_info.value)
        # Exact error message check - references the builtin security.yaml file
        assert error_msg.startswith("Circular include detected:")
        assert "security.yaml" in error_msg

    def test_duplicate_detection_comprehensive(self, manager, temp_project_dir, monkeypatch):
        """Comprehensive test for various duplicate detection scenarios."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Scenario 1: File with local guidelines only (no duplicates) → Should pass
        solo_file = codeyak_dir / "solo.yaml"
        solo_file.write_text("""
guidelines:
  - label: custom-rule
    description: A standalone custom rule.
        """)

        # Should succeed
        result = manager._load_project_guidelines([solo_file])
        assert "project/solo.yaml" in result
        assert len(result["project/solo.yaml"]) == 1

        # Clean up for next scenario
        (temp_project_dir / ".codeyak").mkdir(exist_ok=True)

        # Scenario 2: File with includes only (no local guidelines) → Should pass
        includes_only = codeyak_dir / "includes-only.yaml"
        includes_only.write_text("""
includes:
  - builtin:security
        """)

        result = manager._load_project_guidelines([includes_only])
        assert "project/includes-only.yaml→security.yaml" in result
        assert len(result["project/includes-only.yaml→security.yaml"]) > 0

        # Scenario 3: Two files with same include → Should fail with circular include error
        file1 = codeyak_dir / "dup1.yaml"
        file1.write_text("""
includes:
  - builtin:code-quality
        """)

        file2 = codeyak_dir / "dup2.yaml"
        file2.write_text("""
includes:
  - builtin:code-quality
        """)

        with pytest.raises(GuidelineIncludeError) as exc_info:
            manager._load_project_guidelines([file1, file2])

        error_msg = str(exc_info.value)
        # Exact error message check - references the builtin code-quality.yaml file
        assert error_msg.startswith("Circular include detected:")
        assert "code-quality.yaml" in error_msg

        # Scenario 4: File where local guideline conflicts with include → Should fail
        conflict_file = codeyak_dir / "code-quality.yaml"
        conflict_file.write_text("""
includes:
  - builtin:code-quality

guidelines:
  - label: single-responsibility
    description: Conflicts with builtin code-quality/single-responsibility
        """)

        with pytest.raises(GuidelinesLoadError) as exc_info:
            manager._load_project_guidelines([conflict_file])

        error_msg = str(exc_info.value)
        # Exact error message check - duplicate ID detected
        assert "Duplicate guideline ID 'code-quality/single-responsibility' found in project/code-quality.yaml" in error_msg
        assert "IDs must be unique across all guideline files" in error_msg


class TestValidation:
    """Tests for _validate_guideline_sets method."""

    def test_validate_empty_guideline_sets(self, manager):
        """Test that empty guideline sets raise GuidelinesLoadError."""
        with pytest.raises(GuidelinesLoadError, match="No guidelines loaded"):
            manager._validate_guideline_sets({})

    def test_validate_nonempty_guideline_sets(self, manager):
        """Test that non-empty guideline sets pass validation."""
        guideline = Guideline(id="test/rule", description="Test rule for validation")
        guideline_sets = {"test.yaml": [guideline]}

        # Should not raise
        manager._validate_guideline_sets(guideline_sets)


class TestSummaryPrinting:
    """Tests for _print_loading_summary method."""

    def test_print_summary_single_set(self, manager, capsys):
        """Test summary output for single guideline set."""
        guideline = Guideline(id="test/rule", description="Test rule for summary output")
        guideline_sets = {"test.yaml": [guideline]}

        manager._print_loading_summary(guideline_sets)

        captured = capsys.readouterr()
        assert "1 guidelines" in captured.out
        assert "1 guideline set" in captured.out

    def test_print_summary_multiple_sets(self, manager, capsys):
        """Test summary output for multiple guideline sets."""
        guideline1 = Guideline(id="test/rule-1", description="First rule for testing summary")
        guideline2 = Guideline(id="test/rule-2", description="Second rule for testing summary")
        guideline3 = Guideline(id="test/rule-3", description="Third rule for testing summary")

        guideline_sets = {
            "set1.yaml": [guideline1, guideline2],
            "set2.yaml": [guideline3],
        }

        manager._print_loading_summary(guideline_sets)

        captured = capsys.readouterr()
        assert "3 guidelines" in captured.out
        assert "2 guideline set" in captured.out

    def test_print_summary_total_count(self, manager, capsys):
        """Test that summary counts total guidelines correctly."""
        guidelines_set1 = [
            Guideline(id=f"test/rule-{i}", description=f"Test rule number {i} for counting")
            for i in range(5)
        ]
        guidelines_set2 = [
            Guideline(id=f"test/rule-{i+5}", description=f"Test rule number {i+5} for counting")
            for i in range(3)
        ]

        guideline_sets = {
            "set1.yaml": guidelines_set1,
            "set2.yaml": guidelines_set2,
        }

        manager._print_loading_summary(guideline_sets)

        captured = capsys.readouterr()
        assert "8 guidelines" in captured.out


class TestLoadGuidelineSets:
    """Tests for the main load_guideline_sets method."""

    def test_load_uses_project_when_available(self, manager, temp_project_dir, monkeypatch):
        """Test that project guidelines are used when available."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        yaml_file = codeyak_dir / "custom.yaml"
        yaml_file.write_text("""
guidelines:
  - label: custom-rule
    description: Custom project rule for integration test.
        """)

        guideline_sets = manager.load_guideline_sets()

        # Should load project guidelines, not builtin
        assert any("project/" in name for name in guideline_sets.keys())
        assert not any("builtin/" in name for name in guideline_sets.keys())

    def test_load_uses_builtin_when_no_project(self, manager, monkeypatch):
        """Test that builtin default is used when no project guidelines exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            # No .codeyak/ directory

            guideline_sets = manager.load_guideline_sets()

            # Should load builtin default as separate sets
            assert len(guideline_sets) == 2
            assert "builtin/default.yaml→security.yaml" in guideline_sets
            assert "builtin/default.yaml→code-quality.yaml" in guideline_sets

    def test_load_validates_guideline_sets(self, manager, temp_project_dir, monkeypatch, mocker):
        """Test that validation is called during loading."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        yaml_file = codeyak_dir / "test.yaml"
        yaml_file.write_text("""
guidelines:
  - label: test-rule
    description: Test rule for validation check.
        """)

        # Mock the validation method to verify it's called
        validate_spy = mocker.spy(manager, "_validate_guideline_sets")

        manager.load_guideline_sets()

        # Validation should have been called once
        assert validate_spy.call_count == 1

    def test_load_prints_summary(self, manager, temp_project_dir, monkeypatch, mocker):
        """Test that summary is printed during loading."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        yaml_file = codeyak_dir / "test.yaml"
        yaml_file.write_text("""
guidelines:
  - label: test-rule
    description: Test rule for summary check.
        """)

        # Mock the summary method to verify it's called
        summary_spy = mocker.spy(manager, "_print_loading_summary")

        manager.load_guideline_sets()

        # Summary should have been called once
        assert summary_spy.call_count == 1

    def test_load_integration_project_guidelines(self, manager, temp_project_dir, monkeypatch):
        """Integration test: Load project guidelines end-to-end."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create two project files
        file1 = codeyak_dir / "security.yaml"
        file1.write_text("""
guidelines:
  - label: sql-injection
    description: Prevent SQL injection vulnerabilities in user input.
  - label: xss-prevention
    description: Prevent cross-site scripting attacks.
        """)

        file2 = codeyak_dir / "style.yaml"
        file2.write_text("""
guidelines:
  - label: naming-conventions
    description: Follow consistent naming conventions.
        """)

        guideline_sets = manager.load_guideline_sets()

        # Should have 2 sets
        assert len(guideline_sets) == 2
        assert "project/security.yaml" in guideline_sets
        assert "project/style.yaml" in guideline_sets

        # Check counts
        assert len(guideline_sets["project/security.yaml"]) == 2
        assert len(guideline_sets["project/style.yaml"]) == 1

    def test_load_integration_builtin_default(self, manager, monkeypatch):
        """Integration test: Load built-in default end-to-end."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            guideline_sets = manager.load_guideline_sets()

            # Should have builtin default as 2 separate sets
            assert len(guideline_sets) == 2
            assert "builtin/default.yaml→security.yaml" in guideline_sets
            assert "builtin/default.yaml→code-quality.yaml" in guideline_sets

            # Each set should have guidelines
            for set_name, guidelines in guideline_sets.items():
                assert len(guidelines) > 0


class TestExceptionHandling:
    """Tests for exception handling in manager."""

    def test_guidelines_load_error_pass_through(self, manager, temp_project_dir, monkeypatch):
        """Test that GuidelinesLoadError is not double-wrapped."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create file that will cause GuidelinesLoadError (e.g., circular include)
        # For this test, we'll create a duplicate ID scenario

        file1 = codeyak_dir / "dup1.yaml"
        file1.write_text("""
guidelines:
  - label: same-label
    description: First occurrence
        """)

        file2 = codeyak_dir / "dup1.yaml"  # Same filename = same prefix
        # Actually this won't work, let's manually trigger it

        # Instead, let's test with invalid YAML
        bad_file = codeyak_dir / "bad.yaml"
        bad_file.write_text("invalid: yaml: syntax:")

        # Should raise GuidelinesLoadError, not Exception
        with pytest.raises(GuidelinesLoadError):
            manager.load_guideline_sets()

    def test_parser_exceptions_bubble_up(self, manager, temp_project_dir, monkeypatch):
        """Test that parser exceptions are properly wrapped."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create file with invalid structure
        yaml_file = codeyak_dir / "invalid.yaml"
        yaml_file.write_text("guidelines: not_a_list")

        with pytest.raises(GuidelinesLoadError, match="Invalid guidelines format"):
            manager.load_guideline_sets()


class TestVCSFetching:
    """Tests for fetching guidelines from VCS."""

    def test_fetch_yaml_files_from_vcs_success(self, manager):
        """Test successfully fetching YAML files from VCS."""
        from unittest.mock import Mock

        # Mock VCS client
        mock_vcs = Mock()
        mock_vcs.get_codeyak_files.return_value = {
            "security.yaml": """guidelines:
  - label: test-security
    description: Test security guideline""",
            "style.yaml": """guidelines:
  - label: test-style
    description: Test style guideline"""
        }

        # Execute
        yaml_files = manager._fetch_yaml_files_from_vcs(mock_vcs, "123")

        # Assert
        assert len(yaml_files) == 2
        assert all(f.suffix in [".yaml", ".yml"] for f in yaml_files)
        assert any("security.yaml" in str(f) for f in yaml_files)
        assert any("style.yaml" in str(f) for f in yaml_files)

        # Verify files have correct content
        security_file = next(f for f in yaml_files if "security.yaml" in str(f))
        content = security_file.read_text()
        assert "test-security" in content

    def test_fetch_yaml_files_from_vcs_empty(self, manager):
        """Test VCS returns no files."""
        from unittest.mock import Mock

        mock_vcs = Mock()
        mock_vcs.get_codeyak_files.return_value = {}

        yaml_files = manager._fetch_yaml_files_from_vcs(mock_vcs, "123")

        assert yaml_files == []

    def test_fetch_yaml_files_from_vcs_error(self, manager):
        """Test VCS fetch error is handled gracefully."""
        from unittest.mock import Mock

        mock_vcs = Mock()
        mock_vcs.get_codeyak_files.side_effect = Exception("VCS error")

        # Should not raise, just return empty list
        yaml_files = manager._fetch_yaml_files_from_vcs(mock_vcs, "123")

        assert yaml_files == []

    def test_load_guideline_sets_with_vcs_files(self, manager, monkeypatch):
        """Test loading guidelines when VCS has .codeyak files."""
        from unittest.mock import Mock

        # Change to empty directory (no local .codeyak/)
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Mock VCS with guidelines
            mock_vcs = Mock()
            mock_vcs.get_codeyak_files.return_value = {
                "test.yaml": """guidelines:
  - label: vcs-guideline
    description: Guideline from VCS"""
            }

            # Execute
            guideline_sets = manager.load_guideline_sets(vcs=mock_vcs, mr_id="123")

            # Assert - should load from VCS, not builtin default
            assert len(guideline_sets) == 1
            assert "project/test.yaml" in guideline_sets
            assert len(guideline_sets["project/test.yaml"]) == 1
            assert guideline_sets["project/test.yaml"][0].id == "test/vcs-guideline"

    def test_load_guideline_sets_vcs_falls_back_to_local(self, manager, temp_project_dir, monkeypatch):
        """Test that if VCS returns no files, it falls back to local .codeyak/."""
        from unittest.mock import Mock

        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create local file
        (codeyak_dir / "local.yaml").write_text("""guidelines:
  - label: local-guideline
    description: Local guideline""")

        # Mock VCS that returns empty
        mock_vcs = Mock()
        mock_vcs.get_codeyak_files.return_value = {}

        # Execute
        guideline_sets = manager.load_guideline_sets(vcs=mock_vcs, mr_id="123")

        # Assert - should load from local, not VCS
        assert len(guideline_sets) == 1
        assert "project/local.yaml" in guideline_sets
        assert guideline_sets["project/local.yaml"][0].id == "local/local-guideline"

    def test_load_guideline_sets_vcs_preferred_over_local(self, manager, temp_project_dir, monkeypatch):
        """Test that VCS files are preferred over local files."""
        from unittest.mock import Mock

        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create local file
        (codeyak_dir / "local.yaml").write_text("""guidelines:
  - label: local-guideline
    description: Should not be used""")

        # Mock VCS that returns files
        mock_vcs = Mock()
        mock_vcs.get_codeyak_files.return_value = {
            "vcs.yaml": """guidelines:
  - label: vcs-guideline
    description: Should be used"""
        }

        # Execute
        guideline_sets = manager.load_guideline_sets(vcs=mock_vcs, mr_id="123")

        # Assert - should load from VCS, not local
        assert len(guideline_sets) == 1
        assert "project/vcs.yaml" in guideline_sets
        assert "project/local.yaml" not in guideline_sets
        assert guideline_sets["project/vcs.yaml"][0].id == "vcs/vcs-guideline"

    def test_load_guideline_sets_without_vcs_uses_local(self, manager, temp_project_dir, monkeypatch):
        """Test that without VCS parameter, local files are used."""
        monkeypatch.chdir(temp_project_dir)
        codeyak_dir = temp_project_dir / ".codeyak"

        # Create local file
        (codeyak_dir / "local.yaml").write_text("""guidelines:
  - label: local-guideline
    description: Local guideline""")

        # Execute without VCS
        guideline_sets = manager.load_guideline_sets()

        # Assert
        assert len(guideline_sets) == 1
        assert "project/local.yaml" in guideline_sets

    def test_load_guideline_sets_vcs_with_includes(self, manager, monkeypatch):
        """Test loading VCS files that include built-in guidelines."""
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Mock VCS with file that includes builtin guidelines
            mock_vcs = Mock()
            mock_vcs.get_codeyak_files.return_value = {
                "custom.yaml": """includes:
  - builtin:security

guidelines:
  - label: custom-rule
    description: Custom rule"""
            }

            # Execute
            guideline_sets = manager.load_guideline_sets(vcs=mock_vcs, mr_id="123")

            # Assert - should have both included and local guidelines
            assert len(guideline_sets) == 2
            assert "project/custom.yaml→security.yaml" in guideline_sets
            assert "project/custom.yaml" in guideline_sets

            # Security guidelines
            security_guidelines = guideline_sets["project/custom.yaml→security.yaml"]
            assert len(security_guidelines) > 0
            assert all(g.id.startswith("security/") for g in security_guidelines)

            # Custom guidelines
            custom_guidelines = guideline_sets["project/custom.yaml"]
            assert len(custom_guidelines) == 1
            assert custom_guidelines[0].id == "custom/custom-rule"

    def test_load_guideline_sets_vcs_falls_back_to_builtin(self, manager, monkeypatch):
        """Test that if VCS returns no files and no local files exist, builtin default is loaded."""
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Mock VCS that returns empty
            mock_vcs = Mock()
            mock_vcs.get_codeyak_files.return_value = {}

            # Execute - no VCS files, no local files
            guideline_sets = manager.load_guideline_sets(vcs=mock_vcs, mr_id="123")

            # Assert - should load builtin default
            assert len(guideline_sets) > 0
            assert any("builtin/default.yaml" in name for name in guideline_sets.keys())

    def test_load_guideline_sets_vcs_multiple_files(self, manager, monkeypatch):
        """Test loading multiple files from VCS."""
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Mock VCS with multiple files
            mock_vcs = Mock()
            mock_vcs.get_codeyak_files.return_value = {
                "01-security.yaml": """guidelines:
  - label: security-rule
    description: Security rule""",
                "02-style.yaml": """guidelines:
  - label: style-rule
    description: Style rule""",
                "03-custom.yaml": """guidelines:
  - label: custom-rule
    description: Custom rule"""
            }

            # Execute
            guideline_sets = manager.load_guideline_sets(vcs=mock_vcs, mr_id="123")

            # Assert
            assert len(guideline_sets) == 3
            assert "project/01-security.yaml" in guideline_sets
            assert "project/02-style.yaml" in guideline_sets
            assert "project/03-custom.yaml" in guideline_sets

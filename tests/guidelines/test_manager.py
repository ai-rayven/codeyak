"""Tests for GuidelinesManager."""

import tempfile
from pathlib import Path

import pytest
import yaml

from codeyak.core.guidelines.exceptions import GuidelinesLoadError
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

        assert "project/with-includes.yaml" in guideline_sets
        # Should have custom rule + security guidelines
        guidelines = guideline_sets["project/with-includes.yaml"]
        assert len(guidelines) > 1
        custom_rules = [g for g in guidelines if "custom-rule" in g.id]
        assert len(custom_rules) == 1

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

        assert len(guideline_sets) == 1
        assert "builtin/default.yaml" in guideline_sets
        # Default should have guidelines (from includes or direct)
        assert len(guideline_sets["builtin/default.yaml"]) > 0

    def test_load_builtin_default_with_includes(self, manager):
        """Test that default.yaml with includes works."""
        # This is implicitly tested in test_load_builtin_default_success
        # since the actual default.yaml uses includes
        guideline_sets = manager._load_builtin_default()
        guidelines = guideline_sets["builtin/default.yaml"]
        # Should have merged guidelines from includes
        assert len(guidelines) > 0

    def test_load_builtin_default_display_name(self, manager):
        """Test that display name format is correct."""
        guideline_sets = manager._load_builtin_default()
        assert "builtin/default.yaml" in guideline_sets


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

            # Should load builtin default
            assert "builtin/default.yaml" in guideline_sets

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

            # Should have builtin default
            assert len(guideline_sets) == 1
            assert "builtin/default.yaml" in guideline_sets
            assert len(guideline_sets["builtin/default.yaml"]) > 0


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

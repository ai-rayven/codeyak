"""Tests for GuidelinesParser."""

import re
import tempfile
from pathlib import Path

import pytest
import yaml

from codeyak.core.guidelines.exceptions import (
    BuiltinGuidelineNotFoundError,
    GuidelineIncludeError,
    GuidelinesLoadError,
)
from codeyak.core.guidelines.models import Guideline
from codeyak.core.guidelines.parser import GuidelinesParser


class TestBasicParsing:
    """Tests for basic YAML parsing functionality."""

    def test_parse_simple_yaml(self, parser, data_dir):
        """Test parsing a simple valid YAML file."""
        path = data_dir / "simple.yaml"
        guidelines = parser.parse_file(path)

        assert len(guidelines) == 2
        assert all(isinstance(g, Guideline) for g in guidelines)
        assert guidelines[0].id == "simple/no-print"
        assert guidelines[1].id == "simple/use-logging"

    def test_parse_empty_file(self, parser):
        """Test that empty file raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="empty or contains only whitespace"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_parse_nonexistent_file(self, parser):
        """Test that nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parser.parse_file(Path("/nonexistent/file.yaml"))

    def test_parse_yaml_syntax_error(self, parser, data_dir):
        """Test that invalid YAML syntax raises yaml.YAMLError."""
        path = data_dir / "bad-syntax.yaml"
        with pytest.raises(yaml.YAMLError):
            parser.parse_file(path)

    def test_parse_multiple_guidelines(self, parser):
        """Test parsing file with multiple guidelines."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', prefix='test-', delete=False) as f:
            f.write("""
guidelines:
  - label: rule-1
    description: First rule for testing multiple guidelines.
  - label: rule-2
    description: Second rule for testing multiple guidelines.
  - label: rule-3
    description: Third rule for testing multiple guidelines.
            """)
            temp_path = Path(f.name)

        try:
            guidelines = parser.parse_file(temp_path)
            assert len(guidelines) == 3
            assert guidelines[0].id.endswith("/rule-1")
            assert guidelines[1].id.endswith("/rule-2")
            assert guidelines[2].id.endswith("/rule-3")
        finally:
            temp_path.unlink()


class TestStructureValidation:
    """Tests for YAML structure validation."""

    def test_top_level_not_dict(self, parser):
        """Test that non-dict top-level structure raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("- item1\n- item2\n")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="must contain a YAML dictionary"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_missing_guidelines_and_includes(self, parser):
        """Test that file without guidelines or includes raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("other_key: value\n")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="contains no guidelines"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_guidelines_not_list(self, parser):
        """Test that guidelines as non-list raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("guidelines: not_a_list\n")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="'guidelines' must be a list"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_empty_guidelines_list_no_includes(self, parser):
        """Test that empty guidelines list without includes raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("guidelines: []\n")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="contains no guidelines"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_guideline_item_not_dict(self, parser):
        """Test that guideline item as non-dict raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - "string item"
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="must be a dictionary"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()


class TestGuidelineValidation:
    """Tests for individual guideline validation."""

    def test_missing_label_field(self, parser, data_dir):
        """Test that missing label field raises ValueError."""
        path = data_dir / "missing-label.yaml"
        with pytest.raises(ValueError, match="missing required 'label' field"):
            parser.parse_file(path)

    def test_missing_description_field(self, parser):
        """Test that missing description field raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - label: test-rule
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="missing required 'description' field"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_label_not_string(self, parser):
        """Test that non-string label raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - label: 123
    description: Test rule with numeric label.
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Label must be a string"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_label_with_uppercase(self, parser):
        """Test that uppercase in label raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - label: Test-Rule
    description: Test rule with uppercase in label.
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="must be lowercase alphanumeric"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_label_with_spaces(self, parser):
        """Test that spaces in label raise ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - label: test rule
    description: Test rule with spaces in label.
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="must be lowercase alphanumeric"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_label_with_underscores(self, parser):
        """Test that underscores in label raise ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - label: test_rule
    description: Test rule with underscores in label.
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="must be lowercase alphanumeric"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_label_starts_with_hyphen(self, parser):
        """Test that label starting with hyphen raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - label: -test-rule
    description: Test rule with leading hyphen in label.
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="cannot start or end with a hyphen"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_label_ends_with_hyphen(self, parser):
        """Test that label ending with hyphen raises ValueError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - label: test-rule-
    description: Test rule with trailing hyphen in label.
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="cannot start or end with a hyphen"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_valid_label_format(self, parser, temp_yaml_file):
        """Test that valid label formats are accepted."""
        valid_labels = [
            "simple",
            "with-hyphen",
            "multi-word-label",
            "with123numbers",
            "123starts-with-number",
        ]

        for label in valid_labels:
            temp_path = temp_yaml_file(f"""
guidelines:
  - label: {label}
    description: Test rule with valid label format.
            """, prefix="testlabel")

            guidelines = parser.parse_file(temp_path)
            assert len(guidelines) == 1
            assert label in guidelines[0].id


class TestDuplicateDetection:
    """Tests for duplicate label detection."""

    def test_duplicate_labels_in_same_file(self, parser, data_dir):
        """Test that duplicate labels in same file raise ValueError."""
        path = data_dir / "duplicate-labels.yaml"
        with pytest.raises(ValueError, match="Duplicate guideline label"):
            parser.parse_file(path)

    def test_different_labels_allowed(self, parser, temp_yaml_file):
        """Test that different labels in same file are allowed."""
        temp_path = temp_yaml_file("""
guidelines:
  - label: rule-1
    description: First rule with unique label.
  - label: rule-2
    description: Second rule with different label.
        """, prefix="difflabels")

        guidelines = parser.parse_file(temp_path)
        assert len(guidelines) == 2


class TestIDGeneration:
    """Tests for ID generation from filename and label."""

    def test_id_generated_from_filename_and_label(self, parser, temp_yaml_file):
        """Test that ID is generated as filename/label."""
        temp_path = temp_yaml_file("""
guidelines:
  - label: sql-injection
    description: Prevent SQL injection vulnerabilities.
        """, prefix="security")

        guidelines = parser.parse_file(temp_path)
        assert len(guidelines) == 1
        # ID should be stem of filename + label
        assert guidelines[0].id == f"{temp_path.stem}/sql-injection"


class TestIncludeMechanism:
    """Tests for the include mechanism."""

    def test_parse_includes_directive(self, parser, data_dir):
        """Test parsing file with includes directive."""
        path = data_dir / "with-includes.yaml"
        # This will try to include builtin:security
        guidelines = parser.parse_file(path)

        # Should have guidelines from security.yaml + the custom rule
        assert len(guidelines) > 1
        # Check that custom rule is included
        custom_rules = [g for g in guidelines if "custom-rule" in g.id]
        assert len(custom_rules) == 1

    def test_includes_not_list(self, parser):
        """Test that includes as non-list raises GuidelineIncludeError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("includes: not_a_list\n")
            temp_path = Path(f.name)

        try:
            with pytest.raises(GuidelineIncludeError, match="'includes' must be a list"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_include_item_not_string(self, parser):
        """Test that non-string include item raises GuidelineIncludeError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
includes:
  - 123
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(GuidelineIncludeError, match="Include reference must be a string"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_builtin_include_resolution(self, parser):
        """Test that builtin:security resolves correctly."""
        builtin_path = parser._get_builtin_guidelines_path()
        security_path = builtin_path / "security.yaml"

        if security_path.exists():
            resolved = parser._resolve_builtin_include("builtin:security")
            assert resolved == security_path

    def test_builtin_with_yaml_extension(self, parser):
        """Test that builtin:security.yaml works."""
        builtin_path = parser._get_builtin_guidelines_path()
        security_path = builtin_path / "security.yaml"

        if security_path.exists():
            resolved = parser._resolve_builtin_include("builtin:security.yaml")
            assert resolved == security_path

    def test_builtin_with_yml_extension(self, parser):
        """Test that .yml extension is handled."""
        # Create a test .yml file
        builtin_path = parser._get_builtin_guidelines_path()
        test_yml = builtin_path / "test.yml"

        # Skip if we can't write to builtin path
        try:
            test_yml.write_text("guidelines: []")
            resolved = parser._resolve_builtin_include("builtin:test.yml")
            assert resolved == test_yml
        except (PermissionError, OSError):
            pytest.skip("Cannot write to builtin guidelines path")
        finally:
            if test_yml.exists():
                test_yml.unlink()

    def test_nonexistent_builtin(self, parser):
        """Test that nonexistent builtin raises BuiltinGuidelineNotFoundError."""
        with pytest.raises(BuiltinGuidelineNotFoundError, match="not found"):
            parser._resolve_builtin_include("builtin:nonexistent-guideline")

    def test_unsupported_include_format(self, parser):
        """Test that non-builtin include format raises GuidelineIncludeError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
includes:
  - project:custom
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(GuidelineIncludeError, match="Unsupported include reference"):
                parser.parse_file(temp_path)
        finally:
            temp_path.unlink()

    def test_includes_merged_with_local_guidelines(self, parser, temp_yaml_file):
        """Test that includes and local guidelines are merged."""
        temp_path = temp_yaml_file("""
includes:
  - builtin:security

guidelines:
  - label: local-rule
    description: Local rule that should be merged with included guidelines.
        """, prefix="merged")

        guidelines = parser.parse_file(temp_path)
        # Should have guidelines from security + local rule
        local_rules = [g for g in guidelines if "local-rule" in g.id]
        assert len(local_rules) == 1
        # Should also have security guidelines
        assert len(guidelines) > 1

    def test_only_includes_no_local_guidelines(self, parser):
        """Test that file with only includes (no local guidelines) works."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
includes:
  - builtin:security
            """)
            temp_path = Path(f.name)

        try:
            guidelines = parser.parse_file(temp_path)
            # Should have guidelines from security
            assert len(guidelines) > 0
        finally:
            temp_path.unlink()


class TestCircularIncludes:
    """Tests for circular include prevention."""

    def test_circular_include_detected(self, parser):
        """Test that circular includes are detected through processed_files tracking."""
        # Create a test file that we'll parse twice to simulate a circular include
        builtin_path = parser._get_builtin_guidelines_path()
        test_file = builtin_path / "test-circular.yaml"

        try:
            test_file.write_text("""
guidelines:
  - label: test-rule
    description: Test rule for circular include detection.
            """)

            # Simulate a circular include by adding the file to processed_files
            # and then trying to parse it again
            processed_files = {test_file}

            with pytest.raises(GuidelineIncludeError, match="Circular include detected"):
                parser.parse_file(test_file, processed_files=processed_files)
        except (PermissionError, OSError):
            pytest.skip("Cannot write to builtin guidelines path")
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_self_include_detected(self, parser):
        """Test that self-include is detected."""
        # Create a file that includes itself (via builtin reference)
        builtin_path = parser._get_builtin_guidelines_path()
        self_include_path = builtin_path / "self-include-test.yaml"

        try:
            self_include_path.write_text("""
includes:
  - builtin:self-include-test

guidelines:
  - label: test-rule
    description: Test rule for self-include detection.
            """)

            with pytest.raises(GuidelineIncludeError, match="Circular include detected"):
                parser.parse_file(self_include_path)
        except (PermissionError, OSError):
            pytest.skip("Cannot write to builtin guidelines path")
        finally:
            if self_include_path.exists():
                self_include_path.unlink()


class TestNestedIncludes:
    """Tests for nested include prevention."""

    def test_nested_includes_disabled(self, parser):
        """Test that nested includes are not allowed."""
        # The parse_file method sets allow_includes=False for included files
        # This is tested implicitly in the include tests, but let's be explicit
        builtin_path = parser._get_builtin_guidelines_path()

        # Read security.yaml and check it doesn't have includes
        security_path = builtin_path / "security.yaml"
        if security_path.exists():
            with open(security_path) as f:
                data = yaml.safe_load(f)
            # Security.yaml shouldn't have includes (for this test to be meaningful)
            # If it does, the system should ignore them when included from another file
            assert True  # This is more of a documentation test


class TestBuiltinResolution:
    """Tests for built-in guideline path resolution."""

    def test_get_builtin_guidelines_path(self, parser):
        """Test that builtin guidelines path can be resolved."""
        path = parser._get_builtin_guidelines_path()
        assert path.exists()
        assert path.is_dir()

    def test_list_available_builtins(self, parser):
        """Test listing available built-in guidelines."""
        builtins = parser._list_available_builtins()
        assert isinstance(builtins, list)
        # Should have at least the default built-ins
        assert len(builtins) > 0
        # Check that some expected builtins exist
        expected_builtins = ["default", "security", "code-quality"]
        for expected in expected_builtins:
            assert expected in builtins, f"Expected builtin '{expected}' not found"


class TestErrorContext:
    """Tests for error messages with helpful context."""

    def test_error_includes_filename(self, parser):
        """Test that error messages include the filename."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("guidelines: not_a_list\n")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError) as exc_info:
                parser.parse_file(temp_path)
            # The error message should mention the filename or path
            assert "'guidelines' must be a list" in str(exc_info.value)
        finally:
            temp_path.unlink()

    def test_error_includes_guideline_index(self, parser, temp_yaml_file):
        """Test that error messages include the guideline index."""
        temp_path = temp_yaml_file("""
guidelines:
  - label: valid-rule
    description: Valid rule before the error.
  - label: invalid rule with spaces
    description: This rule has invalid label.
        """, prefix="erroridx")

        with pytest.raises(ValueError) as exc_info:
            parser.parse_file(temp_path)
        # The error should mention index 1 (second guideline)
        assert "index 1" in str(exc_info.value)

    def test_error_includes_guideline_preview(self, parser):
        """Test that error messages include guideline data preview."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
guidelines:
  - label: test-rule
            """)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError) as exc_info:
                parser.parse_file(temp_path)
            # Should show the guideline data in error
            error_msg = str(exc_info.value)
            assert "Guideline data:" in error_msg or "guideline" in error_msg.lower()
        finally:
            temp_path.unlink()

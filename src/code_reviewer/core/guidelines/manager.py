"""
Guidelines management system.

Handles loading, parsing, and validating guideline sets from both
built-in and project-specific sources.
"""

from typing import List, Dict
from pathlib import Path
import yaml
from .models import Guideline
from .exceptions import GuidelinesLoadError
from .parser import GuidelinesParser


class GuidelinesManager:
    """
    Manages guideline loading from built-in and project-specific sources.

    Supports:
    - Built-in guidelines shipped with the package
    - Project-specific guidelines in .code_review/ directory
    - Include mechanism for referencing built-in guidelines
    """

    def __init__(self):
        """Initialize the guidelines manager with a parser instance."""
        self.parser = GuidelinesParser()

    def load_guideline_sets(self) -> Dict[str, List[Guideline]]:
        """
        Load guideline sets from built-in and project-specific sources.

        Loading strategy:
        1. If .code_review/ directory exists with YAML files:
           - Load all project-specific YAML files
           - Process any 'includes' directives in those files
        2. If .code_review/ directory doesn't exist or is empty:
           - Auto-load built-in 'default' guideline set

        Each guideline set (file) becomes a separate review pass.

        Returns:
            Dict[str, List[Guideline]]: Map of display name to list of guidelines
            Display names use format: "builtin/filename" or "project/filename"

        Raises:
            GuidelinesLoadError: If files are invalid or includes cannot be resolved
        """
        project_yaml_files = self._scan_project_yaml_files()

        if project_yaml_files:
            guideline_sets = self._load_project_guidelines(project_yaml_files)
        else:
            guideline_sets = self._load_builtin_default()

        self._validate_guideline_sets(guideline_sets)
        self._print_loading_summary(guideline_sets)

        return guideline_sets

    def _scan_project_yaml_files(self) -> List[Path]:
        """
        Scan for YAML files in the project's .code_review/ directory.

        Returns:
            List[Path]: Sorted list of YAML file paths, empty if none found
        """
        code_review_dir = Path.cwd() / ".code_review"

        if not code_review_dir.exists() or not code_review_dir.is_dir():
            return []

        yaml_files = sorted(
            list(code_review_dir.glob("*.yaml")) +
            list(code_review_dir.glob("*.yml"))
        )

        return yaml_files

    def _load_project_guidelines(self, yaml_files: List[Path]) -> Dict[str, List[Guideline]]:
        """
        Load guidelines from project-specific YAML files.

        Args:
            yaml_files: List of YAML file paths to load

        Returns:
            Dict mapping display names to guideline lists

        Raises:
            GuidelinesLoadError: If files are invalid or have duplicate IDs
        """
        code_review_dir = Path.cwd() / ".code_review"
        print(f"Loading project-specific guidelines from {code_review_dir}...")

        guideline_sets = {}
        all_seen_ids = set()

        for yaml_file in yaml_files:
            try:
                print(f"Loading {yaml_file.name}...")

                # Parse file (includes are processed automatically)
                file_guidelines = self.parser.parse_file(yaml_file)

                # Check for duplicate IDs across all files
                self._check_duplicate_ids(file_guidelines, all_seen_ids, yaml_file.name)

                # Store with descriptive name
                display_name = f"project/{yaml_file.name}"
                guideline_sets[display_name] = file_guidelines
                print(f"  ✅ Loaded {len(file_guidelines)} guidelines from {yaml_file.name}")

            except GuidelinesLoadError:
                # Re-raise our own exceptions without wrapping
                raise
            except yaml.YAMLError as e:
                raise GuidelinesLoadError(
                    f"YAML syntax error in {yaml_file.name}: {e}"
                ) from e
            except ValueError as e:
                raise GuidelinesLoadError(
                    f"Invalid guidelines format in {yaml_file.name}: {e}"
                ) from e

        return guideline_sets

    def _load_builtin_default(self) -> Dict[str, List[Guideline]]:
        """
        Load the built-in default guideline set.

        Returns:
            Dict with single entry containing default guidelines

        Raises:
            GuidelinesLoadError: If default guideline set not found
        """
        print("ℹ️  No project-specific guidelines found in .code_review/")
        print("Loading built-in 'default' guideline set...")

        try:
            builtin_path = self.parser._get_builtin_guidelines_path()
            default_yaml = builtin_path / "default.yaml"

            if not default_yaml.exists():
                # Try .yml extension
                default_yaml = builtin_path / "default.yml"

            if not default_yaml.exists():
                raise GuidelinesLoadError(
                    "Built-in 'default' guideline set not found. "
                    "Package may be incorrectly installed."
                )

            # Parse default guidelines (includes are now supported)
            file_guidelines = self.parser.parse_file(
                default_yaml,
                allow_includes=True
            )

            display_name = "builtin/default.yaml"
            print(f"  ✅ Loaded {len(file_guidelines)} guidelines from built-in default set")

            return {display_name: file_guidelines}

        except GuidelinesLoadError:
            # Re-raise our own exceptions without wrapping
            raise
        except yaml.YAMLError as e:
            raise GuidelinesLoadError(
                f"YAML syntax error in built-in default guidelines: {e}"
            ) from e
        except ValueError as e:
            raise GuidelinesLoadError(
                f"Invalid format in built-in default guidelines: {e}"
            ) from e

    def _check_duplicate_ids(
        self,
        guidelines: List[Guideline],
        all_seen_ids: set,
        filename: str
    ) -> None:
        """
        Check for duplicate guideline IDs and update the seen IDs set.

        Args:
            guidelines: List of guidelines to check
            all_seen_ids: Set of IDs seen so far (will be updated)
            filename: Name of the file being processed (for error messages)

        Raises:
            GuidelinesLoadError: If duplicate ID found
        """
        for guideline in guidelines:
            if guideline.id in all_seen_ids:
                raise GuidelinesLoadError(
                    f"Duplicate guideline ID '{guideline.id}' found in {filename}. "
                    "IDs must be unique across all guideline files."
                )
            all_seen_ids.add(guideline.id)

    def _validate_guideline_sets(self, guideline_sets: Dict[str, List[Guideline]]) -> None:
        """
        Validate that guideline sets are not empty.

        Args:
            guideline_sets: The loaded guideline sets

        Raises:
            GuidelinesLoadError: If no guidelines were loaded
        """
        if not guideline_sets:
            raise GuidelinesLoadError(
                "No guidelines loaded. This should not happen - please report this bug."
            )

    def _print_loading_summary(self, guideline_sets: Dict[str, List[Guideline]]) -> None:
        """
        Print a summary of loaded guidelines.

        Args:
            guideline_sets: The loaded guideline sets
        """
        total_guidelines = sum(len(guidelines) for guidelines in guideline_sets.values())
        total_sets = len(guideline_sets)
        print(f"✅ Total: {total_guidelines} guidelines across {total_sets} guideline set(s)")

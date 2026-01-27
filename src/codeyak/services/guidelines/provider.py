"""
Guidelines management system.

Handles loading, parsing, and validating guideline sets from both
built-in and project-specific sources.
"""

from typing import List, Dict
from pathlib import Path
import yaml
import tempfile
from codeyak.domain.models import Guideline
from codeyak.protocols import VCSClient
from codeyak.domain.exceptions import GuidelinesLoadError, GuidelineIncludeError
from .parser import GuidelinesParser


class GuidelinesProvider:
    """
    Manages guideline loading from built-in and project-specific sources.

    Supports:
    - Built-in guidelines shipped with the package
    - Project-specific guidelines in .codeyak/ directory
    - Include mechanism for referencing built-in guidelines
    """

    def __init__(self, vcs: VCSClient):
        """Initialize the guidelines provider with a parser instance."""
        self.parser = GuidelinesParser()
        self.vcs = vcs

    def load_guidelines_from_vcs(
        self,
        merge_request_id: str
    ) -> Dict[str, List[Guideline]]:
        """
        Load guideline sets from built-in and project-specific sources.

        Loading strategy:
        1. If vcs and mr_id provided, try to fetch .codeyak/ files from repository
        2. If no VCS files found, check local .codeyak/ directory
        3. If no project files found, auto-load built-in 'default' guideline set

        Each guideline set (file) becomes a separate review pass.

        Args:
            mr_id: merge request ID to fetch files from

        Returns:
            Dict[str, List[Guideline]]: Map of display name to list of guidelines
            Display names use format: "builtin/filename" or "project/filename"

        Raises:
            GuidelinesLoadError: If files are invalid or includes cannot be resolved
        """
        # Try to fetch from VCS first (if in CI/CD context)
        project_yaml_files = self._fetch_yaml_files_from_vcs(self.vcs, merge_request_id)

        # Fall back to local filesystem (for local development)
        if not project_yaml_files or len(project_yaml_files) == 0:
            project_yaml_files = self._scan_project_yaml_files()

        if project_yaml_files:
            guideline_sets = self._load_project_guidelines(project_yaml_files)
        else:
            guideline_sets = self._load_builtin_default()

        self._validate_guideline_sets(guideline_sets)

        return guideline_sets

    def _scan_project_yaml_files(self) -> List[Path]:
        """
        Scan for YAML files in the project's .codeyak/ directory.

        Returns:
            List[Path]: Sorted list of YAML file paths, empty if none found
        """
        codeyak_dir = Path.cwd() / ".codeyak"

        if not codeyak_dir.exists() or not codeyak_dir.is_dir():
            return []

        yaml_files = sorted(
            list(codeyak_dir.glob("*.yaml")) +
            list(codeyak_dir.glob("*.yml"))
        )

        return yaml_files

    def _fetch_yaml_files_from_vcs(self, vcs: VCSClient, mr_id: str) -> List[Path]:
        """
        Fetch YAML files from repository's .codeyak/ directory via VCS.

        Creates temporary files for each YAML file fetched from the repository.

        Args:
            vcs: VCS client to fetch files from
            mr_id: Merge request ID

        Returns:
            List[Path]: List of temporary file paths containing YAML content
        """
        # Fetch .codeyak files from repository
        yaml_files_content = vcs.get_codeyak_files(mr_id)

        if not yaml_files_content:
            return []

        # Create temporary directory for storing fetched files
        temp_dir = Path(tempfile.mkdtemp(prefix="codeyak_"))
        temp_files = []

        for filename, content in sorted(yaml_files_content.items()):
            temp_file = temp_dir / filename
            temp_file.write_text(content)
            temp_files.append(temp_file)

        return temp_files

    def _process_guideline_file_with_includes(
        self,
        yaml_file: Path,
        display_prefix: str,
        all_seen_ids: set,
        processed_files: set
    ) -> Dict[str, List[Guideline]]:
        """
        Process a guideline file and its includes as separate sets.

        Each included file becomes a separate guideline set. Local guidelines
        (if any) also become a separate set.

        Args:
            yaml_file: Path to YAML file to process
            display_prefix: Prefix for display names ("project" or "builtin")
            all_seen_ids: Set of already seen guideline IDs (for duplicate detection)
            processed_files: Set of already processed files (for circular detection)

        Returns:
            Dict mapping display names to guideline lists

        Raises:
            GuidelinesLoadError: If files are invalid or have duplicate IDs
            GuidelineIncludeError: If circular includes detected
        """
        guideline_sets = {}

        # Parse file with metadata (extracts includes without merging)
        file_info = self.parser.parse_file_with_metadata(
            yaml_file,
            processed_files=processed_files
        )

        # Process each include as a separate guideline set
        for include_path in file_info.included_files:
            if include_path in processed_files:
                raise GuidelineIncludeError(
                    f"Circular include detected: {include_path}"
                )

            # Parse included file separately (no nested includes)
            included_guidelines = self.parser.parse_file(
                include_path,
                allow_includes=False,
                processed_files=processed_files
            )

            # Create display name showing parent→child relationship
            display_name = f"{display_prefix}/{yaml_file.name}→{include_path.name}"

            # Check for duplicate IDs
            self._check_duplicate_ids(
                included_guidelines,
                all_seen_ids,
                display_name
            )

            # Store as separate set
            guideline_sets[display_name] = included_guidelines

        # Add local guidelines as separate set (if any)
        if file_info.has_local_guidelines:
            display_name = f"{display_prefix}/{yaml_file.name}"

            # Check for duplicate IDs
            self._check_duplicate_ids(
                file_info.local_guidelines,
                all_seen_ids,
                display_name
            )

            # Store as separate set
            guideline_sets[display_name] = file_info.local_guidelines

        return guideline_sets

    def _load_project_guidelines(self, yaml_files: List[Path]) -> Dict[str, List[Guideline]]:
        """
        Load guidelines from project-specific YAML files.

        Each included file becomes a separate guideline set with display name
        "project/{parent}→{included}". Local guidelines (if any) become a separate
        set with display name "project/{filename}".

        Args:
            yaml_files: List of YAML file paths to load

        Returns:
            Dict mapping display names to guideline lists

        Raises:
            GuidelinesLoadError: If files are invalid or have duplicate IDs
        """
        codeyak_dir = Path.cwd() / ".codeyak"

        guideline_sets = {}
        all_seen_ids = set()
        processed_files = set()

        for yaml_file in yaml_files:
            try:
                # Use extracted method with "project" prefix
                file_sets = self._process_guideline_file_with_includes(
                    yaml_file,
                    display_prefix="project",
                    all_seen_ids=all_seen_ids,
                    processed_files=processed_files
                )
                guideline_sets.update(file_sets)

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
            except GuidelineIncludeError as e:
                raise GuidelinesLoadError(
                    f"Include error in {yaml_file.name}: {e}"
                ) from e

        return guideline_sets

    def _load_builtin_default(self) -> Dict[str, List[Guideline]]:
        """
        Load the built-in default guideline set.

        Each included file becomes a separate guideline set with display name
        "builtin/default.yaml→{included}". Local guidelines (if any) become a separate
        set with display name "builtin/default.yaml".

        Returns:
            Dict mapping display names to guideline lists

        Raises:
            GuidelinesLoadError: If default guideline set not found
        """

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

            all_seen_ids = set()
            processed_files = set()

            # Use extracted method with "builtin" prefix
            guideline_sets = self._process_guideline_file_with_includes(
                default_yaml,
                display_prefix="builtin",
                all_seen_ids=all_seen_ids,
                processed_files=processed_files
            )

            return guideline_sets

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
        except GuidelineIncludeError as e:
            raise GuidelinesLoadError(
                f"Include error in built-in default guidelines: {e}"
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

    def load_guidelines_local(self) -> Dict[str, List[Guideline]]:
        """
        Load guideline sets from local filesystem only (no VCS fetch).

        Loading strategy:
        1. Check local .codeyak/ directory for YAML files
        2. If no project files found, auto-load built-in 'default' guideline set

        Each guideline set (file) becomes a separate review pass.

        Returns:
            Dict[str, List[Guideline]]: Map of display name to list of guidelines
            Display names use format: "builtin/filename" or "project/filename"

        Raises:
            GuidelinesLoadError: If files are invalid or includes cannot be resolved
        """
        # Only scan local filesystem
        project_yaml_files = self._scan_project_yaml_files()

        if project_yaml_files:
            guideline_sets = self._load_project_guidelines(project_yaml_files)
        else:
            guideline_sets = self._load_builtin_default()

        self._validate_guideline_sets(guideline_sets)

        return guideline_sets

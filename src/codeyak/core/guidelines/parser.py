"""
Guidelines file parser.

Handles parsing and validation of guideline YAML files, including
support for the 'includes' directive.
"""

from typing import List
from pathlib import Path
import re
import yaml
from .models import Guideline
from .exceptions import (
    GuidelinesLoadError,
    BuiltinGuidelineNotFoundError,
    GuidelineIncludeError
)


class GuidelinesParser:
    """
    Parses guideline YAML files and resolves includes.

    Supports:
    - Parsing YAML files into Guideline objects
    - Include mechanism for referencing built-in guidelines
    - Validation of guideline structure and IDs
    """

    def parse_file(
        self,
        path: Path,
        allow_includes: bool = True,
        processed_files: set = None
    ) -> List[Guideline]:
        """
        Parse and validate guidelines from a single YAML file.

        This method supports the 'includes' directive to reference other
        guideline files (currently limited to built-in guidelines).

        Args:
            path: Path to guidelines YAML file
            allow_includes: Whether to process 'includes' directive
            processed_files: Set of already processed files (prevents circular includes)

        Returns:
            List[Guideline]: Validated guidelines from this file and any includes

        Raises:
            FileNotFoundError: If the file doesn't exist
            yaml.YAMLError: If YAML syntax is invalid
            ValueError: If YAML structure is invalid
            GuidelineIncludeError: If includes are malformed or circular
            BuiltinGuidelineNotFoundError: If referenced built-in doesn't exist

        Note:
            This method does not catch exceptions - they bubble up to be handled
            by the caller which wraps all errors in GuidelinesLoadError.
        """
        if processed_files is None:
            processed_files = set()

        # Prevent circular includes
        if path in processed_files:
            raise GuidelineIncludeError(f"Circular include detected: {path}")

        processed_files.add(path)

        # Read and parse YAML
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Handle empty files
        if data is None:
            raise ValueError(
                f"Guidelines file {path.name} is empty or contains only whitespace"
            )

        # Validate top-level structure
        if not isinstance(data, dict):
            raise ValueError(
                f"Guidelines file must contain a YAML dictionary, "
                f"but found {type(data).__name__} in {path.name}"
            )

        all_guidelines = []

        # Process includes first (if enabled)
        if allow_includes and 'includes' in data:
            included_paths = self._parse_includes(data, path)

            for included_path in included_paths:
                print(f"  ↳ Including {included_path.name}...")
                # Recursively parse included files (but don't allow nested includes)
                included_guidelines = self.parse_file(
                    included_path,
                    allow_includes=False,  # Prevent nested includes
                    processed_files=processed_files
                )
                all_guidelines.extend(included_guidelines)

        # Process local guidelines (if present)
        if 'guidelines' in data:
            guidelines_data = data['guidelines']

            if not isinstance(guidelines_data, list):
                raise ValueError("'guidelines' must be a list")

            if not guidelines_data:
                # Empty guidelines list is OK if we have includes
                if not all_guidelines:
                    raise ValueError("Guidelines file contains no guidelines")
            else:
                # Extract prefix from filename
                prefix = path.stem  # e.g., "security" from "security.yaml"

                # Validate and parse each guideline
                seen_ids_in_file = set()

                for idx, item in enumerate(guidelines_data):
                    try:
                        # Provide context about what we're parsing
                        if not isinstance(item, dict):
                            raise ValueError(
                                f"Guideline at index {idx} must be a dictionary, "
                                f"found {type(item).__name__}"
                            )

                        # Extract and validate label
                        if 'label' not in item:
                            raise ValueError(
                                f"Guideline at index {idx} missing required 'label' field"
                            )

                        label = item['label']
                        if not isinstance(label, str):
                            raise ValueError(
                                f"Label must be a string at index {idx}"
                            )

                        # Validate label format (lowercase, alphanumeric, hyphens)
                        if not re.match(r'^[a-z0-9-]+$', label):
                            raise ValueError(
                                f"Label '{label}' at index {idx} must be lowercase alphanumeric with hyphens"
                            )

                        if label.startswith('-') or label.endswith('-'):
                            raise ValueError(
                                f"Label '{label}' at index {idx} cannot start or end with a hyphen"
                            )

                        # Generate ID from prefix and label
                        generated_id = f"{prefix}/{label}"

                        # Check for duplicate labels within this file
                        if generated_id in seen_ids_in_file:
                            raise ValueError(
                                f"Duplicate guideline label '{label}' at index {idx} (ID: {generated_id})"
                            )
                        seen_ids_in_file.add(generated_id)

                        # Validate description field exists
                        if 'description' not in item:
                            raise ValueError(
                                f"Guideline at index {idx} missing required 'description' field"
                            )

                        # Create guideline with generated ID
                        guideline = Guideline(
                            id=generated_id,
                            description=item['description']
                        )

                        all_guidelines.append(guideline)
                    except Exception as e:
                        # Provide helpful context with the guideline data
                        item_preview = str(item)[:100] + "..." if len(str(item)) > 100 else str(item)
                        raise ValueError(
                            f"Invalid guideline at index {idx} in {path.name}: {e}\n"
                            f"Guideline data: {item_preview}"
                        ) from e

        elif not all_guidelines:
            # No guidelines and no includes
            available_keys = ', '.join(f"'{k}'" for k in data.keys())
            raise ValueError(
                f"Guidelines file contains no guidelines. "
                f"Expected 'guidelines' list or 'includes' list, "
                f"but found: {available_keys if available_keys else 'empty file'}"
            )

        return all_guidelines

    def _parse_includes(self, yaml_data: dict, source_file: Path) -> List[Path]:
        """
        Parse 'includes' section from YAML data and resolve to file paths.

        Args:
            yaml_data: Parsed YAML data
            source_file: Path to the file being parsed (for error messages)

        Returns:
            List of paths to included guideline files

        Raises:
            GuidelineIncludeError: If includes format is invalid
            BuiltinGuidelineNotFoundError: If a referenced guideline doesn't exist
        """
        if 'includes' not in yaml_data:
            return []

        includes = yaml_data['includes']

        if not isinstance(includes, list):
            raise GuidelineIncludeError(
                f"'includes' must be a list in {source_file}"
            )

        resolved_paths = []

        for include_ref in includes:
            if not isinstance(include_ref, str):
                raise GuidelineIncludeError(
                    f"Include reference must be a string in {source_file}: {include_ref}"
                )

            # Currently only support builtin: includes
            if include_ref.startswith("builtin:"):
                path = self._resolve_builtin_include(include_ref)
                resolved_paths.append(path)
            else:
                raise GuidelineIncludeError(
                    f"Unsupported include reference in {source_file}: {include_ref}\n"
                    f"Currently supported: 'builtin:name'"
                )

        return resolved_paths

    def _resolve_builtin_include(self, include_ref: str) -> Path:
        """
        Resolve a builtin include reference to a file path.

        Args:
            include_ref: Include reference like "builtin:default" or "builtin:security-focused"

        Returns:
            Path to the built-in guideline file

        Raises:
            GuidelineIncludeError: If the reference format is invalid
            BuiltinGuidelineNotFoundError: If the referenced guideline doesn't exist
        """
        # Validate format
        if not include_ref.startswith("builtin:"):
            raise GuidelineIncludeError(
                f"Invalid include reference: {include_ref}. "
                f"Expected format: 'builtin:name'"
            )

        # Extract guideline name
        guideline_name = include_ref.replace("builtin:", "")

        # Remove .yaml/.yml extension if provided
        if guideline_name.endswith(".yaml"):
            guideline_name = guideline_name[:-5]
        elif guideline_name.endswith(".yml"):
            guideline_name = guideline_name[:-4]

        # Construct path
        builtin_path = self._get_builtin_guidelines_path()

        # Try both .yaml and .yml extensions
        yaml_path = builtin_path / f"{guideline_name}.yaml"
        yml_path = builtin_path / f"{guideline_name}.yml"

        if yaml_path.exists():
            return yaml_path
        elif yml_path.exists():
            return yml_path
        else:
            available = self._list_available_builtins()
            raise BuiltinGuidelineNotFoundError(
                f"Built-in guideline '{guideline_name}' not found.\n"
                f"Available built-in guidelines: {', '.join(available)}"
            )

    def _list_available_builtins(self) -> List[str]:
        """
        List available built-in guideline sets.

        Returns:
            List of filenames (without extension) of available built-in guidelines
        """
        builtin_path = self._get_builtin_guidelines_path()
        yaml_files = list(builtin_path.glob("*.yaml")) + list(builtin_path.glob("*.yml"))
        return [f.stem for f in yaml_files]

    def _get_builtin_guidelines_path(self) -> Path:
        """
        Get the path to built-in guidelines directory.

        Returns:
            Path to the guidelines/ directory within the package

        Raises:
            GuidelinesLoadError: If built-in guidelines cannot be located
        """
        try:
            from importlib import resources

            # Python 3.9+ approach
            if hasattr(resources, 'files'):
                package_files = resources.files('codeyak')
                guidelines_path = package_files / 'guidelines'

                # Convert to Path and verify it exists
                builtin_path = Path(str(guidelines_path))
                if not builtin_path.exists():
                    # Try alternative: using package __file__
                    # We're in core/guidelines/parser.py, need to go up to codeyak/
                    package_root = Path(__file__).parent.parent.parent
                    builtin_path = package_root / 'guidelines'

                if not builtin_path.exists():
                    raise GuidelinesLoadError(
                        "Built-in guidelines directory not found. "
                        "Package may be incorrectly installed."
                    )

                return builtin_path
            else:
                raise NotImplementedError("Requires Python 3.9+")

        except Exception as e:
            raise GuidelinesLoadError(
                f"Failed to locate built-in guidelines: {e}"
            ) from e

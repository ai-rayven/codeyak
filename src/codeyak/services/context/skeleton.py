"""
Skeleton generator for code files.

Generates signature-only views of code, replacing implementations with '...'.
Supports Python, TypeScript, JavaScript, and C#.
"""

from pathlib import Path

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
import tree_sitter_c_sharp as tscsharp
from tree_sitter import Language, Parser, Node


class SkeletonGenerator:
    """
    Generates skeleton views of code files.
    
    A skeleton shows only signatures (class/function definitions) with 
    implementations replaced by '...'.
    """

    def __init__(self) -> None:
        """Initialize parsers for each supported language."""
        self._parsers: dict[str, Parser] = {}
        self._setup_parsers()

    def _setup_parsers(self) -> None:
        """Set up tree-sitter parsers."""
        # Python
        py_parser = Parser(Language(tspython.language()))
        self._parsers[".py"] = py_parser

        # JavaScript
        js_parser = Parser(Language(tsjavascript.language()))
        self._parsers[".js"] = js_parser
        self._parsers[".jsx"] = js_parser

        # TypeScript
        ts_parser = Parser(Language(tstypescript.language_typescript()))
        self._parsers[".ts"] = ts_parser

        tsx_parser = Parser(Language(tstypescript.language_tsx()))
        self._parsers[".tsx"] = tsx_parser

        # C#
        cs_parser = Parser(Language(tscsharp.language()))
        self._parsers[".cs"] = cs_parser

    def generate(self, file_path: str | Path, content: str) -> str:
        """
        Generate a skeleton for an entire file.
        
        Args:
            file_path: Path to determine language from extension
            content: File content to skeletonize
        
        Returns:
            Skeleton version with implementations replaced by '...'
        """
        ext = Path(file_path).suffix.lower()
        
        if ext not in self._parsers:
            # Unsupported language - return as-is
            return content

        parser = self._parsers[ext]
        tree = parser.parse(content.encode("utf-8"))
        
        if ext == ".py":
            return self._generate_python_skeleton(tree.root_node, content)
        elif ext in (".js", ".jsx"):
            return self._generate_javascript_skeleton(tree.root_node, content)
        elif ext in (".ts", ".tsx"):
            return self._generate_typescript_skeleton(tree.root_node, content)
        elif ext == ".cs":
            return self._generate_csharp_skeleton(tree.root_node, content)
        
        return content

    def generate_with_expansion(
        self,
        file_path: str | Path,
        content: str,
        expand_ranges: list[tuple[int, int]] | None = None,
        expand_functions: list[str] | None = None,
    ) -> str:
        """
        Generate skeleton with certain regions shown in full.
        
        Args:
            file_path: Path to determine language
            content: File content
            expand_ranges: List of (start_line, end_line) tuples to show in full (1-indexed)
            expand_functions: List of function/method names to show in full
        
        Returns:
            Skeleton with expanded regions
        """
        ext = Path(file_path).suffix.lower()
        
        if ext not in self._parsers:
            return content

        parser = self._parsers[ext]
        tree = parser.parse(content.encode("utf-8"))
        lines = content.split("\n")
        
        # Find which lines should be expanded
        expand_lines: set[int] = set()
        
        if expand_ranges:
            for start, end in expand_ranges:
                for line in range(start, end + 1):
                    expand_lines.add(line)
        
        if expand_functions:
            # Find functions by name and mark their lines for expansion
            func_ranges = self._find_function_ranges(tree.root_node, ext, expand_functions)
            for start, end in func_ranges:
                for line in range(start, end + 1):
                    expand_lines.add(line)

        if ext == ".py":
            return self._generate_python_skeleton_with_expansion(
                tree.root_node, content, lines, expand_lines
            )
        elif ext in (".js", ".jsx"):
            return self._generate_js_skeleton_with_expansion(
                tree.root_node, content, lines, expand_lines
            )
        elif ext in (".ts", ".tsx"):
            return self._generate_ts_skeleton_with_expansion(
                tree.root_node, content, lines, expand_lines
            )
        elif ext == ".cs":
            return self._generate_csharp_skeleton_with_expansion(
                tree.root_node, content, lines, expand_lines
            )
        
        return content

    def _find_function_ranges(
        self, root: Node, ext: str, function_names: list[str]
    ) -> list[tuple[int, int]]:
        """Find line ranges for functions by name."""
        ranges: list[tuple[int, int]] = []
        names_set = set(function_names)

        def visit(node: Node) -> None:
            name = None
            
            # Python
            if node.type in ("function_definition", "class_definition"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else None
            
            # JavaScript/TypeScript
            elif node.type in ("function_declaration", "method_definition", 
                               "class_declaration", "interface_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else None
            
            # C#
            elif node.type in ("method_declaration", "class_declaration",
                               "interface_declaration", "constructor_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else None

            if name and name in names_set:
                # 1-indexed lines
                ranges.append((node.start_point[0] + 1, node.end_point[0] + 1))

            for child in node.children:
                visit(child)

        visit(root)
        return ranges

    # --- Python skeleton generation ---

    def _generate_python_skeleton(self, root: Node, content: str) -> str:
        """Generate Python skeleton by replacing function bodies with '...'."""
        lines = content.split("\n")
        
        # Find all function bodies to replace
        replacements: list[tuple[int, int, str]] = []  # (start_line, end_line, replacement)
        self._find_python_bodies(root, lines, replacements)
        
        return self._apply_replacements(lines, replacements)

    def _generate_python_skeleton_with_expansion(
        self, root: Node, content: str, lines: list[str], expand_lines: set[int]
    ) -> str:
        """Generate Python skeleton with expansion."""
        replacements: list[tuple[int, int, str]] = []
        self._find_python_bodies(root, lines, replacements)
        
        # Filter out replacements that overlap with expanded lines
        filtered = []
        for start, end, repl in replacements:
            should_expand = any(line in expand_lines for line in range(start, end + 1))
            if not should_expand:
                filtered.append((start, end, repl))
        
        return self._apply_replacements(lines, filtered)

    def _find_python_bodies(
        self, node: Node, lines: list[str], replacements: list[tuple[int, int, str]]
    ) -> None:
        """Find function/method bodies in Python and add replacements."""
        if node.type == "function_definition":
            # Find the block (body) child
            for child in node.children:
                if child.type == "block":
                    body_start = child.start_point[0] + 1  # 1-indexed
                    body_end = child.end_point[0] + 1
                    
                    # Get the indentation of the first line in the body
                    if body_start <= len(lines):
                        first_body_line = lines[body_start - 1]
                        indent = len(first_body_line) - len(first_body_line.lstrip())
                        replacement = " " * indent + "..."
                        
                        # Only replace if body spans multiple lines or is not just '...'
                        if body_start <= body_end:
                            replacements.append((body_start, body_end, replacement))
                    break
        
        # Recurse into children
        for child in node.children:
            self._find_python_bodies(child, lines, replacements)

    # --- JavaScript skeleton generation ---

    def _generate_javascript_skeleton(self, root: Node, content: str) -> str:
        """Generate JavaScript skeleton."""
        lines = content.split("\n")
        # Find all function bodies and replace with ...
        replacements: list[tuple[int, int, str]] = []  # (start_line, end_line, replacement)
        
        self._find_js_bodies(root, replacements, lines)
        
        return self._apply_replacements(lines, replacements)

    def _generate_js_skeleton_with_expansion(
        self, root: Node, content: str, lines: list[str], expand_lines: set[int]
    ) -> str:
        """Generate JS skeleton with expansion."""
        replacements: list[tuple[int, int, str]] = []
        self._find_js_bodies(root, replacements, lines)
        
        # Filter out replacements that overlap with expanded lines
        filtered = []
        for start, end, repl in replacements:
            # Check if any line in this range should be expanded
            should_expand = any(line in expand_lines for line in range(start, end + 1))
            if not should_expand:
                filtered.append((start, end, repl))
        
        return self._apply_replacements(lines, filtered)

    def _find_js_bodies(
        self, node: Node, replacements: list[tuple[int, int, str]], lines: list[str]
    ) -> None:
        """Find function bodies in JavaScript."""
        if node.type in ("function_declaration", "method_definition", "arrow_function"):
            body = node.child_by_field_name("body")
            if body and body.type == "statement_block":
                # Get the line where the body starts
                body_start_line = body.start_point[0] + 1  # 1-indexed
                body_end_line = body.end_point[0] + 1
                
                # If body spans multiple lines, replace with { ... }
                if body_start_line != body_end_line or body.start_point[1] != body.end_point[1]:
                    # Get the signature part (everything before the body on the same line)
                    sig_line = lines[body_start_line - 1] if body_start_line <= len(lines) else ""
                    body_col = body.start_point[1]
                    signature = sig_line[:body_col].rstrip()
                    
                    # Build replacement with signature + { ... }
                    replacement = signature + " { ... }"
                    
                    # Replace from body start line to body end line
                    replacements.append((body_start_line, body_end_line, replacement))

        for child in node.children:
            self._find_js_bodies(child, replacements, lines)

    # --- TypeScript skeleton generation ---

    def _generate_typescript_skeleton(self, root: Node, content: str) -> str:
        """Generate TypeScript skeleton."""
        lines = content.split("\n")
        replacements: list[tuple[int, int, str]] = []
        
        self._find_ts_bodies(root, replacements, lines)
        
        return self._apply_replacements(lines, replacements)

    def _generate_ts_skeleton_with_expansion(
        self, root: Node, content: str, lines: list[str], expand_lines: set[int]
    ) -> str:
        """Generate TypeScript skeleton with expansion."""
        replacements: list[tuple[int, int, str]] = []
        self._find_ts_bodies(root, replacements, lines)
        
        filtered = []
        for start, end, repl in replacements:
            should_expand = any(line in expand_lines for line in range(start, end + 1))
            if not should_expand:
                filtered.append((start, end, repl))
        
        return self._apply_replacements(lines, filtered)

    def _find_ts_bodies(
        self, node: Node, replacements: list[tuple[int, int, str]], lines: list[str]
    ) -> None:
        """Find function bodies in TypeScript."""
        if node.type in ("function_declaration", "method_definition", "arrow_function"):
            body = node.child_by_field_name("body")
            if body and body.type == "statement_block":
                body_start_line = body.start_point[0] + 1  # 1-indexed
                body_end_line = body.end_point[0] + 1
                
                # If body spans multiple lines, replace with { ... }
                if body_start_line != body_end_line or body.start_point[1] != body.end_point[1]:
                    # Get the signature part (everything before the body on the same line)
                    sig_line = lines[body_start_line - 1] if body_start_line <= len(lines) else ""
                    body_col = body.start_point[1]
                    signature = sig_line[:body_col].rstrip()
                    
                    # Build replacement with signature + { ... }
                    replacement = signature + " { ... }"
                    
                    replacements.append((body_start_line, body_end_line, replacement))

        for child in node.children:
            self._find_ts_bodies(child, replacements, lines)

    # --- C# skeleton generation ---

    def _generate_csharp_skeleton(self, root: Node, content: str) -> str:
        """Generate C# skeleton."""
        lines = content.split("\n")
        replacements: list[tuple[int, int, str]] = []
        
        self._find_csharp_bodies(root, replacements, lines)
        
        return self._apply_replacements(lines, replacements)

    def _generate_csharp_skeleton_with_expansion(
        self, root: Node, content: str, lines: list[str], expand_lines: set[int]
    ) -> str:
        """Generate C# skeleton with expansion."""
        replacements: list[tuple[int, int, str]] = []
        self._find_csharp_bodies(root, replacements, lines)
        
        filtered = []
        for start, end, repl in replacements:
            should_expand = any(line in expand_lines for line in range(start, end + 1))
            if not should_expand:
                filtered.append((start, end, repl))
        
        return self._apply_replacements(lines, filtered)

    def _find_csharp_bodies(
        self, node: Node, replacements: list[tuple[int, int, str]], lines: list[str]
    ) -> None:
        """Find method bodies in C#."""
        if node.type in ("method_declaration", "constructor_declaration"):
            body = node.child_by_field_name("body")
            if body and body.type == "block":
                body_start_line = body.start_point[0] + 1
                body_end_line = body.end_point[0] + 1
                
                # If body spans multiple lines
                if body_start_line != body_end_line or body.start_point[1] != body.end_point[1]:
                    # In C#, the method signature might be on the previous line
                    # (common Allman brace style)
                    method_start_line = node.start_point[0] + 1
                    
                    # Get the signature (from method start to body start)
                    sig_lines = []
                    for sig_line_num in range(method_start_line, body_start_line + 1):
                        if sig_line_num <= len(lines):
                            sig_line = lines[sig_line_num - 1]
                            # If this is the body start line, only take up to the brace
                            if sig_line_num == body_start_line:
                                body_col = body.start_point[1]
                                sig_line = sig_line[:body_col].rstrip()
                            sig_lines.append(sig_line.strip())
                    
                    # Join signature lines and add { ... }
                    signature = " ".join(filter(None, sig_lines))
                    replacement = "    " + signature + " { ... }"  # Add indentation
                    
                    replacements.append((method_start_line, body_end_line, replacement))
        
        # Handle expression-bodied members
        if node.type in ("method_declaration", "property_declaration"):
            for child in node.children:
                if child.type == "arrow_expression_clause":
                    # Keep the => but replace the expression with ...
                    pass  # For now, keep expression-bodied members as-is

        for child in node.children:
            self._find_csharp_bodies(child, replacements, lines)

    # --- Helper methods ---

    def _apply_replacements(
        self, lines: list[str], replacements: list[tuple[int, int, str]]
    ) -> str:
        """Apply replacements to lines, handling overlaps."""
        if not replacements:
            return "\n".join(lines)
        
        # Sort by start line
        replacements.sort(key=lambda x: x[0])
        
        result: list[str] = []
        current_line = 1  # 1-indexed
        
        for start, end, replacement in replacements:
            # Add lines before this replacement
            while current_line < start:
                result.append(lines[current_line - 1])
                current_line += 1
            
            # Add replacement
            result.append(replacement)
            current_line = end + 1
        
        # Add remaining lines
        while current_line <= len(lines):
            result.append(lines[current_line - 1])
            current_line += 1
        
        return "\n".join(result)

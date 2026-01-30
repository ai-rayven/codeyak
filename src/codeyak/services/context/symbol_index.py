"""
Symbol index using tree-sitter for fast codebase parsing.

Extracts classes, functions, methods, and interfaces from supported languages:
- Python
- TypeScript
- JavaScript
- C#
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
import tree_sitter_c_sharp as tscsharp
from tree_sitter import Language, Parser, Node


class SymbolKind(str, Enum):
    """Kind of symbol extracted from code."""
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"


@dataclass
class SymbolLocation:
    """Location of a symbol in the codebase."""
    file_path: str
    name: str
    kind: SymbolKind
    start_line: int  # 1-indexed
    end_line: int    # 1-indexed, inclusive
    signature: str   # The signature line(s) for skeleton rendering

    def __hash__(self) -> int:
        return hash((self.file_path, self.name, self.start_line))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SymbolLocation):
            return False
        return (
            self.file_path == other.file_path
            and self.name == other.name
            and self.start_line == other.start_line
        )


@dataclass
class SymbolIndex:
    """
    Index of all symbols in a codebase.
    
    Built by parsing files with tree-sitter and extracting symbol definitions.
    """
    symbols: dict[str, list[SymbolLocation]] = field(default_factory=dict)
    _file_symbols: dict[str, list[SymbolLocation]] = field(default_factory=dict)
    
    # Language configurations
    _parsers: dict[str, Parser] = field(default_factory=dict, repr=False)
    _extractors: dict[str, Callable[[Node, str], list[SymbolLocation]]] = field(
        default_factory=dict, repr=False
    )

    def __post_init__(self) -> None:
        """Initialize parsers and extractors for each language."""
        self._setup_parsers()
        self._setup_extractors()

    def _setup_parsers(self) -> None:
        """Set up tree-sitter parsers for each supported language."""
        # Python
        py_parser = Parser(Language(tspython.language()))
        self._parsers["python"] = py_parser
        self._parsers[".py"] = py_parser

        # JavaScript
        js_parser = Parser(Language(tsjavascript.language()))
        self._parsers["javascript"] = js_parser
        self._parsers[".js"] = js_parser
        self._parsers[".jsx"] = js_parser

        # TypeScript
        ts_parser = Parser(Language(tstypescript.language_typescript()))
        self._parsers["typescript"] = ts_parser
        self._parsers[".ts"] = ts_parser

        # TSX (TypeScript with JSX)
        tsx_parser = Parser(Language(tstypescript.language_tsx()))
        self._parsers[".tsx"] = tsx_parser

        # C#
        cs_parser = Parser(Language(tscsharp.language()))
        self._parsers["csharp"] = cs_parser
        self._parsers[".cs"] = cs_parser

    def _setup_extractors(self) -> None:
        """Set up symbol extractors for each language."""
        self._extractors[".py"] = self._extract_python_symbols
        self._extractors[".js"] = self._extract_javascript_symbols
        self._extractors[".jsx"] = self._extract_javascript_symbols
        self._extractors[".ts"] = self._extract_typescript_symbols
        self._extractors[".tsx"] = self._extract_typescript_symbols
        self._extractors[".cs"] = self._extract_csharp_symbols

    @classmethod
    def build(cls, repo_path: Path, exclude_patterns: list[str] | None = None) -> "SymbolIndex":
        """
        Build a symbol index for a repository.
        
        Args:
            repo_path: Root path of the repository
            exclude_patterns: Glob patterns to exclude (e.g., ["**/node_modules/**"])
        
        Returns:
            SymbolIndex with all extracted symbols
        """
        index = cls()
        exclude_patterns = exclude_patterns or [
            "**/node_modules/**",
            "**/.git/**",
            "**/venv/**",
            "**/__pycache__/**",
            "**/dist/**",
            "**/build/**",
            "**/.venv/**",
            "**/env/**",
        ]

        supported_extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".cs"}

        for ext in supported_extensions:
            for file_path in repo_path.rglob(f"*{ext}"):
                # Check exclusions
                should_exclude = False
                for pattern in exclude_patterns:
                    if file_path.match(pattern):
                        should_exclude = True
                        break
                
                if should_exclude:
                    continue

                try:
                    index._index_file(file_path, repo_path)
                except Exception:
                    # Skip files that can't be parsed
                    continue

        return index

    def _index_file(self, file_path: Path, repo_path: Path) -> None:
        """Index a single file."""
        ext = file_path.suffix.lower()
        
        if ext not in self._parsers or ext not in self._extractors:
            return

        content = file_path.read_text(encoding="utf-8", errors="replace")
        parser = self._parsers[ext]
        extractor = self._extractors[ext]

        tree = parser.parse(content.encode("utf-8"))
        relative_path = str(file_path.relative_to(repo_path))
        
        symbols = extractor(tree.root_node, relative_path)
        
        # Store symbols
        for symbol in symbols:
            if symbol.name not in self.symbols:
                self.symbols[symbol.name] = []
            self.symbols[symbol.name].append(symbol)

        if relative_path not in self._file_symbols:
            self._file_symbols[relative_path] = []
        self._file_symbols[relative_path].extend(symbols)

    def resolve(
        self, 
        name: str, 
        file_hint: str | None = None
    ) -> SymbolLocation | None:
        """
        Resolve a symbol name to its location.
        
        Uses strict resolution - returns None if:
        - Symbol not found
        - Multiple symbols found and no file_hint provided
        - file_hint doesn't match any of the found symbols
        
        Args:
            name: Symbol name to resolve
            file_hint: Optional file path hint for disambiguation
        
        Returns:
            SymbolLocation if uniquely resolved, None otherwise
        """
        if name not in self.symbols:
            return None

        locations = self.symbols[name]
        
        if len(locations) == 1:
            return locations[0]

        # Multiple locations - need file_hint
        if not file_hint:
            return None

        # Try to match file hint
        for loc in locations:
            if file_hint in loc.file_path or loc.file_path.endswith(file_hint):
                return loc

        return None

    def get_file_symbols(self, file_path: str) -> list[SymbolLocation]:
        """Get all symbols defined in a file."""
        return self._file_symbols.get(file_path, [])

    def get_symbol_at_line(self, file_path: str, line: int) -> SymbolLocation | None:
        """Get the symbol that contains a specific line."""
        symbols = self.get_file_symbols(file_path)
        for symbol in symbols:
            if symbol.start_line <= line <= symbol.end_line:
                return symbol
        return None

    # --- Language-specific extractors ---

    def _extract_python_symbols(
        self, root: Node, file_path: str
    ) -> list[SymbolLocation]:
        """Extract symbols from Python code."""
        symbols: list[SymbolLocation] = []
        
        def visit(node: Node, parent_class: str | None = None) -> None:
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_python_class_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.CLASS,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                    # Visit children with class context
                    for child in node.children:
                        visit(child, name)
                return

            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_python_function_signature(node)
                    kind = SymbolKind.METHOD if parent_class else SymbolKind.FUNCTION
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=kind,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            # Continue visiting children
            for child in node.children:
                visit(child, parent_class)

        visit(root)
        return symbols

    def _get_python_class_signature(self, node: Node) -> str:
        """Extract class signature from Python class_definition node."""
        parts = []
        for child in node.children:
            if child.type in ("class", "identifier", "argument_list", ":"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "block":
                break
        return " ".join(parts).replace(" :", ":").replace("( ", "(").replace(" )", ")")

    def _get_python_function_signature(self, node: Node) -> str:
        """Extract function signature from Python function_definition node."""
        parts = []
        for child in node.children:
            if child.type in ("def", "async", "identifier", "parameters", "->", "type", ":"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "block":
                break
        return " ".join(parts).replace(" :", ":").replace("( ", "(").replace(" )", ")")

    def _extract_javascript_symbols(
        self, root: Node, file_path: str
    ) -> list[SymbolLocation]:
        """Extract symbols from JavaScript code."""
        symbols: list[SymbolLocation] = []

        def visit(node: Node, parent_class: str | None = None) -> None:
            # Class declarations
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_js_class_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.CLASS,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                    # Visit class body for methods
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            visit(child, name)
                return

            # Method definitions in classes
            if node.type == "method_definition" and parent_class:
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_js_method_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.METHOD,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            # Function declarations
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_js_function_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.FUNCTION,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            # Arrow functions assigned to variables
            if node.type == "lexical_declaration" or node.type == "variable_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        value_node = child.child_by_field_name("value")
                        if name_node and value_node and value_node.type == "arrow_function":
                            name = name_node.text.decode("utf-8") if name_node.text else ""
                            signature = self._get_js_arrow_signature(node, name_node, value_node)
                            symbols.append(SymbolLocation(
                                file_path=file_path,
                                name=name,
                                kind=SymbolKind.FUNCTION,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                signature=signature,
                            ))
                return

            # Continue visiting children
            for child in node.children:
                visit(child, parent_class)

        visit(root)
        return symbols

    def _get_js_class_signature(self, node: Node) -> str:
        """Extract class signature from JavaScript class_declaration node."""
        parts = []
        for child in node.children:
            if child.type in ("class", "identifier", "extends", "class_heritage"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "class_body":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_js_method_signature(self, node: Node) -> str:
        """Extract method signature from JavaScript method_definition node."""
        parts = []
        for child in node.children:
            if child.type in ("async", "static", "get", "set", "property_identifier", 
                              "formal_parameters", "identifier"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "statement_block":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_js_function_signature(self, node: Node) -> str:
        """Extract function signature from JavaScript function_declaration node."""
        parts = []
        for child in node.children:
            if child.type in ("async", "function", "identifier", "formal_parameters"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "statement_block":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_js_arrow_signature(
        self, decl_node: Node, name_node: Node, arrow_node: Node
    ) -> str:
        """Extract arrow function signature."""
        # Get const/let/var
        keyword = ""
        for child in decl_node.children:
            if child.type in ("const", "let", "var"):
                keyword = child.text.decode("utf-8") if child.text else ""
                break
        
        name = name_node.text.decode("utf-8") if name_node.text else ""
        
        # Get parameters
        params = ""
        for child in arrow_node.children:
            if child.type in ("formal_parameters", "identifier"):
                params = child.text.decode("utf-8") if child.text else ""
                break

        return f"{keyword} {name} = ({params}) => {{"

    def _extract_typescript_symbols(
        self, root: Node, file_path: str
    ) -> list[SymbolLocation]:
        """Extract symbols from TypeScript code."""
        symbols: list[SymbolLocation] = []

        def visit(node: Node, parent_class: str | None = None) -> None:
            # Interface declarations
            if node.type == "interface_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_ts_interface_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.INTERFACE,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            # Type alias declarations
            if node.type == "type_alias_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = node.text.decode("utf-8").split("\n")[0] if node.text else ""
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.INTERFACE,  # Treat type aliases as interfaces
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            # Class declarations
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_ts_class_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.CLASS,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            visit(child, name)
                return

            # Method definitions
            if node.type == "method_definition" and parent_class:
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_ts_method_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.METHOD,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            # Function declarations
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_ts_function_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.FUNCTION,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            # Arrow functions
            if node.type == "lexical_declaration" or node.type == "variable_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        value_node = child.child_by_field_name("value")
                        if name_node and value_node and value_node.type == "arrow_function":
                            name = name_node.text.decode("utf-8") if name_node.text else ""
                            signature = self._get_ts_arrow_signature(node, name_node, value_node)
                            symbols.append(SymbolLocation(
                                file_path=file_path,
                                name=name,
                                kind=SymbolKind.FUNCTION,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                signature=signature,
                            ))
                return

            for child in node.children:
                visit(child, parent_class)

        visit(root)
        return symbols

    def _get_ts_interface_signature(self, node: Node) -> str:
        """Extract interface signature from TypeScript."""
        parts = []
        for child in node.children:
            if child.type in ("export", "interface", "identifier", "type_identifier",
                              "extends", "type_parameters"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "object_type":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_ts_class_signature(self, node: Node) -> str:
        """Extract class signature from TypeScript."""
        parts = []
        for child in node.children:
            if child.type in ("export", "abstract", "class", "identifier", "type_identifier",
                              "extends", "implements", "type_parameters", "class_heritage"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "class_body":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_ts_method_signature(self, node: Node) -> str:
        """Extract method signature from TypeScript."""
        parts = []
        for child in node.children:
            if child.type in ("accessibility_modifier", "static", "async", "readonly",
                              "get", "set", "property_identifier", "identifier",
                              "formal_parameters", "call_signature", "type_annotation"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "statement_block":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_ts_function_signature(self, node: Node) -> str:
        """Extract function signature from TypeScript."""
        parts = []
        for child in node.children:
            if child.type in ("export", "async", "function", "identifier",
                              "formal_parameters", "type_parameters", "type_annotation"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "statement_block":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_ts_arrow_signature(
        self, decl_node: Node, name_node: Node, arrow_node: Node
    ) -> str:
        """Extract arrow function signature from TypeScript."""
        keyword = ""
        for child in decl_node.children:
            if child.type in ("const", "let", "var"):
                keyword = child.text.decode("utf-8") if child.text else ""
                break

        name = name_node.text.decode("utf-8") if name_node.text else ""

        # Get type annotation and parameters
        params = ""
        return_type = ""
        for child in arrow_node.children:
            if child.type in ("formal_parameters",):
                params = child.text.decode("utf-8") if child.text else ""
            elif child.type == "type_annotation":
                return_type = child.text.decode("utf-8") if child.text else ""

        sig = f"{keyword} {name} = {params}"
        if return_type:
            sig += f"{return_type}"
        sig += " => {"
        return sig

    def _extract_csharp_symbols(
        self, root: Node, file_path: str
    ) -> list[SymbolLocation]:
        """Extract symbols from C# code."""
        symbols: list[SymbolLocation] = []

        def visit(node: Node, parent_class: str | None = None) -> None:
            # Interface declarations
            if node.type == "interface_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_csharp_interface_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.INTERFACE,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            visit(child, name)
                return

            # Class declarations
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_csharp_class_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.CLASS,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            visit(child, name)
                return

            # Struct declarations
            if node.type == "struct_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_csharp_struct_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.CLASS,  # Treat structs as classes
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            visit(child, name)
                return

            # Method declarations
            if node.type == "method_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_csharp_method_signature(node)
                    kind = SymbolKind.METHOD if parent_class else SymbolKind.FUNCTION
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=kind,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            # Constructor declarations
            if node.type == "constructor_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8") if name_node.text else ""
                    signature = self._get_csharp_constructor_signature(node)
                    symbols.append(SymbolLocation(
                        file_path=file_path,
                        name=name,
                        kind=SymbolKind.METHOD,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=signature,
                    ))
                return

            for child in node.children:
                visit(child, parent_class)

        visit(root)
        return symbols

    def _get_csharp_interface_signature(self, node: Node) -> str:
        """Extract interface signature from C#."""
        parts = []
        for child in node.children:
            if child.type in ("modifier", "interface", "identifier", "type_parameter_list",
                              "base_list"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "declaration_list":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_csharp_class_signature(self, node: Node) -> str:
        """Extract class signature from C#."""
        parts = []
        for child in node.children:
            if child.type in ("modifier", "class", "identifier", "type_parameter_list",
                              "base_list"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "declaration_list":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_csharp_struct_signature(self, node: Node) -> str:
        """Extract struct signature from C#."""
        parts = []
        for child in node.children:
            if child.type in ("modifier", "struct", "identifier", "type_parameter_list",
                              "base_list"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "declaration_list":
                parts.append("{")
                break
        return " ".join(parts)

    def _get_csharp_method_signature(self, node: Node) -> str:
        """Extract method signature from C#."""
        parts = []
        for child in node.children:
            if child.type in ("modifier", "type", "predefined_type", "identifier",
                              "type_parameter_list", "parameter_list", "generic_name",
                              "nullable_type", "array_type"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "block":
                parts.append("{")
                break
            elif child.type == "arrow_expression_clause":
                parts.append("=>")
                break
        return " ".join(parts)

    def _get_csharp_constructor_signature(self, node: Node) -> str:
        """Extract constructor signature from C#."""
        parts = []
        for child in node.children:
            if child.type in ("modifier", "identifier", "parameter_list",
                              "constructor_initializer"):
                text = child.text.decode("utf-8") if child.text else ""
                parts.append(text)
            elif child.type == "block":
                parts.append("{")
                break
        return " ".join(parts)

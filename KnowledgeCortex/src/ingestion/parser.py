"""Tree-sitter based code parser for extracting code structure."""

from dataclasses import dataclass, field
from pathlib import Path
import tree_sitter_python as ts_python
import tree_sitter_javascript as ts_javascript
import tree_sitter_typescript as ts_typescript
from tree_sitter import Language, Parser


@dataclass
class FunctionInfo:
    """Information about a function or method."""
    name: str
    line_start: int
    line_end: int
    parameters: list[str] = field(default_factory=list)
    docstring: str | None = None
    is_method: bool = False
    class_name: str | None = None  # If it's a method, which class


@dataclass
class ClassInfo:
    """Information about a class."""
    name: str
    line_start: int
    line_end: int
    bases: list[str] = field(default_factory=list)  # Parent classes
    methods: list[str] = field(default_factory=list)  # Method names
    docstring: str | None = None


@dataclass
class ImportInfo:
    """Information about an import statement."""
    module: str  # The module being imported
    names: list[str] = field(default_factory=list)  # Specific names (for from X import Y)
    alias: str | None = None  # Import alias
    line: int = 0


@dataclass
class ParsedFile:
    """Result of parsing a source file."""
    path: Path
    language: str
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    lines_of_code: int = 0
    parse_errors: list[str] = field(default_factory=list)


class CodeParser:
    """
    Multi-language code parser using Tree-sitter.

    Supports Python, JavaScript, and TypeScript.
    """

    def __init__(self):
        self._parsers: dict[str, Parser] = {}
        self._init_parsers()

    def _init_parsers(self):
        """Initialize parsers for supported languages."""
        # Python
        py_parser = Parser(Language(ts_python.language()))
        self._parsers["python"] = py_parser

        # JavaScript
        js_parser = Parser(Language(ts_javascript.language()))
        self._parsers["javascript"] = js_parser

        # TypeScript
        tsx_parser = Parser(Language(ts_typescript.language_tsx()))
        self._parsers["typescript"] = tsx_parser

    def parse_file(self, file_path: Path, language: str | None = None) -> ParsedFile:
        """
        Parse a source file and extract structural information.

        Args:
            file_path: Path to the source file
            language: Language hint (auto-detected if not provided)

        Returns:
            ParsedFile with extracted functions, classes, and imports
        """
        if language is None:
            language = self._detect_language(file_path)

        if language not in self._parsers:
            return ParsedFile(
                path=file_path,
                language=language,
                parse_errors=[f"Unsupported language: {language}"]
            )

        try:
            content = file_path.read_bytes()
            content_str = content.decode("utf-8", errors="replace")
        except Exception as e:
            return ParsedFile(
                path=file_path,
                language=language,
                parse_errors=[f"Failed to read file: {e}"]
            )

        parser = self._parsers[language]
        tree = parser.parse(content)

        result = ParsedFile(
            path=file_path,
            language=language,
            lines_of_code=content_str.count("\n") + 1
        )

        # Extract based on language
        if language == "python":
            self._extract_python(tree.root_node, content_str, result)
        elif language in ("javascript", "typescript"):
            self._extract_javascript(tree.root_node, content_str, result)

        return result

    def _detect_language(self, file_path: Path) -> str:
        """Detect language from file extension."""
        ext = file_path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
        }
        return mapping.get(ext, "unknown")

    def _get_node_text(self, node, source: str) -> str:
        """Get the text content of a node."""
        return source[node.start_byte:node.end_byte]

    def _extract_python(self, root_node, source: str, result: ParsedFile):
        """Extract Python-specific constructs."""

        def walk(node, class_context: str | None = None):
            if node.type == "function_definition":
                func = self._parse_python_function(node, source, class_context)
                if class_context:
                    func.is_method = True
                    func.class_name = class_context
                result.functions.append(func)

            elif node.type == "class_definition":
                cls = self._parse_python_class(node, source)
                result.classes.append(cls)
                # Recursively find methods
                for child in node.children:
                    if child.type == "block":
                        for block_child in child.children:
                            walk(block_child, cls.name)
                return  # Don't recurse further, we handled methods

            elif node.type == "import_statement":
                imp = self._parse_python_import(node, source)
                if imp:
                    result.imports.append(imp)

            elif node.type == "import_from_statement":
                imp = self._parse_python_from_import(node, source)
                if imp:
                    result.imports.append(imp)

            # Recurse into children
            for child in node.children:
                walk(child, class_context)

        walk(root_node)

    def _parse_python_function(self, node, source: str, class_context: str | None) -> FunctionInfo:
        """Parse a Python function definition."""
        name = ""
        params = []
        docstring = None

        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child, source)
            elif child.type == "parameters":
                for param in child.children:
                    if param.type == "identifier":
                        params.append(self._get_node_text(param, source))
                    elif param.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
                        # Get the parameter name (first identifier)
                        for p_child in param.children:
                            if p_child.type == "identifier":
                                params.append(self._get_node_text(p_child, source))
                                break
            elif child.type == "block":
                # Check for docstring (first expression_statement with string)
                for block_child in child.children:
                    if block_child.type == "expression_statement":
                        for expr_child in block_child.children:
                            if expr_child.type == "string":
                                docstring = self._get_node_text(expr_child, source).strip("\"'")
                                break
                    break  # Only check first statement

        return FunctionInfo(
            name=name,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parameters=params,
            docstring=docstring,
        )

    def _parse_python_class(self, node, source: str) -> ClassInfo:
        """Parse a Python class definition."""
        name = ""
        bases = []
        docstring = None

        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child, source)
            elif child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier":
                        bases.append(self._get_node_text(arg, source))
            elif child.type == "block":
                # Check for docstring
                for block_child in child.children:
                    if block_child.type == "expression_statement":
                        for expr_child in block_child.children:
                            if expr_child.type == "string":
                                docstring = self._get_node_text(expr_child, source).strip("\"'")
                                break
                    break

        return ClassInfo(
            name=name,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            bases=bases,
            docstring=docstring,
        )

    def _parse_python_import(self, node, source: str) -> ImportInfo | None:
        """Parse 'import X' statement."""
        for child in node.children:
            if child.type == "dotted_name":
                module = self._get_node_text(child, source)
                return ImportInfo(
                    module=module,
                    line=node.start_point[0] + 1
                )
            elif child.type == "aliased_import":
                module = ""
                alias = None
                for ac in child.children:
                    if ac.type == "dotted_name":
                        module = self._get_node_text(ac, source)
                    elif ac.type == "identifier":
                        alias = self._get_node_text(ac, source)
                return ImportInfo(
                    module=module,
                    alias=alias,
                    line=node.start_point[0] + 1
                )
        return None

    def _parse_python_from_import(self, node, source: str) -> ImportInfo | None:
        """Parse 'from X import Y' statement."""
        module = ""
        names = []

        for child in node.children:
            if child.type == "dotted_name":
                module = self._get_node_text(child, source)
            elif child.type == "import_prefix":
                # Relative import (.)
                module = self._get_node_text(child, source)
            elif child.type in ("identifier", "aliased_import"):
                if child.type == "identifier":
                    names.append(self._get_node_text(child, source))
                else:
                    for ac in child.children:
                        if ac.type == "identifier":
                            names.append(self._get_node_text(ac, source))
                            break

        if module or names:
            return ImportInfo(
                module=module,
                names=names,
                line=node.start_point[0] + 1
            )
        return None

    def _extract_javascript(self, root_node, source: str, result: ParsedFile):
        """Extract JavaScript/TypeScript constructs."""

        def walk(node, class_context: str | None = None):
            # Function declarations
            if node.type in ("function_declaration", "function"):
                func = self._parse_js_function(node, source, class_context)
                if func.name:  # Skip anonymous functions at top level
                    result.functions.append(func)

            # Arrow functions with variable declaration
            elif node.type == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        name = None
                        for vc in child.children:
                            if vc.type == "identifier":
                                name = self._get_node_text(vc, source)
                            elif vc.type == "arrow_function" and name:
                                func = self._parse_js_arrow_function(vc, source, name)
                                result.functions.append(func)

            # Class declarations
            elif node.type == "class_declaration":
                cls = self._parse_js_class(node, source)
                result.classes.append(cls)
                # Find methods
                for child in node.children:
                    if child.type == "class_body":
                        for body_child in child.children:
                            walk(body_child, cls.name)
                return

            # Method definitions (inside class)
            elif node.type == "method_definition" and class_context:
                func = self._parse_js_method(node, source, class_context)
                result.functions.append(func)

            # Import statements
            elif node.type == "import_statement":
                imp = self._parse_js_import(node, source)
                if imp:
                    result.imports.append(imp)

            # Recurse
            for child in node.children:
                walk(child, class_context)

        walk(root_node)

    def _parse_js_function(self, node, source: str, class_context: str | None) -> FunctionInfo:
        """Parse a JavaScript function declaration."""
        name = ""
        params = []

        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child, source)
            elif child.type == "formal_parameters":
                for param in child.children:
                    if param.type == "identifier":
                        params.append(self._get_node_text(param, source))
                    elif param.type in ("required_parameter", "optional_parameter"):
                        for pc in param.children:
                            if pc.type == "identifier":
                                params.append(self._get_node_text(pc, source))
                                break

        return FunctionInfo(
            name=name,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parameters=params,
            is_method=class_context is not None,
            class_name=class_context,
        )

    def _parse_js_arrow_function(self, node, source: str, name: str) -> FunctionInfo:
        """Parse a JavaScript arrow function."""
        params = []

        for child in node.children:
            if child.type == "formal_parameters":
                for param in child.children:
                    if param.type == "identifier":
                        params.append(self._get_node_text(param, source))
            elif child.type == "identifier":
                # Single param without parens
                params.append(self._get_node_text(child, source))

        return FunctionInfo(
            name=name,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parameters=params,
        )

    def _parse_js_method(self, node, source: str, class_context: str) -> FunctionInfo:
        """Parse a JavaScript class method."""
        name = ""
        params = []

        for child in node.children:
            if child.type == "property_identifier":
                name = self._get_node_text(child, source)
            elif child.type == "formal_parameters":
                for param in child.children:
                    if param.type == "identifier":
                        params.append(self._get_node_text(param, source))

        return FunctionInfo(
            name=name,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parameters=params,
            is_method=True,
            class_name=class_context,
        )

    def _parse_js_class(self, node, source: str) -> ClassInfo:
        """Parse a JavaScript class declaration."""
        name = ""
        bases = []

        for child in node.children:
            if child.type == "type_identifier" or child.type == "identifier":
                if not name:
                    name = self._get_node_text(child, source)
            elif child.type == "class_heritage":
                for hc in child.children:
                    if hc.type == "identifier":
                        bases.append(self._get_node_text(hc, source))

        return ClassInfo(
            name=name,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            bases=bases,
        )

    def _parse_js_import(self, node, source: str) -> ImportInfo | None:
        """Parse a JavaScript import statement."""
        module = ""
        names = []

        for child in node.children:
            if child.type == "string":
                module = self._get_node_text(child, source).strip("\"'")
            elif child.type == "import_clause":
                for ic in child.children:
                    if ic.type == "identifier":
                        names.append(self._get_node_text(ic, source))
                    elif ic.type == "named_imports":
                        for ni in ic.children:
                            if ni.type == "import_specifier":
                                for spec in ni.children:
                                    if spec.type == "identifier":
                                        names.append(self._get_node_text(spec, source))
                                        break

        if module:
            return ImportInfo(
                module=module,
                names=names,
                line=node.start_point[0] + 1
            )
        return None

"""
ctx map — Codebase skeleton generator using Tree-sitter.

Parses source code files using Tree-sitter ASTs and extracts only
structural information (function signatures, class definitions, imports)
to produce a compressed codebase map. Zero AI, zero tokens, pure parsing.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_java as tsjava
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser, Node


# ─── Language Registry ─────────────────────────────────────────────────────────

LANGUAGE_MAP: Dict[str, Tuple] = {
    ".py": ("python", tspython),
    ".js": ("javascript", tsjavascript),
    ".jsx": ("javascript", tsjavascript),
    ".java": ("java", tsjava),
    ".ts": ("typescript", tstypescript),
    ".tsx": ("typescript", tstypescript),
}

# File patterns to always ignore
IGNORE_PATTERNS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".egg-info", ".tox", ".nox",
    "__pypackages__", ".ctx_output",
}

IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".zip", ".tar", ".gz", ".bz2",
    ".lock", ".log",
}


def _get_parser(extension: str) -> Optional[Parser]:
    """Create a Tree-sitter parser for the given file extension."""
    if extension not in LANGUAGE_MAP:
        return None
    lang_name, lang_module = LANGUAGE_MAP[extension]
    language = Language(lang_module.language())
    parser = Parser(language)
    return parser


def _get_node_text(node: Node, source: bytes) -> str:
    """Extract the text of a node from source bytes."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


# ─── Python Extractor ──────────────────────────────────────────────────────────

def _line_num(node: Node) -> int:
    """Get 1-indexed line number from a Tree-sitter node."""
    return node.start_point[0] + 1


def _extract_python(tree, source: bytes) -> List[str]:
    """Extract structural skeleton from a Python AST."""
    lines = []
    root = tree.root_node

    # Pass 1: Collect imports
    imports = []
    for child in root.children:
        if child.type in ("import_statement", "import_from_statement"):
            imports.append(_get_node_text(child, source).strip())

    if imports:
        # Compress imports into a single summary line
        lines.append("imports: " + "; ".join(imports))
        lines.append("")

    # Pass 2: Collect top-level assignments (constants/configs)
    for child in root.children:
        if child.type == "expression_statement":
            expr = child.children[0] if child.children else None
            if expr and expr.type == "assignment":
                target = _get_node_text(expr.children[0], source).strip()
                ln = _line_num(child)
                lines.append(f"L{ln}: {target} = ...")

    # Pass 3: Collect top-level functions and classes
    for child in root.children:
        if child.type == "function_definition":
            lines.append("")
            lines.append(_extract_python_function(child, source, indent=0))
        elif child.type == "decorated_definition":
            # Handle decorated functions/classes
            for sub in child.children:
                if sub.type == "function_definition":
                    decorator_text = []
                    for d in child.children:
                        if d.type == "decorator":
                            decorator_text.append(f"L{_line_num(d)}: {_get_node_text(d, source).strip()}")
                    lines.append("")
                    for dt in decorator_text:
                        lines.append(dt)
                    lines.append(_extract_python_function(sub, source, indent=0))
                elif sub.type == "class_definition":
                    decorator_text = []
                    for d in child.children:
                        if d.type == "decorator":
                            decorator_text.append(f"L{_line_num(d)}: {_get_node_text(d, source).strip()}")
                    lines.append("")
                    for dt in decorator_text:
                        lines.append(dt)
                    lines.extend(_extract_python_class(sub, source))
        elif child.type == "class_definition":
            lines.append("")
            lines.extend(_extract_python_class(child, source))

    return lines


def _extract_python_function(node: Node, source: bytes, indent: int = 0) -> str:
    """Extract a function signature (no body) with line number."""
    prefix = "    " * indent
    name = ""
    params = ""
    return_type = ""
    ln = _line_num(node)

    for child in node.children:
        if child.type == "identifier":
            name = _get_node_text(child, source)
        elif child.type == "parameters":
            params = _get_node_text(child, source)
        elif child.type == "type":
            return_type = f" -> {_get_node_text(child, source)}"

    return f"{prefix}L{ln}: def {name}{params}{return_type}"


def _extract_python_class(node: Node, source: bytes) -> List[str]:
    """Extract a class definition with its method signatures."""
    lines = []
    class_name = ""
    superclasses = ""
    docstring = ""
    ln = _line_num(node)

    for child in node.children:
        if child.type == "identifier":
            class_name = _get_node_text(child, source)
        elif child.type == "argument_list":
            superclasses = _get_node_text(child, source)

    class_line = f"L{ln}: class {class_name}"
    if superclasses:
        class_line += superclasses
    class_line += ":"
    lines.append(class_line)

    # Walk class body for methods and class-level docstring
    body = None
    for child in node.children:
        if child.type == "block":
            body = child
            break

    if body:
        for i, child in enumerate(body.children):
            # Get class docstring (first expression statement with a string)
            if i == 0 and child.type == "expression_statement":
                expr = child.children[0] if child.children else None
                if expr and expr.type == "string":
                    docstring = _get_node_text(expr, source).strip()
                    lines.append(f"    {docstring}")

            if child.type == "function_definition":
                lines.append(_extract_python_function(child, source, indent=1))
            elif child.type == "decorated_definition":
                for sub in child.children:
                    if sub.type == "decorator":
                        lines.append(f"    {_get_node_text(sub, source).strip()}")
                    elif sub.type == "function_definition":
                        lines.append(_extract_python_function(sub, source, indent=1))

    return lines


# ─── JavaScript/TypeScript Extractor ───────────────────────────────────────────

def _extract_js(tree, source: bytes) -> List[str]:
    """Extract structural skeleton from JavaScript/TypeScript AST."""
    lines = []
    root = tree.root_node

    for child in root.children:
        if child.type in ("import_statement",):
            lines.append(f"L{_line_num(child)}: {_get_node_text(child, source).strip()}")
        elif child.type == "function_declaration":
            lines.append(_extract_js_function(child, source))
        elif child.type == "class_declaration":
            lines.extend(_extract_js_class(child, source))
        elif child.type in ("export_statement",):
            for sub in child.children:
                if sub.type == "function_declaration":
                    lines.append("export " + _extract_js_function(sub, source))
                elif sub.type == "class_declaration":
                    cls_lines = _extract_js_class(sub, source)
                    if cls_lines:
                        cls_lines[0] = "export " + cls_lines[0]
                    lines.extend(cls_lines)
                elif sub.type == "lexical_declaration":
                    lines.append("export " + _extract_js_variable(sub, source))
        elif child.type == "lexical_declaration":
            lines.append(_extract_js_variable(child, source))

    return lines


def _extract_js_function(node: Node, source: bytes) -> str:
    """Extract a JS function signature with line number."""
    name = ""
    params = ""
    ln = _line_num(node)
    for child in node.children:
        if child.type == "identifier":
            name = _get_node_text(child, source)
        elif child.type == "formal_parameters":
            params = _get_node_text(child, source)
    return f"L{ln}: function {name}{params}"


def _extract_js_class(node: Node, source: bytes) -> List[str]:
    """Extract a JS class with method signatures and line numbers."""
    lines = []
    class_name = ""
    ln = _line_num(node)
    for child in node.children:
        if child.type == "identifier":
            class_name = _get_node_text(child, source)
    lines.append(f"L{ln}: class {class_name}:")

    body = None
    for child in node.children:
        if child.type == "class_body":
            body = child
            break

    if body:
        for child in body.children:
            if child.type == "method_definition":
                name = ""
                params = ""
                mln = _line_num(child)
                for sub in child.children:
                    if sub.type == "property_identifier":
                        name = _get_node_text(sub, source)
                    elif sub.type == "formal_parameters":
                        params = _get_node_text(sub, source)
                lines.append(f"    L{mln}: {name}{params}")

    return lines


def _extract_js_variable(node: Node, source: bytes) -> str:
    """Extract a top-level variable/const declaration with line number."""
    ln = _line_num(node)
    text = _get_node_text(node, source).strip()
    # Truncate the value — just show the declaration name
    if "=" in text:
        left = text.split("=")[0].strip()
        return f"L{ln}: {left} = ..."
    return f"L{ln}: {text}"


# ─── Java Extractor ────────────────────────────────────────────────────────────

def _extract_java(tree, source: bytes) -> List[str]:
    """Extract structural skeleton from Java AST."""
    lines = []
    root = tree.root_node

    for child in root.children:
        if child.type == "package_declaration":
            lines.append(_get_node_text(child, source).strip())
        elif child.type == "import_declaration":
            lines.append(_get_node_text(child, source).strip())
        elif child.type == "class_declaration":
            lines.extend(_extract_java_class(child, source))

    return lines


def _extract_java_class(node: Node, source: bytes) -> List[str]:
    """Extract a Java class with method signatures."""
    lines = []
    class_header_parts = []

    for child in node.children:
        if child.type in ("modifiers",):
            class_header_parts.append(_get_node_text(child, source))
        elif child.type == "identifier":
            class_header_parts.append(f"class {_get_node_text(child, source)}")
        elif child.type == "superclass":
            class_header_parts.append(_get_node_text(child, source))

    lines.append(f"L{_line_num(node)}: " + " ".join(class_header_parts) + ":")

    body = None
    for child in node.children:
        if child.type == "class_body":
            body = child
            break

    if body:
        for child in body.children:
            if child.type == "method_declaration":
                sig_parts = []
                for sub in child.children:
                    if sub.type in ("modifiers",):
                        sig_parts.append(_get_node_text(sub, source))
                    elif sub.type in ("void_type", "type_identifier", "integral_type",
                                      "boolean_type", "floating_point_type", "generic_type",
                                      "array_type"):
                        sig_parts.append(_get_node_text(sub, source))
                    elif sub.type == "identifier":
                        sig_parts.append(_get_node_text(sub, source))
                    elif sub.type == "formal_parameters":
                        sig_parts.append(_get_node_text(sub, source))
                lines.append(f"    L{_line_num(child)}: " + " ".join(sig_parts))
            elif child.type == "constructor_declaration":
                sig_parts = []
                for sub in child.children:
                    if sub.type in ("modifiers",):
                        sig_parts.append(_get_node_text(sub, source))
                    elif sub.type == "identifier":
                        sig_parts.append(_get_node_text(sub, source))
                    elif sub.type == "formal_parameters":
                        sig_parts.append(_get_node_text(sub, source))
                lines.append("    " + " ".join(sig_parts))

    return lines


# ─── Dispatcher ────────────────────────────────────────────────────────────────

EXTRACTORS = {
    "python": _extract_python,
    "javascript": _extract_js,
    "typescript": _extract_js,  # TS shares structural similarities with JS
    "java": _extract_java,
}


def map_file(filepath: str) -> Optional[str]:
    """
    Generate a compressed skeleton for a single file.
    Returns None if the file type is unsupported.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    parser = _get_parser(ext)
    if parser is None:
        return None

    lang_name = LANGUAGE_MAP[ext][0]
    extractor = EXTRACTORS.get(lang_name)
    if extractor is None:
        return None

    try:
        source = path.read_bytes()
    except (OSError, IOError):
        return None

    tree = parser.parse(source)
    lines = extractor(tree, source)

    if not lines:
        return None

    return "\n".join(lines)


def map_directory(directory: str, extensions: Optional[List[str]] = None) -> Dict[str, str]:
    """
    Walk a directory and generate skeletons for all supported files.
    Returns a dict of {relative_path: skeleton_text}.
    """
    root = Path(directory).resolve()
    results: Dict[str, str] = {}

    if extensions is None:
        extensions = list(LANGUAGE_MAP.keys())

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORE_PATTERNS
                       and not d.startswith(".")]

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()

            if ext in IGNORE_EXTENSIONS:
                continue
            if ext not in extensions:
                continue

            skeleton = map_file(str(fpath))
            if skeleton:
                rel_path = str(fpath.relative_to(root)).replace("\\", "/")
                results[rel_path] = skeleton

    return results


def format_map_output(skeletons: Dict[str, str]) -> str:
    """Format all skeletons into a single markdown document."""
    if not skeletons:
        return "# Codebase Map\n\n_No supported source files found._\n"

    sections = []
    sections.append("# Codebase Map")
    sections.append(f"_Generated by `ctx map` — {len(skeletons)} file(s) indexed._\n")

    for filepath, skeleton in skeletons.items():
        sections.append(f"## {filepath}")
        sections.append("```")
        sections.append(skeleton)
        sections.append("```")
        sections.append("")

    return "\n".join(sections)

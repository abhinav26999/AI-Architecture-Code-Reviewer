import os
import logging
from typing import List, Dict, Any, Optional, Tuple
import tree_sitter
import tree_sitter_python
import tree_sitter_typescript
from app.schemas.parser import (
    ParsedFile,
    ImportMetadata,
    ImportSymbol,
    ClassMetadata,
    FunctionMetadata
)

logger = logging.getLogger(__name__)


class ASTParser:
    def __init__(self):
        # Load Tree-sitter languages
        try:
            self.py_lang = tree_sitter.Language(tree_sitter_python.language())
            self.ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            self.tsx_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
            
            # Map extensions to languages
            self.lang_map = {
                ".py": self.py_lang,
                ".js": self.tsx_lang,   # Use TSX parser for JS/JSX as it is fully compatible
                ".jsx": self.tsx_lang,
                ".ts": self.ts_lang,
                ".tsx": self.tsx_lang,
                ".mjs": self.tsx_lang,
                ".cjs": self.tsx_lang
            }
        except Exception as e:
            logger.error(f"Failed to load Tree-sitter languages: {e}")
            raise

    def get_language_for_extension(self, ext: str) -> Optional[tree_sitter.Language]:
        return self.lang_map.get(ext.lower())

    def _get_node_text(self, node: tree_sitter.Node, code_bytes: bytes) -> str:
        """Helper to get node text decoded as UTF-8."""
        return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

    def parse_code(self, code: str, filename: str) -> ParsedFile:
        """Parses a code string based on its file extension and returns ParsedFile metadata."""
        ext = os.path.splitext(filename)[1]
        lang = self.get_language_for_extension(ext)
        
        if not lang:
            logger.info(f"ASTParser: Extension '{ext}' is not supported by Tree-sitter. Returning raw parsed metadata container.")
            return ParsedFile(
                file_path=filename,
                language="other",
                imports=[],
                classes=[],
                functions=[]
            )

        logger.info(f"ASTParser: Parsing file '{filename}' with extension '{ext}'")

        code_bytes = code.encode("utf-8")
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(code_bytes)
        
        imports: List[ImportMetadata] = []
        classes: List[ClassMetadata] = []
        functions: List[FunctionMetadata] = []

        # Detect lang name
        lang_name = "python" if ext.lower() == ".py" else "typescript"

        try:
            if lang_name == "python":
                self._extract_python_metadata(tree.root_node, code_bytes, imports, classes, functions)
            else:
                self._extract_typescript_metadata(tree.root_node, code_bytes, imports, classes, functions)
        except Exception as e:
            logger.exception(f"Error parsing metadata for {filename}")
            raise ValueError(f"AST traversal failed: {str(e)}")

        logger.info(f"ASTParser: Parsed '{filename}' -> Found {len(imports)} imports, {len(classes)} classes, {len(functions)} functions.")

        return ParsedFile(
            file_path=filename,
            language=lang_name,
            imports=imports,
            classes=classes,
            functions=functions
        )

    # ==========================================
    # PYTHON METADATA EXTRACTION
    # ==========================================

    def _extract_python_metadata(
        self,
        node: tree_sitter.Node,
        code_bytes: bytes,
        imports: List[ImportMetadata],
        classes: List[ClassMetadata],
        functions: List[FunctionMetadata]
    ):
        """Recursively parses a Python AST tree to populate metadata collections."""
        
        # Helper to process child nodes
        def recurse_children(parent_node):
            for child in parent_node.children:
                self._extract_python_metadata(child, code_bytes, imports, classes, functions)

        # 1. Handle Imports
        if node.type == "import_statement":
            # Example: import sys, os
            line = node.start_point[0] + 1
            for child in node.children:
                if child.type == "dotted_name":
                    src = self._get_node_text(child, code_bytes)
                    imports.append(ImportMetadata(source=src, line=line))
                elif child.type == "aliased_import":
                    # import sys as s
                    dotted = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if dotted and alias_node:
                        src = self._get_node_text(dotted, code_bytes)
                        alias = self._get_node_text(alias_node, code_bytes)
                        imports.append(ImportMetadata(source=src, alias=alias, line=line))
            return  # No need to traverse imports children

        elif node.type == "import_from_statement":
            # Example: from x import y, z
            line = node.start_point[0] + 1
            module_node = node.child_by_field_name("module_name")
            if module_node:
                source = self._get_node_text(module_node, code_bytes)
                symbols = []
                
                # Look for imported names
                for sibling in node.children:
                    if sibling.type in ("dotted_name", "aliased_import", "import_list"):
                        self._collect_python_import_symbols(sibling, code_bytes, symbols)
                
                imports.append(ImportMetadata(source=source, symbols=symbols, line=line))
            return

        # 2. Handle Classes
        elif node.type == "class_definition":
            cls_name_node = node.child_by_field_name("name")
            if cls_name_node:
                cls_name = self._get_node_text(cls_name_node, code_bytes)
                
                # Extracted base classes
                bases = []
                arg_list = node.child_by_field_name("superclasses")
                if arg_list:
                    for arg in arg_list.children:
                        if arg.type in ("identifier", "attribute"):
                            bases.append(self._get_node_text(arg, code_bytes))

                # Walk class body to find methods
                methods: List[FunctionMetadata] = []
                body = node.child_by_field_name("body")
                if body:
                    # Parse only function_definitions nested directly or indirectly inside class body
                    self._collect_python_class_methods(body, code_bytes, methods)
                
                classes.append(ClassMetadata(
                    name=cls_name,
                    bases=bases,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    methods=methods
                ))
            return  # The class's internal methods are already collected, so we bypass recursion

        # 3. Handle Top-Level Functions (functions outside classes)
        elif node.type == "function_definition":
            fn_meta = self._parse_python_function(node, code_bytes)
            if fn_meta:
                functions.append(fn_meta)
            return  # Bypassing inner recursion, calls are collected inside _parse_python_function

        # Default fallback: keep traversing down
        recurse_children(node)

    def _collect_python_import_symbols(self, node: tree_sitter.Node, code_bytes: bytes, symbols: List[ImportSymbol]):
        if node.type == "import_list":
            for child in node.children:
                self._collect_python_import_symbols(child, code_bytes, symbols)
        elif node.type == "dotted_name":
            symbols.append(ImportSymbol(name=self._get_node_text(node, code_bytes)))
        elif node.type == "aliased_import":
            name_node = node.child_by_field_name("name")
            alias_node = node.child_by_field_name("alias")
            if name_node and alias_node:
                symbols.append(ImportSymbol(
                    name=self._get_node_text(name_node, code_bytes),
                    alias=self._get_node_text(alias_node, code_bytes)
                ))

    def _collect_python_class_methods(self, node: tree_sitter.Node, code_bytes: bytes, methods: List[FunctionMetadata]):
        if node.type == "function_definition":
            fn = self._parse_python_function(node, code_bytes)
            if fn:
                methods.append(fn)
            return
        
        for child in node.children:
            self._collect_python_class_methods(child, code_bytes, methods)

    def _parse_python_function(self, node: tree_sitter.Node, code_bytes: bytes) -> Optional[FunctionMetadata]:
        fn_name_node = node.child_by_field_name("name")
        if not fn_name_node:
            return None

        fn_name = self._get_node_text(fn_name_node, code_bytes)
        
        # Check if function is async (python wraps function_definition in decorated_definition or has async prefix)
        is_async = False
        # Tree-sitter python includes 'async' token as child
        for child in node.children:
            if child.type == "async":
                is_async = True

        # Extract parameters
        parameters = []
        param_list = node.child_by_field_name("parameters")
        if param_list:
            for param in param_list.children:
                # parameter types: identifier, typed_parameter, default_parameter
                if param.type in ("identifier", "typed_parameter", "default_parameter"):
                    # For simplicity, extract the main parameter name
                    if param.type == "typed_parameter":
                        name_node = param.child_by_field_name("name")
                    elif param.type == "default_parameter":
                        name_node = param.child_by_field_name("name")
                    else:
                        name_node = param
                    
                    if name_node:
                        parameters.append(self._get_node_text(name_node, code_bytes))

        # Extract function calls inside function body
        calls = []
        body = node.child_by_field_name("body")
        if body:
            self._collect_python_calls(body, code_bytes, calls)

        return FunctionMetadata(
            name=fn_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parameters=parameters,
            calls=calls,
            is_async=is_async
        )

    def _collect_python_calls(self, node: tree_sitter.Node, code_bytes: bytes, calls: List[str]):
        """Finds all call nodes and appends the function names/expression to calls."""
        if node.type == "call":
            function_node = node.child_by_field_name("function")
            if function_node:
                calls.append(self._get_node_text(function_node, code_bytes))
        
        for child in node.children:
            self._collect_python_calls(child, code_bytes, calls)

    # ==========================================
    # TYPESCRIPT/JAVASCRIPT METADATA EXTRACTION
    # ==========================================

    def _extract_typescript_metadata(
        self,
        node: tree_sitter.Node,
        code_bytes: bytes,
        imports: List[ImportMetadata],
        classes: List[ClassMetadata],
        functions: List[FunctionMetadata]
    ):
        """Recursively parses a TypeScript/JavaScript AST tree to populate metadata collections."""
        
        def recurse_children(parent_node):
            for child in parent_node.children:
                self._extract_typescript_metadata(child, code_bytes, imports, classes, functions)

        # 1. Handle Imports
        if node.type == "import_statement":
            # Example: import { A, B } from './module';
            line = node.start_point[0] + 1
            source_node = node.child_by_field_name("source")
            if source_node:
                # Strip quotes around module path
                source = self._get_node_text(source_node, code_bytes).strip("\"'")
                
                symbols = []
                clause = None
                for child in node.children:
                    if child.type in ("import_clause", "named_imports"):
                        clause = child
                        break
                if clause:
                    # Check for named imports: import { x } from ...
                    self._collect_ts_import_symbols(clause, code_bytes, symbols)

                imports.append(ImportMetadata(source=source, symbols=symbols, line=line))
            return

        # Handle require calls: const x = require('y')
        elif node.type == "lexical_declaration" or node.type == "variable_declaration":
            # Scan for 'require' call inside variable assignments
            line = node.start_point[0] + 1
            self._check_and_extract_ts_require(node, code_bytes, imports, line)
            recurse_children(node)
            return

        # 2. Handle Classes
        elif node.type == "class_declaration":
            cls_name_node = node.child_by_field_name("name")
            if cls_name_node:
                cls_name = self._get_node_text(cls_name_node, code_bytes)
                
                # Check heritage (bases/extends)
                bases = []
                # Find Heritage Clause (e.g. extends BaseClass implements Interface)
                for child in node.children:
                    if child.type == "class_heritage":
                        for h_child in child.children:
                            if h_child.type == "extends_clause":
                                for ec_child in h_child.children:
                                    if ec_child.type in ("identifier", "type_identifier", "nested_identifier"):
                                        bases.append(self._get_node_text(ec_child, code_bytes))

                # Walk class body to find methods
                methods: List[FunctionMetadata] = []
                body = node.child_by_field_name("body")
                if body:
                    self._collect_ts_class_methods(body, code_bytes, methods)

                classes.append(ClassMetadata(
                    name=cls_name,
                    bases=bases,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    methods=methods
                ))
            return

        # 3. Handle Functions
        elif node.type in ("function_declaration", "generator_function_declaration"):
            fn_meta = self._parse_ts_function(node, code_bytes)
            if fn_meta:
                functions.append(fn_meta)
            return

        # Default fallback
        recurse_children(node)

    def _collect_ts_import_symbols(self, node: tree_sitter.Node, code_bytes: bytes, symbols: List[ImportSymbol]):
        if node.type == "named_imports":
            for child in node.children:
                if child.type == "import_specifier":
                    identifiers = [c for c in child.children if c.type in ("identifier", "type_identifier")]
                    if len(identifiers) == 1:
                        symbols.append(ImportSymbol(name=self._get_node_text(identifiers[0], code_bytes)))
                    elif len(identifiers) == 2:
                        symbols.append(ImportSymbol(
                            name=self._get_node_text(identifiers[0], code_bytes),
                            alias=self._get_node_text(identifiers[1], code_bytes)
                        ))
        elif node.type == "namespace_import":
            # import * as x from ...
            for child in node.children:
                if child.type == "identifier":
                    symbols.append(ImportSymbol(name=self._get_node_text(child, code_bytes), alias="*"))
        elif node.type == "identifier":
            # Default import: import x from ...
            symbols.append(ImportSymbol(name=self._get_node_text(node, code_bytes), alias="default"))
        else:
            for child in node.children:
                self._collect_ts_import_symbols(child, code_bytes, symbols)

    def _check_and_extract_ts_require(self, node: tree_sitter.Node, code_bytes: bytes, imports: List[ImportMetadata], line: int):
        """Checks if a variable declaration is a CommonJS require call and extracts it."""
        if node.type == "call_expression":
            function_node = node.child_by_field_name("function")
            if function_node and self._get_node_text(function_node, code_bytes) == "require":
                arguments = node.child_by_field_name("arguments")
                if arguments and len(arguments.children) >= 2: # arguments includes '(' and ')'
                    arg_val_node = arguments.children[1] # first actual arg
                    if arg_val_node.type == "string":
                        source = self._get_node_text(arg_val_node, code_bytes).strip("\"'")
                        imports.append(ImportMetadata(source=source, line=line, alias="require"))
            return

        for child in node.children:
            self._check_and_extract_ts_require(child, code_bytes, imports, line)

    def _collect_ts_class_methods(self, node: tree_sitter.Node, code_bytes: bytes, methods: List[FunctionMetadata]):
        if node.type == "method_definition":
            fn = self._parse_ts_function(node, code_bytes)
            if fn:
                methods.append(fn)
            return

        for child in node.children:
            self._collect_ts_class_methods(child, code_bytes, methods)

    def _parse_ts_function(self, node: tree_sitter.Node, code_bytes: bytes) -> Optional[FunctionMetadata]:
        fn_name_node = node.child_by_field_name("name")
        if not fn_name_node:
            return None

        fn_name = self._get_node_text(fn_name_node, code_bytes)
        
        # Check if function has 'async' modifier
        is_async = False
        for child in node.children:
            if child.type == "async": # or modifier containing async
                is_async = True

        # Extract parameters
        parameters = []
        param_list = node.child_by_field_name("parameters")
        if param_list:
            for param in param_list.children:
                # TS parameter can be identifier, required_parameter, optional_parameter, assignment_pattern
                if param.type in ("identifier", "required_parameter", "optional_parameter", "formal_parameter"):
                    # Find parameter name
                    name_node = param
                    if param.type == "required_parameter" or param.type == "optional_parameter":
                        name_node = param.child_by_field_name("pattern")
                    elif param.type == "formal_parameter":
                        # extracts name from pattern child if present
                        name_node = param.children[0]
                    
                    if name_node:
                        parameters.append(self._get_node_text(name_node, code_bytes))

        # Extract function calls inside function body
        calls = []
        body = node.child_by_field_name("body")
        if body:
            self._collect_ts_calls(body, code_bytes, calls)

        return FunctionMetadata(
            name=fn_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parameters=parameters,
            calls=calls,
            is_async=is_async
        )

    def _collect_ts_calls(self, node: tree_sitter.Node, code_bytes: bytes, calls: List[str]):
        """Finds all call expression nodes and appends names/expressions to calls."""
        if node.type == "call_expression":
            function_node = node.child_by_field_name("function")
            if function_node:
                calls.append(self._get_node_text(function_node, code_bytes))
        
        for child in node.children:
            self._collect_ts_calls(child, code_bytes, calls)


# Singleton instance
ast_parser = ASTParser()

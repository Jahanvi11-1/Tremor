"""
Dart/Flutter parser using tree-sitter.
Handles .dart files.
"""

from pathlib import Path
from typing import Optional, List, Set

try:
    from tree_sitter_languages import get_parser
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

from .base import LanguageParser, FunctionInfo, ModuleInfo


class DartParser(LanguageParser):
    """Parse Dart/Flutter files using tree-sitter."""
    
    def __init__(self, repo_path: str):
        super().__init__(repo_path)
        
        if not HAS_TREE_SITTER:
            raise ImportError(
                "tree-sitter-languages not installed. "
                "Run: pip install tree-sitter-languages"
            )
        
        try:
            self.parser = get_parser('dart')
        except Exception as e:
            print(f"Warning: Could not load Dart grammar: {e}")
            print("Dart parsing will be limited")
            self.parser = None
    
    def get_file_extensions(self) -> List[str]:
        return ['.dart']
    
    def get_language_name(self) -> str:
        return 'dart'
    
    def parse_file(self, file_path: Path) -> Optional[ModuleInfo]:
        """Parse a single Dart file."""
        if not self.parser:
            # Fallback: basic parsing
            return self._basic_parse(file_path)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        source_bytes = bytes(source_code, 'utf-8')
        tree = self.parser.parse(source_bytes)
        root_node = tree.root_node
        
        # Create module info
        relative_path = str(file_path.relative_to(self.repo_path))
        module_name = file_path.stem
        
        module = ModuleInfo(
            path=relative_path,
            name=module_name,
            language='dart'
        )
        
        # Extract imports
        module.imports = self._extract_imports(root_node, source_bytes)
        
        # Extract functions and methods
        module.functions = self._extract_functions(root_node, source_bytes, relative_path)
        
        # Extract class names for metadata
        classes = self._extract_classes(root_node, source_bytes)
        if classes:
            module.metadata['classes'] = classes
        
        return module
    
    def _basic_parse(self, file_path: Path) -> ModuleInfo:
        """
        Basic regex-based parsing when tree-sitter is not available.
        Limited functionality but better than nothing.
        """
        import re
        
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        relative_path = str(file_path.relative_to(self.repo_path))
        module_name = file_path.stem
        
        module = ModuleInfo(
            path=relative_path,
            name=module_name,
            language='dart'
        )
        
        # Extract imports: import 'package:foo/bar.dart';
        import_pattern = r"import\s+['\"]([^'\"]+)['\"]"
        imports = re.findall(import_pattern, source_code)
        module.imports = set(imports)
        
        # Extract functions: returnType functionName(params) {
        func_pattern = r"(?:^|\n)\s*(?:Future<\w+>|\w+)\s+(\w+)\s*\([^)]*\)\s*(?:async\s*)?\{"
        
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            match = re.search(func_pattern, line)
            if match:
                func_name = match.group(1)
                # Skip keywords
                if func_name in ['if', 'for', 'while', 'switch']:
                    continue
                
                is_test = func_name.startswith('test') or '_test.dart' in relative_path
                
                func_info = FunctionInfo(
                    name=func_name,
                    module_path=relative_path,
                    start_line=i + 1,
                    end_line=i + 1,  # Approximate
                    language='dart',
                    is_test=is_test,
                    calls=set()  # Cannot extract reliably with regex
                )
                module.functions.append(func_info)
        
        return module
    
    def _extract_imports(self, node, source_bytes: bytes) -> Set[str]:
        """Extract import statements."""
        imports = set()
        
        def traverse(n):
            if n.type == 'import_or_export':
                # import 'package:foo/bar.dart';
                for child in n.children:
                    if child.type == 'configurable_uri':
                        for uri_child in child.children:
                            if uri_child.type == 'uri':
                                import_path = source_bytes[uri_child.start_byte:uri_child.end_byte].decode('utf-8')
                                import_path = import_path.strip('\'"')
                                imports.add(import_path)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return imports
    
    def _extract_functions(
        self,
        node,
        source_bytes: bytes,
        module_path: str
    ) -> List[FunctionInfo]:
        """Extract functions and methods."""
        functions = []
        
        def traverse(n):
            # Top-level functions
            if n.type == 'function_signature':
                parent = n.parent
                if parent and parent.type == 'function_declaration':
                    func_info = self._create_function_info(parent, source_bytes, module_path)
                    if func_info:
                        functions.append(func_info)
            
            # Methods in classes
            elif n.type == 'method_signature':
                parent = n.parent
                if parent and parent.type == 'method_declaration':
                    func_info = self._create_method_info(parent, source_bytes, module_path)
                    if func_info:
                        functions.append(func_info)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return functions
    
    def _create_function_info(
        self,
        node,
        source_bytes: bytes,
        module_path: str
    ) -> Optional[FunctionInfo]:
        """Create FunctionInfo from function_declaration node."""
        # Get function signature
        signature = node.child_by_field_name('signature')
        if not signature:
            return None
        
        name_node = signature.child_by_field_name('name')
        if not name_node:
            return None
        
        func_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        is_test = func_name.startswith('test') or '_test.dart' in module_path
        
        calls = self._extract_calls_from_node(node, source_bytes)
        
        # Extract parameters
        params_node = signature.child_by_field_name('parameters')
        parameters = self._extract_parameters(params_node, source_bytes) if params_node else []
        
        # Extract return type
        return_type_node = signature.child_by_field_name('return_type')
        return_type = None
        if return_type_node:
            return_type = source_bytes[return_type_node.start_byte:return_type_node.end_byte].decode('utf-8')
        
        return FunctionInfo(
            name=func_name,
            module_path=module_path,
            start_line=start_line,
            end_line=end_line,
            language='dart',
            is_test=is_test,
            calls=calls,
            parameters=parameters,
            return_type=return_type
        )
    
    def _create_method_info(
        self,
        node,
        source_bytes: bytes,
        module_path: str
    ) -> Optional[FunctionInfo]:
        """Create FunctionInfo from method_declaration node."""
        signature = node.child_by_field_name('signature')
        if not signature:
            return None
        
        name_node = signature.child_by_field_name('name')
        if not name_node:
            return None
        
        method_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        is_test = method_name.startswith('test') or '_test.dart' in module_path
        
        calls = self._extract_calls_from_node(node, source_bytes)
        
        params_node = signature.child_by_field_name('parameters')
        parameters = self._extract_parameters(params_node, source_bytes) if params_node else []
        
        return FunctionInfo(
            name=method_name,
            module_path=module_path,
            start_line=start_line,
            end_line=end_line,
            language='dart',
            is_test=is_test,
            calls=calls,
            parameters=parameters
        )
    
    def _extract_calls_from_node(self, node, source_bytes: bytes) -> Set[str]:
        """Extract function/method calls."""
        calls = set()
        
        def traverse(n):
            # foo()
            if n.type == 'function_expression_body' or n.type == 'function_body':
                for child in n.children:
                    if child.type == 'identifier':
                        call_name = source_bytes[child.start_byte:child.end_byte].decode('utf-8')
                        # Filter out keywords
                        if call_name not in ['if', 'for', 'while', 'return', 'var', 'final']:
                            calls.add(call_name)
            
            # obj.method()
            elif n.type == 'method_invocation':
                method_node = n.child_by_field_name('method')
                if method_node:
                    call_name = source_bytes[method_node.start_byte:method_node.end_byte].decode('utf-8')
                    calls.add(call_name)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return calls
    
    def _extract_parameters(self, params_node, source_bytes: bytes) -> List[str]:
        """Extract parameter names."""
        parameters = []
        
        def traverse(n):
            if n.type == 'formal_parameter':
                # Find identifier
                for child in n.children:
                    if child.type == 'identifier':
                        param_name = source_bytes[child.start_byte:child.end_byte].decode('utf-8')
                        parameters.append(param_name)
                        break
            
            for child in n.children:
                traverse(child)
        
        traverse(params_node)
        return parameters
    
    def _extract_classes(self, node, source_bytes: bytes) -> List[str]:
        """Extract class names for metadata."""
        classes = []
        
        def traverse(n):
            if n.type == 'class_declaration':
                name_node = n.child_by_field_name('name')
                if name_node:
                    class_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
                    classes.append(class_name)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return classes

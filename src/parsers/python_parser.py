"""
Python parser using AST.
Refactored from original parser.py to implement LanguageParser interface.
"""

import ast
from pathlib import Path
from typing import Optional, List, Set

from .base import LanguageParser, FunctionInfo, ModuleInfo


class PythonParser(LanguageParser):
    """Parse Python source code using built-in AST."""
    
    def get_file_extensions(self) -> List[str]:
        return ['.py']
    
    def get_language_name(self) -> str:
        return 'python'
    
    def parse_file(self, file_path: Path) -> Optional[ModuleInfo]:
        """Parse a single Python file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            raise ValueError(f"Syntax error: {e}")
        
        # Create module info
        relative_path = str(file_path.relative_to(self.repo_path))
        module_name = file_path.stem
        
        module = ModuleInfo(
            path=relative_path,
            name=module_name,
            language='python'
        )
        
        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module.imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module.imports.add(node.module)
        
        # Extract functions and methods
        module.functions = self._extract_functions(tree, relative_path)
        
        # Store class information in metadata
        classes = self._extract_classes(tree)
        if classes:
            module.metadata['classes'] = classes
        
        return module
    
    def _extract_functions(self, tree: ast.AST, module_path: str) -> List[FunctionInfo]:
        """Extract all functions and methods from AST."""
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = self._create_function_info(node, module_path)
                functions.append(func_info)
        
        return functions
    
    def _create_function_info(
        self, 
        node: ast.FunctionDef, 
        module_path: str
    ) -> FunctionInfo:
        """Create FunctionInfo from AST FunctionDef node."""
        func_name = node.name
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        
        # Detect test functions
        is_test = (
            func_name.startswith('test_') or 
            '/test' in module_path or
            'test/' in module_path
        )
        
        # Extract function calls
        calls = self._extract_calls(node)
        
        # Extract parameters
        parameters = [arg.arg for arg in node.args.args]
        
        # Extract return type annotation if present
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)
        
        return FunctionInfo(
            name=func_name,
            module_path=module_path,
            start_line=start_line,
            end_line=end_line,
            language='python',
            is_test=is_test,
            calls=calls,
            parameters=parameters,
            return_type=return_type
        )
    
    def _extract_calls(self, node: ast.FunctionDef) -> Set[str]:
        """Extract function calls within a function."""
        calls = set()
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child.func)
                if call_name:
                    calls.add(call_name)
        
        return calls
    
    def _get_call_name(self, node: ast.expr) -> Optional[str]:
        """
        Extract function name from a Call node.
        
        Handles:
        - Simple calls: foo()
        - Attribute calls: obj.method()
        - Nested attributes: obj.attr.method()
        
        Does NOT handle:
        - Dynamic calls: getattr(obj, name)()
        - Lambda/function returns: get_func()()
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # For obj.method(), return 'method'
            return node.attr
        elif isinstance(node, ast.Call):
            # Nested call: skip
            return None
        return None
    
    def _extract_classes(self, tree: ast.AST) -> List[str]:
        """Extract class names for metadata."""
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
        
        return classes

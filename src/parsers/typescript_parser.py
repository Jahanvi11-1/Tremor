"""
TypeScript/JavaScript parser using tree-sitter.
Handles .ts, .tsx, .js, .jsx files.
"""

from pathlib import Path
from typing import Optional, List, Set

try:
    import tree_sitter_languages
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

from .base import LanguageParser, FunctionInfo, ModuleInfo


class TypeScriptParser(LanguageParser):
    """Parse TypeScript and JavaScript files using tree-sitter."""
    
    def __init__(self, repo_path: str):
        super().__init__(repo_path)
        
        if not HAS_TREE_SITTER:
            raise ImportError(
                "tree_sitter_languages not installed or unavailable for this Python version. "
                "TypeScript parsing will not work."
            )
        
        # Load TypeScript grammar (handles both TS and JS)
        self.parser = tree_sitter_languages.get_parser('typescript')
    
    def get_file_extensions(self) -> List[str]:
        return ['.ts', '.tsx', '.js', '.jsx']
    
    def get_language_name(self) -> str:
        return 'typescript'
    
    def parse_file(self, file_path: Path) -> Optional[ModuleInfo]:
        """Parse a single TypeScript/JavaScript file."""
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
            language='typescript'
        )
        
        # Extract imports
        module.imports = self._extract_imports(root_node, source_bytes)
        
        # Extract functions
        module.functions = self._extract_functions(root_node, source_bytes, relative_path)
        
        # Extract exports for metadata
        exports = self._extract_exports(root_node, source_bytes)
        if exports:
            module.metadata['exports'] = exports
        
        return module
    
    def _extract_imports(self, node, source_bytes: bytes) -> Set[str]:
        """Extract import statements."""
        imports = set()
        
        def traverse(n):
            # import foo from 'bar'
            if n.type == 'import_statement':
                for child in n.children:
                    if child.type == 'string':
                        # Remove quotes
                        import_path = source_bytes[child.start_byte:child.end_byte].decode('utf-8')
                        import_path = import_path.strip('\'"')
                        imports.add(import_path)
            
            # require('foo')
            elif n.type == 'call_expression':
                callee = n.child_by_field_name('function')
                if callee and source_bytes[callee.start_byte:callee.end_byte].decode('utf-8') == 'require':
                    args = n.child_by_field_name('arguments')
                    if args:
                        for arg in args.children:
                            if arg.type == 'string':
                                import_path = source_bytes[arg.start_byte:arg.end_byte].decode('utf-8')
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
        """Extract all functions, methods, and arrow functions."""
        functions = []
        
        def traverse(n):
            # Regular functions: function foo() {}
            if n.type == 'function_declaration':
                func_info = self._create_function_info(n, source_bytes, module_path)
                if func_info:
                    functions.append(func_info)
            
            # Arrow functions: const foo = () => {}
            elif n.type == 'lexical_declaration' or n.type == 'variable_declaration':
                for child in n.children:
                    if child.type == 'variable_declarator':
                        name_node = child.child_by_field_name('name')
                        value_node = child.child_by_field_name('value')
                        
                        if value_node and value_node.type == 'arrow_function' and name_node:
                            func_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
                            func_info = self._create_arrow_function_info(
                                func_name, value_node, source_bytes, module_path
                            )
                            functions.append(func_info)
            
            # Methods in classes
            elif n.type == 'method_definition':
                func_info = self._create_method_info(n, source_bytes, module_path)
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
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None
        
        func_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
        start_line = node.start_point[0] + 1  # 0-indexed to 1-indexed
        end_line = node.end_point[0] + 1
        
        # Detect test functions
        is_test = (
            func_name.startswith('test') or
            'test' in module_path.lower() or
            'spec' in module_path.lower() or
            module_path.endswith('.test.ts') or
            module_path.endswith('.spec.ts')
        )
        
        # Extract calls
        calls = self._extract_calls_from_node(node, source_bytes)
        
        # Extract parameters
        params_node = node.child_by_field_name('parameters')
        parameters = self._extract_parameters(params_node, source_bytes) if params_node else []
        
        # Extract return type if present
        return_type_node = node.child_by_field_name('return_type')
        return_type = None
        if return_type_node:
            return_type = source_bytes[return_type_node.start_byte:return_type_node.end_byte].decode('utf-8')
        
        return FunctionInfo(
            name=func_name,
            module_path=module_path,
            start_line=start_line,
            end_line=end_line,
            language='typescript',
            is_test=is_test,
            calls=calls,
            parameters=parameters,
            return_type=return_type
        )
    
    def _create_arrow_function_info(
        self,
        func_name: str,
        node,
        source_bytes: bytes,
        module_path: str
    ) -> FunctionInfo:
        """Create FunctionInfo from arrow_function node."""
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        is_test = (
            func_name.startswith('test') or
            'test' in module_path.lower() or
            'spec' in module_path.lower()
        )
        
        calls = self._extract_calls_from_node(node, source_bytes)
        
        params_node = node.child_by_field_name('parameters')
        parameters = self._extract_parameters(params_node, source_bytes) if params_node else []
        
        return FunctionInfo(
            name=func_name,
            module_path=module_path,
            start_line=start_line,
            end_line=end_line,
            language='typescript',
            is_test=is_test,
            calls=calls,
            parameters=parameters
        )
    
    def _create_method_info(
        self,
        node,
        source_bytes: bytes,
        module_path: str
    ) -> Optional[FunctionInfo]:
        """Create FunctionInfo from method_definition node."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None
        
        method_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        
        is_test = method_name.startswith('test') or 'test' in module_path.lower()
        
        calls = self._extract_calls_from_node(node, source_bytes)
        
        params_node = node.child_by_field_name('parameters')
        parameters = self._extract_parameters(params_node, source_bytes) if params_node else []
        
        return FunctionInfo(
            name=method_name,
            module_path=module_path,
            start_line=start_line,
            end_line=end_line,
            language='typescript',
            is_test=is_test,
            calls=calls,
            parameters=parameters
        )
    
    def _extract_calls_from_node(self, node, source_bytes: bytes) -> Set[str]:
        """Extract function calls from a node."""
        calls = set()
        
        def traverse(n):
            if n.type == 'call_expression':
                func_node = n.child_by_field_name('function')
                if func_node:
                    # Handle obj.method() - get 'method'
                    if func_node.type == 'member_expression':
                        property_node = func_node.child_by_field_name('property')
                        if property_node:
                            call_name = source_bytes[property_node.start_byte:property_node.end_byte].decode('utf-8')
                            calls.add(call_name)
                    # Handle foo() - get 'foo'
                    elif func_node.type == 'identifier':
                        call_name = source_bytes[func_node.start_byte:func_node.end_byte].decode('utf-8')
                        calls.add(call_name)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return calls
    
    def _extract_parameters(self, params_node, source_bytes: bytes) -> List[str]:
        """Extract parameter names from parameters node."""
        parameters = []
        
        for child in params_node.children:
            if child.type == 'required_parameter' or child.type == 'optional_parameter':
                # Get identifier
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        param_name = source_bytes[subchild.start_byte:subchild.end_byte].decode('utf-8')
                        parameters.append(param_name)
                        break
        
        return parameters
    
    def _extract_exports(self, node, source_bytes: bytes) -> List[str]:
        """Extract exported names for metadata."""
        exports = []
        
        def traverse(n):
            if n.type == 'export_statement':
                # export { foo, bar }
                for child in n.children:
                    if child.type == 'export_clause':
                        for spec in child.children:
                            if spec.type == 'export_specifier':
                                name_node = spec.child_by_field_name('name')
                                if name_node:
                                    export_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
                                    exports.append(export_name)
            
            # export function foo() {}
            elif n.type in ['function_declaration', 'lexical_declaration']:
                # Check if parent is export
                parent = n.parent
                if parent and parent.type == 'export_statement':
                    name_node = n.child_by_field_name('name')
                    if name_node:
                        export_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf-8')
                        exports.append(export_name)
            
            for child in n.children:
                traverse(child)
        
        traverse(node)
        return exports

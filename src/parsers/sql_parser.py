"""
SQL parser using sqlparse.
Handles .sql files (stored procedures, functions, queries).
"""

from pathlib import Path
from typing import Optional, List, Set
import sqlparse
from sqlparse.sql import Function, Identifier, IdentifierList
from sqlparse.tokens import Keyword, DML

from .base import LanguageParser, FunctionInfo, ModuleInfo


class SQLParser(LanguageParser):
    """Parse SQL files to extract procedures, functions, and dependencies."""
    
    def get_file_extensions(self) -> List[str]:
        return ['.sql']
    
    def get_language_name(self) -> str:
        return 'sql'
    
    def parse_file(self, file_path: Path) -> Optional[ModuleInfo]:
        """Parse a single SQL file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        # Create module info
        relative_path = str(file_path.relative_to(self.repo_path))
        module_name = file_path.stem
        
        module = ModuleInfo(
            path=relative_path,
            name=module_name,
            language='sql'
        )
        
        # Parse SQL
        statements = sqlparse.parse(source_code)
        
        for stmt in statements:
            # Extract CREATE PROCEDURE/FUNCTION
            if self._is_create_procedure(stmt) or self._is_create_function(stmt):
                func_info = self._extract_procedure_or_function(stmt, relative_path, source_code)
                if func_info:
                    module.functions.append(func_info)
            
            # Extract table references for imports
            tables = self._extract_table_references(stmt)
            module.imports.update(tables)
        
        return module
    
    def _is_create_procedure(self, stmt) -> bool:
        """Check if statement is CREATE PROCEDURE or CREATE OR REPLACE PROCEDURE."""
        tokens = [t for t in stmt.flatten() if not t.is_whitespace]
        
        for i, token in enumerate(tokens):
            # Check for CREATE OR REPLACE PROCEDURE
            if token.ttype is Keyword.DDL and 'CREATE' in token.value.upper():
                # Next token should be FUNCTION or PROCEDURE
                if i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    if next_token.ttype is Keyword and next_token.value.upper() == 'PROCEDURE':
                        return True
        return False
    
    def _is_create_function(self, stmt) -> bool:
        """Check if statement is CREATE FUNCTION or CREATE OR REPLACE FUNCTION."""
        tokens = [t for t in stmt.flatten() if not t.is_whitespace]
        
        for i, token in enumerate(tokens):
            # Check for CREATE OR REPLACE FUNCTION
            if token.ttype is Keyword.DDL and 'CREATE' in token.value.upper():
                # Next token should be FUNCTION or PROCEDURE
                if i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    if next_token.ttype is Keyword and next_token.value.upper() == 'FUNCTION':
                        return True
        return False
    
    def _extract_procedure_or_function(
        self,
        stmt,
        module_path: str,
        source_code: str
    ) -> Optional[FunctionInfo]:
        """Extract procedure/function info from CREATE statement."""
        # Get tokens
        tokens = [t for t in stmt.flatten() if not t.is_whitespace]
        
        # Find procedure/function name (after CREATE [OR REPLACE] PROCEDURE/FUNCTION)
        proc_name = None
        for i, token in enumerate(tokens):
            if token.ttype is Keyword and token.value.upper() in ['PROCEDURE', 'FUNCTION']:
                # Next non-whitespace token should be the name
                if i + 1 < len(tokens):
                    name_token = tokens[i + 1]
                    proc_name = name_token.value
                    # Remove schema prefix if present (schema.proc_name -> proc_name)
                    if '.' in proc_name:
                        proc_name = proc_name.split('.')[-1]
                    # Remove parentheses if present
                    if '(' in proc_name:
                        proc_name = proc_name.split('(')[0]
                    break
        
        if not proc_name:
            return None
        
        # Get line numbers (approximate from statement position)
        stmt_str = str(stmt)
        start_pos = source_code.find(stmt_str)
        if start_pos != -1:
            start_line = source_code[:start_pos].count('\n') + 1
            end_line = start_line + stmt_str.count('\n')
        else:
            start_line = 1
            end_line = 1
        
        # Extract calls to other procedures/functions
        calls = self._extract_proc_calls(stmt)
        
        # Extract parameters
        parameters = self._extract_parameters(stmt)
        
        return FunctionInfo(
            name=proc_name,
            module_path=module_path,
            start_line=start_line,
            end_line=end_line,
            language='sql',
            is_test=False,  # SQL doesn't have typical test conventions
            calls=calls,
            parameters=parameters
        )
    
    def _extract_proc_calls(self, stmt) -> Set[str]:
        """Extract procedure/function calls (CALL, EXECUTE, direct calls)."""
        calls = set()
        
        # Look for CALL or EXEC/EXECUTE keywords
        tokens = list(stmt.flatten())
        
        for i, token in enumerate(tokens):
            if token.ttype is Keyword and token.value.upper() in ['CALL', 'EXEC', 'EXECUTE']:
                # Next identifier should be the procedure name
                for j in range(i + 1, min(i + 5, len(tokens))):
                    if not tokens[j].is_whitespace:
                        if tokens[j].ttype in [sqlparse.tokens.Name, None]:
                            call_name = tokens[j].value
                            # Remove schema prefix
                            if '.' in call_name:
                                call_name = call_name.split('.')[-1]
                            # Remove parentheses
                            call_name = call_name.rstrip('(')
                            calls.add(call_name)
                        break
        
        # Also look for function calls in SELECT/WHERE clauses
        for token in stmt.tokens:
            if isinstance(token, Function):
                func_name = self._get_function_name(token)
                if func_name:
                    calls.add(func_name)
        
        return calls
    
    def _get_function_name(self, func_token) -> Optional[str]:
        """Extract function name from Function token."""
        for token in func_token.tokens:
            if isinstance(token, Identifier):
                return token.get_name()
            elif token.ttype in [sqlparse.tokens.Name, None]:
                name = token.value.strip('(')
                if name:
                    return name
        return None
    
    def _extract_parameters(self, stmt) -> List[str]:
        """Extract parameter names from procedure/function definition."""
        parameters = []
        
        # Look for parameter list (between first '(' and matching ')')
        stmt_str = str(stmt)
        
        # Find first '(' after procedure name
        paren_start = stmt_str.find('(')
        if paren_start == -1:
            return parameters
        
        # Find matching ')'
        depth = 0
        paren_end = -1
        for i in range(paren_start, len(stmt_str)):
            if stmt_str[i] == '(':
                depth += 1
            elif stmt_str[i] == ')':
                depth -= 1
                if depth == 0:
                    paren_end = i
                    break
        
        if paren_end == -1:
            return parameters
        
        # Parse parameter list
        params_str = stmt_str[paren_start + 1:paren_end]
        
        # Split by comma and extract parameter names
        for param in params_str.split(','):
            param = param.strip()
            if param:
                # Extract first word (parameter name)
                words = param.split()
                if words:
                    param_name = words[0].strip('@')  # Remove @ prefix (SQL Server)
                    parameters.append(param_name)
        
        return parameters
    
    def _extract_table_references(self, stmt) -> Set[str]:
        """Extract table names referenced in FROM/JOIN clauses."""
        tables = set()
        
        tokens = list(stmt.flatten())
        
        for i, token in enumerate(tokens):
            # Look for FROM or JOIN keywords
            if token.ttype is Keyword and token.value.upper() in ['FROM', 'JOIN', 'INTO', 'UPDATE']:
                # Next identifier should be table name
                for j in range(i + 1, min(i + 5, len(tokens))):
                    if not tokens[j].is_whitespace:
                        if tokens[j].ttype in [sqlparse.tokens.Name, None] and tokens[j].value.upper() not in ['AS', 'ON', 'WHERE', 'SET']:
                            table_name = tokens[j].value
                            # Remove schema prefix
                            if '.' in table_name:
                                table_name = table_name.split('.')[-1]
                            tables.add(table_name)
                        break
        
        return tables

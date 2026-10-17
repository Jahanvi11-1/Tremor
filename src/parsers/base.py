"""
Abstract base parser interface for multi-language support.

All language-specific parsers implement this interface to provide
a consistent graph schema regardless of source language.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Optional


@dataclass
class FunctionInfo:
    """Represents a callable unit (function, method, procedure, query)."""
    name: str
    module_path: str  # Relative path to file
    start_line: int
    end_line: int
    language: str  # 'python', 'typescript', 'dart', 'sql'
    is_test: bool = False
    calls: Set[str] = field(default_factory=set)  # Names of functions/methods called
    parameters: List[str] = field(default_factory=list)  # Parameter names
    return_type: Optional[str] = None
    
    # Language-specific metadata
    metadata: Dict[str, any] = field(default_factory=dict)


@dataclass
class ModuleInfo:
    """Represents a source file (module, class, schema)."""
    path: str  # Relative path
    name: str  # File/module name
    language: str
    imports: Set[str] = field(default_factory=set)  # Imported module/package names
    functions: List[FunctionInfo] = field(default_factory=list)
    
    # Language-specific metadata (e.g., class hierarchy, exports)
    metadata: Dict[str, any] = field(default_factory=dict)


class LanguageParser(ABC):
    """
    Abstract base class for language-specific parsers.
    
    Each parser extracts:
    - Modules (files)
    - Functions/methods/procedures
    - Import/dependency relationships
    - Call graphs
    """
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.modules: Dict[str, ModuleInfo] = {}
    
    @abstractmethod
    def get_file_extensions(self) -> List[str]:
        """
        Return list of file extensions this parser handles.
        
        Example: ['.py', '.pyi']
        """
        pass
    
    @abstractmethod
    def get_language_name(self) -> str:
        """Return language identifier (e.g., 'python', 'typescript')."""
        pass
    
    @abstractmethod
    def parse_file(self, file_path: Path) -> Optional[ModuleInfo]:
        """
        Parse a single source file.
        
        Args:
            file_path: Absolute path to file
            
        Returns:
            ModuleInfo if successful, None if parse failed
        """
        pass
    
    def parse_repository(self, src_dirs: List[str] = None) -> Dict[str, ModuleInfo]:
        """
        Parse all relevant files in the repository.
        
        Args:
            src_dirs: List of subdirectories to parse (relative to repo_path).
                     If None, parse entire repo.
        
        Returns:
            Dictionary mapping relative module path to ModuleInfo
        """
        if src_dirs is None:
            src_dirs = ['.']
        
        extensions = self.get_file_extensions()
        lang = self.get_language_name()
        
        print(f"Parsing {lang} files ({', '.join(extensions)})...")
        
        all_files = []
        for src_dir in src_dirs:
            target_path = self.repo_path / src_dir
            
            if not target_path.exists():
                print(f"  Warning: Directory not found: {target_path}")
                continue
            
            for ext in extensions:
                files = list(target_path.rglob(f"*{ext}"))
                all_files.extend(files)
        
        print(f"  Found {len(all_files)} {lang} files")
        
        parsed_count = 0
        failed_count = 0
        
        for file_path in all_files:
            try:
                module_info = self.parse_file(file_path)
                if module_info:
                    self.modules[module_info.path] = module_info
                    parsed_count += 1
            except Exception as e:
                print(f"  Warning: Failed to parse {file_path.name}: {e}")
                failed_count += 1
        
        print(f"  ✓ Parsed {parsed_count} modules ({failed_count} failed)")
        return self.modules
    
    def get_statistics(self) -> Dict[str, int]:
        """Get parsing statistics."""
        total_functions = sum(len(m.functions) for m in self.modules.values())
        total_imports = sum(len(m.imports) for m in self.modules.values())
        total_calls = sum(
            len(f.calls) 
            for m in self.modules.values() 
            for f in m.functions
        )
        test_functions = sum(
            1 
            for m in self.modules.values() 
            for f in m.functions 
            if f.is_test
        )
        
        return {
            'language': self.get_language_name(),
            'modules': len(self.modules),
            'functions': total_functions,
            'imports': total_imports,
            'calls': total_calls,
            'test_functions': test_functions
        }

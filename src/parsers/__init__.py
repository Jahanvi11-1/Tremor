"""
Multi-language parser factory with auto-detection.

Usage:
    from parsers import detect_languages, create_parsers, parse_multi_language_repo
    
    # Auto-detect languages in repo
    languages = detect_languages(repo_path)
    
    # Create parsers for detected languages
    parsers = create_parsers(repo_path, languages)
    
    # Parse entire repo
    all_modules = parse_multi_language_repo(repo_path, languages)
"""

from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict

from .base import LanguageParser, ModuleInfo
from .python_parser import PythonParser
from .typescript_parser import TypeScriptParser
from .dart_parser import DartParser
from .sql_parser import SQLParser


# Registry of available parsers
PARSER_REGISTRY: Dict[str, type] = {
    'python': PythonParser,
    'typescript': TypeScriptParser,
    'dart': DartParser,
    'sql': SQLParser
}


def detect_languages(repo_path: str) -> Set[str]:
    """
    Auto-detect languages in repository based on file extensions.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Set of language identifiers (e.g., {'python', 'typescript'})
    """
    repo = Path(repo_path)
    
    if not repo.exists():
        raise ValueError(f"Repository not found: {repo_path}")
    
    # Map extensions to languages
    ext_to_lang = {}
    for lang, parser_class in PARSER_REGISTRY.items():
        # Create temporary instance to get extensions
        try:
            temp_parser = parser_class(repo_path)
            for ext in temp_parser.get_file_extensions():
                ext_to_lang[ext] = lang
        except (ImportError, Exception) as e:
            # Skip parsers that can't be initialized (missing dependencies)
            print(f"Note: {lang} parser unavailable ({e})")
            continue
    
    # Scan repository
    detected = set()
    
    # Look for common source directories first
    common_dirs = ['src', 'lib', 'app', 'pkg', 'packages', 'backend', 'frontend', 'server', 'client', 'db', 'sql']
    search_paths = []
    
    for common_dir in common_dirs:
        dir_path = repo / common_dir
        if dir_path.exists() and dir_path.is_dir():
            search_paths.append(dir_path)
    
    # If no common dirs found, search entire repo
    if not search_paths:
        search_paths = [repo]
    
    # Count file extensions
    ext_counts = defaultdict(int)
    
    for search_path in search_paths:
        for file_path in search_path.rglob('*'):
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in ext_to_lang:
                    ext_counts[ext] += 1
                    detected.add(ext_to_lang[ext])
    
    # Print detection summary
    print("Language Detection Results:")
    print("-" * 60)
    
    if detected:
        for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1]):
            lang = ext_to_lang[ext]
            print(f"  {lang:12} ({ext:6}): {count:4} files")
    else:
        print("  No supported languages detected")
    
    print("-" * 60)
    print(f"Detected languages: {', '.join(sorted(detected)) if detected else 'none'}")
    print()
    
    return detected


def create_parsers(
    repo_path: str,
    languages: Set[str] = None
) -> Dict[str, LanguageParser]:
    """
    Create parser instances for specified languages.
    
    Args:
        repo_path: Path to repository
        languages: Set of language identifiers. If None, auto-detect.
        
    Returns:
        Dictionary mapping language -> parser instance
    """
    if languages is None:
        languages = detect_languages(repo_path)
    
    parsers = {}
    
    for lang in languages:
        if lang not in PARSER_REGISTRY:
            print(f"Warning: No parser available for language '{lang}'")
            continue
        
        parser_class = PARSER_REGISTRY[lang]
        try:
            parser = parser_class(repo_path)
            parsers[lang] = parser
            print(f"✓ Created {lang} parser")
        except (ImportError, Exception) as e:
            print(f"✗ Failed to create {lang} parser: {e}")
            print(f"  Skipping {lang} files...")
    
    return parsers


def parse_multi_language_repo(
    repo_path: str,
    languages: Set[str] = None,
    src_dirs: Dict[str, List[str]] = None
) -> Dict[str, ModuleInfo]:
    """
    Parse multi-language repository.
    
    Args:
        repo_path: Path to repository
        languages: Set of languages to parse. If None, auto-detect.
        src_dirs: Optional dict mapping language -> list of source directories.
                 Example: {'python': ['src/backend'], 'typescript': ['src/frontend']}
                 If None, each parser searches the entire repo.
    
    Returns:
        Dictionary mapping module path -> ModuleInfo (all languages combined)
    """
    print("=" * 60)
    print("MULTI-LANGUAGE REPOSITORY PARSING")
    print("=" * 60)
    print(f"Repository: {repo_path}")
    print()
    
    # Create parsers
    parsers = create_parsers(repo_path, languages)
    
    if not parsers:
        print("No parsers available. Exiting.")
        return {}
    
    print()
    print("=" * 60)
    print("PARSING SOURCE FILES")
    print("=" * 60)
    
    # Parse with each parser
    all_modules = {}
    
    for lang, parser in parsers.items():
        print()
        print(f"Parsing {lang}...")
        print("-" * 60)
        
        # Get language-specific source directories
        lang_dirs = None
        if src_dirs and lang in src_dirs:
            lang_dirs = src_dirs[lang]
        
        try:
            modules = parser.parse_repository(lang_dirs)
            all_modules.update(modules)
            
            stats = parser.get_statistics()
            print(f"  Modules:   {stats['modules']}")
            print(f"  Functions: {stats['functions']}")
            print(f"  Imports:   {stats['imports']}")
            print(f"  Calls:     {stats['calls']}")
            
        except Exception as e:
            print(f"  Error parsing {lang}: {e}")
    
    print()
    print("=" * 60)
    print("PARSING COMPLETE")
    print("=" * 60)
    
    # Overall statistics
    total_modules = len(all_modules)
    total_functions = sum(len(m.functions) for m in all_modules.values())
    
    print(f"Total modules:   {total_modules}")
    print(f"Total functions: {total_functions}")
    
    # Per-language breakdown
    lang_counts = defaultdict(lambda: {'modules': 0, 'functions': 0})
    
    for module in all_modules.values():
        lang_counts[module.language]['modules'] += 1
        lang_counts[module.language]['functions'] += len(module.functions)
    
    print()
    print("Breakdown by language:")
    for lang, counts in sorted(lang_counts.items()):
        print(f"  {lang:12}: {counts['modules']:4} modules, {counts['functions']:5} functions")
    
    print("=" * 60)
    print()
    
    return all_modules


# Convenience exports
__all__ = [
    'LanguageParser',
    'ModuleInfo',
    'FunctionInfo',
    'PythonParser',
    'TypeScriptParser',
    'DartParser',
    'SQLParser',
    'detect_languages',
    'create_parsers',
    'parse_multi_language_repo',
    'PARSER_REGISTRY'
]

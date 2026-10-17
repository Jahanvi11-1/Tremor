"""
Multi-language graph loader.
Supports Python, TypeScript, Dart, SQL in the same graph.

Usage:
    python src/multi_loader.py
    
Or with specific languages:
    LANGUAGES=python,typescript python src/multi_loader.py
"""

import os
from dotenv import load_dotenv
from typing import Dict, Set

from db import get_graph
from parsers import parse_multi_language_repo, ModuleInfo
from git_loader import GitHistoryLoader

load_dotenv()


class MultiLanguageGraphLoader:
    """Load multi-language code structure into FalkorDB."""
    
    def __init__(self, graph):
        self.graph = graph
    
    def clear_graph(self):
        """Clear all nodes and edges (fresh start)."""
        print("Clearing existing graph data...")
        self.graph.query("MATCH (n) DETACH DELETE n")
        print("✓ Graph cleared")
    
    def load_modules_and_functions(self, modules: Dict[str, ModuleInfo]):
        """
        Load Module and Function nodes, plus CONTAINS edges.
        Works with modules from any supported language.
        
        Args:
            modules: Dict of ModuleInfo from multi-language parser
        """
        print("\nLoading modules and functions into graph...")
        
        module_count = 0
        function_count = 0
        contains_count = 0
        
        for module_path, module_info in modules.items():
            # Create Module node with language attribute
            query = """
            CREATE (m:Module {
                path: $path,
                name: $name,
                language: $language
            })
            """
            self.graph.query(query, {
                'path': module_info.path,
                'name': module_info.name,
                'language': module_info.language
            })
            module_count += 1
            
            # Create Function nodes and CONTAINS edges
            for func in module_info.functions:
                query = """
                MATCH (m:Module {path: $module_path})
                CREATE (f:Function {
                    name: $name,
                    module: $module_path,
                    language: $language,
                    is_test: $is_test,
                    start_line: $start_line,
                    end_line: $end_line
                })
                CREATE (m)-[:CONTAINS]->(f)
                """
                self.graph.query(query, {
                    'module_path': module_info.path,
                    'name': func.name,
                    'language': func.language,
                    'is_test': func.is_test,
                    'start_line': func.start_line,
                    'end_line': func.end_line
                })
                function_count += 1
                contains_count += 1
        
        print(f"✓ Loaded {module_count} modules")
        print(f"✓ Loaded {function_count} functions")
        print(f"✓ Created {contains_count} CONTAINS edges")
    
    def load_imports(self, modules: Dict[str, ModuleInfo]):
        """
        Load IMPORTS/DEPENDS_ON edges between modules.
        
        Handles:
        - Python: import statements
        - TypeScript: import/require statements
        - Dart: import statements
        - SQL: table references (as dependencies)
        
        Only creates edges if both modules exist in the graph.
        """
        print("\nLoading import relationships...")
        
        imports_count = 0
        
        # Build module name -> path lookup (per language for disambiguation)
        module_lookup = {}
        for m in modules.values():
            key = (m.name, m.language)
            module_lookup[key] = m.path
        
        # Also build simple name lookup for cross-language references
        simple_lookup = {m.name: m.path for m in modules.values()}
        
        for module_path, module_info in modules.items():
            for imported_name in module_info.imports:
                target_path = None
                
                # Try same-language lookup first
                key = (imported_name, module_info.language)
                if key in module_lookup:
                    target_path = module_lookup[key]
                # Try simple lookup
                elif imported_name in simple_lookup:
                    target_path = simple_lookup[imported_name]
                # Try matching file path
                else:
                    # Check if import is a relative/absolute path
                    for other_path, other_module in modules.items():
                        if imported_name in other_path or other_module.name in imported_name:
                            target_path = other_path
                            break
                
                if target_path:
                    query = """
                    MATCH (m1:Module {path: $from_path})
                    MATCH (m2:Module {path: $to_path})
                    MERGE (m1)-[:IMPORTS]->(m2)
                    """
                    self.graph.query(query, {
                        'from_path': module_path,
                        'to_path': target_path
                    })
                    imports_count += 1
        
        print(f"✓ Created {imports_count} IMPORTS edges")
    
    def load_calls(self, modules: Dict[str, ModuleInfo]):
        """
        Load CALLS edges between functions.
        
        For intra-module calls (function calls within same module).
        Cross-module call tracking can be enhanced later.
        
        Confidence property = 1.0 (static analysis certainty).
        """
        print("\nLoading function call relationships...")
        
        calls_count = 0
        
        for module_path, module_info in modules.items():
            # Build function name -> FunctionInfo lookup for this module
            func_lookup = {f.name: f for f in module_info.functions}
            
            for func in module_info.functions:
                for called_name in func.calls:
                    # Check if called function exists in same module
                    if called_name in func_lookup:
                        query = """
                        MATCH (f1:Function {name: $from_name, module: $module})
                        MATCH (f2:Function {name: $to_name, module: $module})
                        MERGE (f1)-[:CALLS {confidence: 1.0}]->(f2)
                        """
                        self.graph.query(query, {
                            'from_name': func.name,
                            'to_name': called_name,
                            'module': module_path
                        })
                        calls_count += 1
        
        print(f"✓ Created {calls_count} CALLS edges (intra-module)")
    
    def print_graph_stats(self):
        """Print graph statistics for verification."""
        print("\n" + "=" * 60)
        print("GRAPH STATISTICS")
        print("=" * 60)
        
        # Count nodes
        result = self.graph.query("MATCH (m:Module) RETURN count(m) AS count")
        module_count = result.result_set[0][0] if result.result_set else 0
        
        result = self.graph.query("MATCH (f:Function) RETURN count(f) AS count")
        function_count = result.result_set[0][0] if result.result_set else 0
        
        result = self.graph.query("MATCH (f:Function {is_test: true}) RETURN count(f) AS count")
        test_count = result.result_set[0][0] if result.result_set else 0
        
        result = self.graph.query("MATCH (c:Commit) RETURN count(c) AS count")
        commit_count = result.result_set[0][0] if result.result_set else 0
        
        result = self.graph.query("MATCH (a:Author) RETURN count(a) AS count")
        author_count = result.result_set[0][0] if result.result_set else 0
        
        # Count edges
        result = self.graph.query("MATCH ()-[r:CONTAINS]->() RETURN count(r) AS count")
        contains_count = result.result_set[0][0] if result.result_set else 0
        
        result = self.graph.query("MATCH ()-[r:IMPORTS]->() RETURN count(r) AS count")
        imports_count = result.result_set[0][0] if result.result_set else 0
        
        result = self.graph.query("MATCH ()-[r:CALLS]->() RETURN count(r) AS count")
        calls_count = result.result_set[0][0] if result.result_set else 0
        
        result = self.graph.query("MATCH ()-[r:TOUCHED]->() RETURN count(r) AS count")
        touched_count = result.result_set[0][0] if result.result_set else 0
        
        result = self.graph.query("MATCH ()-[r:AUTHORED]->() RETURN count(r) AS count")
        authored_count = result.result_set[0][0] if result.result_set else 0
        
        print(f"Modules:        {module_count}")
        print(f"Functions:      {function_count}")
        print(f"  (tests):      {test_count}")
        print(f"Commits:        {commit_count}")
        print(f"Authors:        {author_count} (pseudonymized)")
        print()
        print(f"CONTAINS edges: {contains_count}")
        print(f"IMPORTS edges:  {imports_count}")
        print(f"CALLS edges:    {calls_count}")
        print(f"TOUCHED edges:  {touched_count}")
        print(f"AUTHORED edges: {authored_count}")
        print()
        
        # Language breakdown
        print("Modules by language:")
        result = self.graph.query("""
            MATCH (m:Module)
            RETURN m.language AS language, count(m) AS count
            ORDER BY count DESC
        """)
        
        for row in result.result_set:
            language, count = row
            print(f"  {language:12}: {count:4} modules")
        
        print()
        print("Functions by language:")
        result = self.graph.query("""
            MATCH (f:Function)
            RETURN f.language AS language, count(f) AS count
            ORDER BY count DESC
        """)
        
        for row in result.result_set:
            language, count = row
            print(f"  {language:12}: {count:5} functions")
        
        print()
        print("Top 5 most-calling functions (any language):")
        result = self.graph.query("""
            MATCH (f:Function)-[c:CALLS]->()
            RETURN f.name AS function, f.module AS module, f.language AS language, count(c) AS calls
            ORDER BY calls DESC
            LIMIT 5
        """)
        
        for row in result.result_set:
            func_name, module, language, call_count = row
            short_module = module.split('/')[-1] if '/' in module else module
            print(f"  {func_name} ({short_module}, {language}): {call_count} calls")
        
        print()
        print("Top 5 contributors:")
        result = self.graph.query("""
            MATCH (a:Author)-[:AUTHORED]->(c:Commit)
            RETURN a.name AS author, count(c) AS commits
            ORDER BY commits DESC
            LIMIT 5
        """)
        
        for row in result.result_set:
            author, commits = row
            print(f"  {author}: {commits} commits")
        
        print("=" * 60)


def main():
    """Parse multi-language repository and load into FalkorDB."""
    repo_path = os.getenv('REPO_PATH', './data/click')
    
    # Optional: specify languages (comma-separated)
    languages_env = os.getenv('LANGUAGES')
    languages = set(languages_env.split(',')) if languages_env else None
    
    # Optional: specify source directories per language
    # Example: PYTHON_DIRS=src/backend,backend TYPESCRIPT_DIRS=src/frontend,frontend
    src_dirs = {}
    for lang in ['python', 'typescript', 'dart', 'sql']:
        env_var = f"{lang.upper()}_DIRS"
        dirs_env = os.getenv(env_var)
        if dirs_env:
            src_dirs[lang] = dirs_env.split(',')
    
    print("TREMOR: Multi-Language Code Analysis")
    print("=" * 60)
    print(f"Repository: {repo_path}")
    if languages:
        print(f"Languages:  {', '.join(languages)}")
    else:
        print("Languages:  Auto-detect")
    
    if src_dirs:
        print("\nSource directories:")
        for lang, dirs in src_dirs.items():
            print(f"  {lang}: {', '.join(dirs)}")
    
    print()
    
    # Parse repository
    modules = parse_multi_language_repo(
        repo_path,
        languages=languages,
        src_dirs=src_dirs if src_dirs else None
    )
    
    if not modules:
        print("No modules parsed. Exiting.")
        return
    
    # Load into graph
    print()
    print("=" * 60)
    print("LOADING INTO FALKORDB")
    print("=" * 60)
    
    graph = get_graph()
    loader = MultiLanguageGraphLoader(graph)
    
    # Clear existing data
    loader.clear_graph()
    
    # Load structure
    loader.load_modules_and_functions(modules)
    loader.load_imports(modules)
    loader.load_calls(modules)
    
    # Load git history
    print()
    git_loader = GitHistoryLoader(repo_path, graph)
    git_loader.load_history(max_commits=50)

    # Load project context
    try:
        from project_loader import load_projects
        load_projects(repo_path)
    except Exception as e:
        print(f"  Note: Project loading skipped: {e}")

    # Verify
    loader.print_graph_stats()
    
    print("\n✓ Multi-language graph loaded successfully!")
    print("\nView in browser: http://localhost:3000")
    print('Try query: MATCH (m:Module) RETURN m.name, m.language, m.path LIMIT 20')


if __name__ == "__main__":
    main()

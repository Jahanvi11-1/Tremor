"""
Load parsed code structures into FalkorDB graph.

Graph schema:
- Node: Module (properties: path, name)
- Node: Function (properties: name, module, is_test, start_line, end_line)
- Node: Commit (properties: sha, message, timestamp)
- Node: Author (properties: pseudonym_id, name)
- Edge: CONTAINS (Module -> Function)
- Edge: IMPORTS (Module -> Module)
- Edge: CALLS (Function -> Function, property: confidence=1.0 for static analysis)
- Edge: TOUCHED (Commit -> Module)
- Edge: AUTHORED (Author -> Commit)

This is the foundation for multi-hop traversal queries.
"""

import os
from dotenv import load_dotenv

from db import get_graph
from parser import CodeParser
from git_loader import GitHistoryLoader

load_dotenv()


class GraphLoader:
    """Load code structure into FalkorDB."""
    
    def __init__(self, graph):
        self.graph = graph
    
    def clear_graph(self):
        """Clear all nodes and edges (fresh start)."""
        print("Clearing existing graph data...")
        self.graph.query("MATCH (n) DETACH DELETE n")
        print("✓ Graph cleared")
    
    def load_modules_and_functions(self, modules: dict):
        """
        Load Module and Function nodes, plus CONTAINS edges.
        
        Args:
            modules: Dict of ModuleInfo from parser
        """
        print("\nLoading modules and functions into graph...")
        
        module_count = 0
        function_count = 0
        contains_count = 0
        
        for module_path, module_info in modules.items():
            # Create Module node
            query = """
            CREATE (m:Module {
                path: $path,
                name: $name
            })
            """
            self.graph.query(query, {
                'path': module_info.path,
                'name': module_info.name
            })
            module_count += 1
            
            # Create Function nodes and CONTAINS edges
            for func in module_info.functions:
                query = """
                MATCH (m:Module {path: $module_path})
                CREATE (f:Function {
                    name: $name,
                    module: $module_path,
                    is_test: $is_test,
                    start_line: $start_line,
                    end_line: $end_line
                })
                CREATE (m)-[:CONTAINS]->(f)
                """
                self.graph.query(query, {
                    'module_path': module_info.path,
                    'name': func.name,
                    'is_test': func.is_test,
                    'start_line': func.start_line,
                    'end_line': func.end_line
                })
                function_count += 1
                contains_count += 1
        
        print(f"✓ Loaded {module_count} modules")
        print(f"✓ Loaded {function_count} functions")
        print(f"✓ Created {contains_count} CONTAINS edges")
    
    def load_imports(self, modules: dict):
        """
        Load IMPORTS edges between modules.
        
        Note: Only creates edges if both modules exist in the graph.
        External imports (e.g., 'os', 'sys') are ignored.
        """
        print("\nLoading import relationships...")
        
        imports_count = 0
        
        # Build module name -> path lookup
        module_names = {m.name: m.path for m in modules.values()}
        
        for module_path, module_info in modules.items():
            for imported_name in module_info.imports:
                # Check if imported module exists in our parsed set
                if imported_name in module_names:
                    target_path = module_names[imported_name]
                    
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
    
    def load_calls(self, modules: dict):
        """
        Load CALLS edges between functions.
        
        For Step 3, we focus on intra-module calls (function calls within same module).
        Cross-module call tracking will be enhanced in later steps if needed.
        
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
        
        # Sample query: functions with most calls
        print("Top 5 most-calling functions:")
        result = self.graph.query("""
            MATCH (f:Function)-[c:CALLS]->()
            RETURN f.name AS function, f.module AS module, count(c) AS calls
            ORDER BY calls DESC
            LIMIT 5
        """)
        
        for row in result.result_set:
            func_name, module, call_count = row
            short_module = module.split('/')[-1] if '/' in module else module
            print(f"  {func_name} ({short_module}): {call_count} calls")
        
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
    """Parse code and load into FalkorDB."""
    repo_path = os.getenv('REPO_PATH', './data/click')
    
    print("TREMOR: Loading code structure into FalkorDB")
    print("=" * 60)
    print(f"Repository: {repo_path}")
    print()
    
    # Parse repository
    parser = CodeParser(repo_path)
    modules = parser.parse_repository()
    
    stats = parser.get_statistics()
    print()
    print(f"Parsed: {stats['modules']} modules, {stats['functions']} functions")
    print()
    
    # Load into graph
    graph = get_graph()
    loader = GraphLoader(graph)
    
    # Clear existing data
    loader.clear_graph()
    
    # Load structure
    loader.load_modules_and_functions(modules)
    loader.load_imports(modules)
    loader.load_calls(modules)
    
    # Load git history
    git_loader = GitHistoryLoader(repo_path, graph)
    git_loader.load_history(max_commits=50)
    
    # Verify
    loader.print_graph_stats()
    
    print("\n✓ Graph loaded successfully!")
    print("\nView in browser: http://localhost:3000")
    print('Try query: MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(m:Module) RETURN a.name, c.message, m.name LIMIT 10')


if __name__ == "__main__":
    main()

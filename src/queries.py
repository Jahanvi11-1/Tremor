"""
Core Cypher queries for Tremor.

These 5 queries are the multi-hop reasoning core that powers the agent.
Each one is documented with:
  - What it does in plain English
  - Why a graph is needed (what breaks without it)
  - The Cypher query itself

All queries run INSIDE FalkorDB — not Python loops over data.
"""

from db import get_graph


def blast_radius(function_name: str, max_hops: int = 3) -> dict:
    """
    Find all functions that could be affected if this function changes.

    HOW IT WORKS:
    Traverse CALLS edges outward from the starting function up to max_hops.
    Each hop means: "function X calls function Y, so if X changes, Y may break."

    WHY A GRAPH IS NEEDED:
    This is a multi-hop traversal — impact can cascade 3+ levels deep.
    In a flat database you'd need recursive self-joins or application-level loops.
    In FalkorDB, a single Cypher query walks the entire path in one shot.

    Cypher explanation:
      MATCH p = (start:Function {name: $name})-[:CALLS*1..3]->(affected:Function)
        - Start at the named function
        - Follow CALLS edges 1 to 3 hops out
        - Collect all reachable functions
    """
    graph = get_graph()

    query = f"""
    MATCH p = (start:Function {{name: $name}})-[:CALLS*1..{max_hops}]->(affected:Function)
    RETURN DISTINCT
        affected.name AS function,
        affected.module AS module,
        affected.is_test AS is_test,
        length(p) AS hops
    ORDER BY hops ASC, function ASC
    """

    result = graph.query(query, {'name': function_name})

    affected = []
    for row in result.result_set:
        affected.append({
            'function': row[0],
            'module': row[1],
            'is_test': row[2],
            'hops': row[3]
        })

    return {
        'origin': function_name,
        'affected_count': len(affected),
        'affected': affected,
        'query': query.strip()
    }


def find_tests(function_name: str, max_hops: int = 4) -> dict:
    """
    Find test functions that cover a given function.

    HOW IT WORKS:
    Walk CALLS edges BACKWARDS from the target function until we reach
    functions where is_test=true. These are the tests that exercise the code.

    WHY A GRAPH IS NEEDED:
    Test coverage here is derived from the call graph, not from coverage tools.
    We need to traverse MULTIPLE hops backwards:
      test_foo -> helper -> validator -> target_function
    That 3-hop reverse path is trivial in Cypher, painful in SQL.

    WHY THIS IS AN APPROXIMATION:
    Static analysis only — we can't know if a test actually exercises the code
    at runtime. But structural reachability is a good proxy.

    Cypher explanation:
      MATCH p = (test:Function {is_test: true})-[:CALLS*1..4]->(target:Function {name: $name})
        - Start from test functions
        - Walk forward through CALLS until we reach the target
        - This is a reverse reachability check
    """
    graph = get_graph()

    query = f"""
    MATCH p = (test:Function {{is_test: true}})-[:CALLS*1..{max_hops}]->(target:Function {{name: $name}})
    RETURN DISTINCT
        test.name AS test_function,
        test.module AS test_module,
        length(p) AS hops
    ORDER BY hops ASC, test_function ASC
    """

    result = graph.query(query, {'name': function_name})

    tests = []
    for row in result.result_set:
        tests.append({
            'test_function': row[0],
            'test_module': row[1],
            'hops': row[2]
        })

    return {
        'target': function_name,
        'tests_found': len(tests),
        'tests': tests,
        'approximation_note': 'Static call graph — structural reachability only, not runtime coverage',
        'query': query.strip()
    }


def find_reviewers(module_name: str, top_n: int = 3) -> dict:
    """
    Find the best reviewers for changes to a module.

    HOW IT WORKS:
    Follow the path: Author -[AUTHORED]-> Commit -[TOUCHED]-> Module
    Count how many commits each author has that touched this module.
    Rank by commit count — higher count = more familiarity.

    WHY A GRAPH IS NEEDED:
    This is a 2-hop traversal connecting three node types.
    SQL needs two JOIN operations and GROUP BY.
    In a graph: one MATCH with two hops is natural and readable.
    More importantly, this can extend to 3-hop patterns like:
      "find reviewers who also worked on modules that import this one"
    That kind of contextual multi-hop reasoning is where graphs shine.

    Cypher explanation:
      MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(m:Module {name: $name})
        - Start from Author nodes
        - Walk to Commits they authored
        - Walk to Modules those commits touched
        - Filter by module name, count, rank
    """
    graph = get_graph()

    query = """
    MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(m:Module)
    WHERE m.name = $name OR m.path CONTAINS $name
    RETURN
        a.name AS author,
        a.pseudonym_id AS pseudonym_id,
        count(DISTINCT c) AS commit_count,
        collect(DISTINCT c.message)[0..3] AS recent_commits
    ORDER BY commit_count DESC
    LIMIT $top_n
    """

    result = graph.query(query, {'name': module_name, 'top_n': top_n})

    reviewers = []
    for row in result.result_set:
        reviewers.append({
            'author': row[0],
            'pseudonym_id': row[1],
            'commit_count': row[2],
            'recent_commits': row[3]
        })

    return {
        'module': module_name,
        'reviewers_found': len(reviewers),
        'reviewers': reviewers,
        'query': query.strip()
    }


def rank_risk(top_n: int = 10) -> dict:
    """
    Rank functions by risk score using PageRank on the CALLS graph.

    HOW IT WORKS:
    Run FalkorDB's native PageRank algorithm on Function nodes connected by CALLS edges.
    PageRank assigns higher scores to functions that are called by many other
    high-importance functions. A function called from everywhere is riskier to change.

    WHY A GRAPH IS NEEDED:
    PageRank is a graph algorithm — it requires iterative traversal across the
    entire connected graph. It cannot be computed with a single SQL query.
    FalkorDB runs this natively inside the database engine, not in Python.

    WHY PAGERANK FOR RISK:
    In a codebase, a function with high PageRank is a "hub":
      - Many callers depend on it
      - Those callers are themselves widely used
    Changing a hub function causes cascading failures — it's the highest risk.

    Cypher explanation:
      CALL algo.pageRank('Function', 'CALLS') YIELD node, score
        - Run PageRank on Function nodes using CALLS as the relationship
        - FalkorDB iterates internally until convergence
        - Returns each node with its computed score
    """
    graph = get_graph()

    # Try native FalkorDB PageRank first
    try:
        query = """
        CALL algo.pageRank('Function', 'CALLS')
        YIELD node, score
        RETURN node.name AS function, node.module AS module, score
        ORDER BY score DESC
        LIMIT $top_n
        """
        result = graph.query(query, {'top_n': top_n})

        ranked = []
        for row in result.result_set:
            ranked.append({
                'function': row[0],
                'module': row[1],
                'score': round(row[2], 4),
                'method': 'pagerank'
            })

        return {
            'method': 'FalkorDB native PageRank',
            'top_n': top_n,
            'ranked': ranked,
            'query': query.strip()
        }

    except Exception as e:
        # Fallback: in-degree centrality (count of callers)
        # This is still a graph query — counts incoming CALLS edges
        query_fallback = """
        MATCH (caller:Function)-[:CALLS]->(f:Function)
        RETURN
            f.name AS function,
            f.module AS module,
            count(caller) AS caller_count
        ORDER BY caller_count DESC
        LIMIT $top_n
        """
        result = graph.query(query_fallback, {'top_n': top_n})

        ranked = []
        for row in result.result_set:
            ranked.append({
                'function': row[0],
                'module': row[1],
                'score': row[2],
                'method': 'in_degree'
            })

        return {
            'method': 'in-degree centrality (PageRank fallback)',
            'pagerank_error': str(e),
            'top_n': top_n,
            'ranked': ranked,
            'query': query_fallback.strip()
        }


def explain_path(from_function: str, to_function: str) -> dict:
    """
    Find and explain the shortest path between two functions.

    HOW IT WORKS:
    Use FalkorDB's shortest path algorithm to find the minimum-hop chain
    of CALLS relationships connecting two functions.
    Returns the path with all intermediate functions for evidence.

    WHY A GRAPH IS NEEDED:
    Shortest path between two arbitrary nodes requires graph traversal.
    In a relational DB this requires recursive CTEs with path tracking.
    In a graph: shortestPath() is a built-in, one-line operation.

    USE CASE:
    When the agent says "function A affects function B", this query provides
    the evidence: the exact chain of calls that connects them.
    Every claim has a graph path as proof.

    Cypher explanation:
      MATCH p = shortestPath((a:Function {name: $from})-[:CALLS*]->(b:Function {name: $to}))
        - shortestPath finds the minimum-hop route
        - [:CALLS*] means any number of CALLS hops
        - Returns the full path object (nodes + relationships)
    """
    graph = get_graph()

    # FalkorDB requires shortestPath to appear directly in RETURN clause
    query = """
    MATCH (a:Function {name: $from_name}), (b:Function {name: $to_name})
    RETURN shortestPath((a)-[:CALLS*]->(b)) AS p
    """

    result = graph.query(query, {
        'from_name': from_function,
        'to_name': to_function
    })

    if not result.result_set or result.result_set[0][0] is None:
        return {
            'from': from_function,
            'to': to_function,
            'found': False,
            'message': f'No call path found from {from_function} to {to_function}',
            'query': query.strip()
        }

    # FalkorDB returns the path object; extract nodes from it
    path_obj = result.result_set[0][0]
    try:
        path_nodes = path_obj.nodes()
        path_functions = [n.properties.get('name', '?') for n in path_nodes]
        path_modules = [n.properties.get('module', '?') for n in path_nodes]
        hops = len(path_functions) - 1
    except Exception:
        return {
            'from': from_function,
            'to': to_function,
            'found': False,
            'message': f'Path found but could not parse result: {path_obj}',
            'query': query.strip()
        }

    # Build human-readable path
    path_steps = []
    for i, func in enumerate(path_functions):
        short_module = path_modules[i].split('/')[-1] if path_modules[i] else '?'
        path_steps.append(f"{func} ({short_module})")

    path_str = " -> ".join(path_steps)

    return {
        'from': from_function,
        'to': to_function,
        'found': True,
        'hops': hops,
        'path': path_str,
        'path_functions': path_functions,
        'path_modules': path_modules,
        'query': query.strip()
    }


def get_session_history(function_name: str, limit: int = 5) -> dict:
    """
    Retrieve past analysis sessions for a function from the graph.

    WHY IN THE GRAPH:
    Memory is stored as graph nodes (AnalysisSession) connected to Function nodes.
    This means we can do multi-hop queries like:
      "Find sessions where blast radius increased AND the function is in core.py"
    Memory is queryable the same way code structure is — no separate DB needed.

    Cypher explanation:
      MATCH (s:AnalysisSession {function_name: $name})
        - Find all session nodes for this function
        - Order by timestamp descending (most recent first)
        - Return change metrics for trend analysis
    """
    graph = get_graph()

    query = """
    MATCH (s:AnalysisSession {function_name: $name})
    RETURN
        s.session_id AS session_id,
        s.timestamp AS timestamp,
        s.risk_rank AS risk_rank,
        s.blast_radius_count AS blast_radius_count,
        s.tests_found AS tests_found,
        s.review_summary AS review_summary
    ORDER BY s.timestamp DESC
    LIMIT $limit
    """

    result = graph.query(query, {'name': function_name, 'limit': limit})

    sessions = []
    for row in result.result_set:
        sessions.append({
            'session_id': row[0],
            'timestamp': row[1],
            'risk_rank': row[2] if row[2] and row[2] != -1 else None,
            'blast_radius_count': row[3],
            'tests_found': row[4],
            'review_summary': row[5]
        })

    return {
        'function': function_name,
        'session_count': len(sessions),
        'sessions': sessions,
        'query': query.strip()
    }


def get_project_context(module_path: str) -> dict:
    """
    Get the project/feature context for a module.

    HOW IT WORKS:
    Auto-detects project grouping from directory structure.
    Returns which project a module belongs to and other modules in that project.

    WHY A GRAPH IS NEEDED:
    Project context requires traversing:
      Module -> Project -> [other modules in same project]
    This cross-entity traversal is natural in a graph.
    """
    graph = get_graph()

    query = """
    MATCH (m:Module {path: $path})-[:BELONGS_TO]->(p:Project)
    OPTIONAL MATCH (other:Module)-[:BELONGS_TO]->(p)
    WHERE other.path <> $path
    RETURN
        p.name AS project_name,
        p.language AS project_language,
        collect(DISTINCT other.name) AS sibling_modules
    LIMIT 1
    """

    try:
        result = graph.query(query, {'path': module_path})
        if result.result_set:
            row = result.result_set[0]
            return {
                'project_name': row[0],
                'project_language': row[1],
                'sibling_modules': row[2] or [],
                'query': query.strip()
            }
    except Exception:
        pass

    return {
        'project_name': None,
        'sibling_modules': [],
        'query': query.strip()
    }


def _print_section(title: str):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main():
    """Test all 5 queries with real data from the click graph."""

    print("TREMOR: Core Query Tests")
    print("Running all 5 queries against the click graph...")

    # --- 1. blast_radius ---
    _print_section("1. BLAST RADIUS — invoke()")
    result = blast_radius('invoke', max_hops=2)
    print(f"Function: {result['origin']}")
    print(f"Affected functions (up to 2 hops): {result['affected_count']}")
    for item in result['affected'][:8]:
        test_mark = " [TEST]" if item['is_test'] else ""
        short_mod = item['module'].split('/')[-1]
        print(f"  hop {item['hops']}: {item['function']}{test_mark} ({short_mod})")
    if result['affected_count'] > 8:
        print(f"  ... and {result['affected_count'] - 8} more")

    # --- 2. find_tests ---
    _print_section("2. FIND TESTS — invoke()")
    result = find_tests('invoke', max_hops=4)
    print(f"Function: {result['target']}")
    print(f"Tests found: {result['tests_found']}")
    print(f"Note: {result['approximation_note']}")
    for t in result['tests'][:5]:
        short_mod = t['test_module'].split('/')[-1]
        print(f"  hop {t['hops']}: {t['test_function']} ({short_mod})")

    # --- 3. find_reviewers ---
    _print_section("3. FIND REVIEWERS — core module")
    result = find_reviewers('core')
    print(f"Module: {result['module']}")
    print(f"Reviewers found: {result['reviewers_found']}")
    for r in result['reviewers']:
        print(f"  {r['author']} (id: {r['pseudonym_id']}) — {r['commit_count']} commits")
        for msg in (r['recent_commits'] or [])[:2]:
            print(f"    • {msg[:60]}")

    # --- 4. rank_risk ---
    _print_section("4. RANK RISK — top 10 riskiest functions")
    result = rank_risk(top_n=10)
    print(f"Method: {result['method']}")
    for i, item in enumerate(result['ranked'], 1):
        short_mod = (item['module'] or '').split('/')[-1]
        print(f"  {i:2}. {item['function']} ({short_mod}) — score: {item['score']}")

    # --- 5. explain_path ---
    _print_section("5. EXPLAIN PATH — invoke() -> make_context()")
    result = explain_path('invoke', 'make_context')
    if result['found']:
        print(f"Path ({result['hops']} hops):")
        print(f"  {result['path']}")
    else:
        print(result['message'])
        # Try another pair
        print("\nTrying: convert -> fail...")
        result2 = explain_path('convert', 'fail')
        if result2['found']:
            print(f"Path ({result2['hops']} hops): {result2['path']}")
        else:
            print(result2['message'])

    print()
    print("=" * 60)
    print("All queries complete.")
    print("These functions are the MCP tools in Step 8.")
    print("=" * 60)


if __name__ == "__main__":
    main()

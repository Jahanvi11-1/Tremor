"""
MCP (Model Context Protocol) server for Tremor.

Exposes the 5 core graph query tools as HTTP endpoints.
The Gemini agent calls these endpoints to reason about code changes.

ENDPOINTS:
  GET  /                       — health check
  GET  /ui                     — serve the graph explorer UI
  GET  /tools                  — tool manifest (agent reads this)
  POST /tools/blast_radius     — find affected functions
  POST /tools/find_tests       — find test coverage
  POST /tools/find_reviewers   — find who to review
  POST /tools/rank_risk        — get risk rankings
  POST /tools/explain_path     — get path evidence
  POST /analyze                — full agent: graph evidence + Gemini review
  POST /query/natural          — natural language → Cypher → results
  GET  /graph/data             — all nodes/edges for vis.js visualization
  POST /graph/expand           — expand neighbors of a node
  GET  /memory/history         — session history for a function
  GET  /memory/all             — all analyzed functions (memory panel)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import uvicorn

from queries import blast_radius, find_tests, find_reviewers, rank_risk, explain_path, get_session_history

app = FastAPI(
    title="Tremor MCP Server",
    description="Graph-powered code review tools for the Tremor agent",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request models ---

class BlastRadiusRequest(BaseModel):
    function_name: str
    max_hops: Optional[int] = 3


class FindTestsRequest(BaseModel):
    function_name: str
    max_hops: Optional[int] = 4


class FindReviewersRequest(BaseModel):
    module_name: str
    top_n: Optional[int] = 3


class RankRiskRequest(BaseModel):
    top_n: Optional[int] = 10


class ExplainPathRequest(BaseModel):
    from_function: str
    to_function: str


class AnalyzeRequest(BaseModel):
    function_name: str
    module_name: Optional[str] = None


class NaturalQueryRequest(BaseModel):
    query: str                        # "show me high risk functions"
    max_results: Optional[int] = 20


class GraphExpandRequest(BaseModel):
    node_name: str
    node_type: Optional[str] = "Function"  # Function | Module | Author
    max_neighbors: Optional[int] = 20


class MemoryHistoryRequest(BaseModel):
    function_name: str
    limit: Optional[int] = 5


# --- Tool manifest ---

TOOL_MANIFEST = [
    {
        "name": "blast_radius",
        "description": (
            "Find all functions that could be affected if a given function changes. "
            "Traverses the CALLS graph outward using multi-hop Cypher query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "function_name": {"type": "string"},
                "max_hops": {"type": "integer", "default": 3}
            },
            "required": ["function_name"]
        }
    },
    {
        "name": "find_tests",
        "description": (
            "Find test functions that structurally cover a given function. "
            "Reverse-traverses the CALLS graph from test functions to the target."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "function_name": {"type": "string"},
                "max_hops": {"type": "integer", "default": 4}
            },
            "required": ["function_name"]
        }
    },
    {
        "name": "find_reviewers",
        "description": (
            "Find the best reviewers for a module based on git history. "
            "Traverses Author->Commit->Module relationships in the graph."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "module_name": {"type": "string"},
                "top_n": {"type": "integer", "default": 3}
            },
            "required": ["module_name"]
        }
    },
    {
        "name": "rank_risk",
        "description": (
            "Rank functions by risk using FalkorDB native PageRank algorithm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer", "default": 10}
            },
            "required": []
        }
    },
    {
        "name": "explain_path",
        "description": (
            "Find the shortest call path between two functions. "
            "Returns the chain of CALLS relationships as evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_function": {"type": "string"},
                "to_function": {"type": "string"}
            },
            "required": ["from_function", "to_function"]
        }
    }
]


# --- Endpoints ---

@app.get("/")
def health_check():
    try:
        from db import get_graph
        graph = get_graph()
        result = graph.query("MATCH (f:Function) RETURN count(f) AS count")
        function_count = result.result_set[0][0] if result.result_set else 0
        return {
            "status": "ok",
            "server": "Tremor MCP Server",
            "graph": "tremor",
            "functions_in_graph": function_count
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/ui", response_class=HTMLResponse)
@app.get("/ui/", response_class=HTMLResponse)
def serve_ui():
    """Serve the graph explorer UI from localhost to avoid CORS issues."""
    # Look for frontend directory relative to project root
    server_dir = os.path.dirname(__file__)          # src/
    project_root = os.path.dirname(server_dir)      # graphacks/
    
    ui_path = os.path.join(project_root, "frontend", "explorer.html")
    
    if not os.path.exists(ui_path):
        return HTMLResponse(content="<h1>UI not found</h1><p>Expected: frontend/explorer.html</p>", status_code=404)
    
    with open(ui_path, "r", encoding="utf-8") as f:
        html = f.read()
    
    # Inject the API URL so it always points to this server
    # This replaces the hardcoded localhost reference
    inject = """<script>window.TREMOR_API = window.location.origin;</script>"""
    html = html.replace("</head>", f"{inject}\n</head>")
    
    return HTMLResponse(content=html)


@app.get("/tools")
def list_tools():
    return {"tools": TOOL_MANIFEST, "total": len(TOOL_MANIFEST)}


@app.post("/tools/blast_radius")
def tool_blast_radius(req: BlastRadiusRequest):
    try:
        return {"ok": True, "result": blast_radius(req.function_name, req.max_hops)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/find_tests")
def tool_find_tests(req: FindTestsRequest):
    try:
        return {"ok": True, "result": find_tests(req.function_name, req.max_hops)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/find_reviewers")
def tool_find_reviewers(req: FindReviewersRequest):
    try:
        return {"ok": True, "result": find_reviewers(req.module_name, req.top_n)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/rank_risk")
def tool_rank_risk(req: RankRiskRequest):
    try:
        return {"ok": True, "result": rank_risk(req.top_n)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/explain_path")
def tool_explain_path(req: ExplainPathRequest):
    try:
        return {"ok": True, "result": explain_path(req.from_function, req.to_function)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """
    Full agent endpoint: gather graph evidence + call Gemini -> markdown review.
    This is what the UI calls.
    """
    from agent import gather_evidence, build_prompt, call_gemini, run_agent
    try:
        result = run_agent(req.function_name, req.module_name)

        # Handle both dict (new with memory) and str (legacy)
        if isinstance(result, dict):
            review_md = result['review']
            session_id = result.get('session_id')
            memory = result.get('memory')
            evidence = result.get('evidence', {})
        else:
            review_md = result
            session_id = None
            memory = None
            evidence = {}

        blast = evidence.get("blast_radius", {})
        reviewers_data = evidence.get("find_reviewers", {})
        risk_data = evidence.get("rank_risk", {})

        return {
            "ok": True,
            "function": req.function_name,
            "review": review_md,
            "session_id": session_id,
            "memory": memory,
            "stats": {
                "blast_radius": blast.get("affected_count", 0),
                "tests_found": evidence.get("find_tests", {}).get("tests_found", 0),
                "reviewers": [r["author"] for r in reviewers_data.get("reviewers", [])],
                "top_risk": risk_data.get("ranked", [{}])[0].get("function", "n/a") if risk_data.get("ranked") else "n/a",
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Natural Language Query ──────────────────────────────────────────────────

# Predefined safe query templates (fast, no Gemini needed for common queries)
QUERY_TEMPLATES = {
    "high risk": {
        "cypher": "MATCH (f:Function) WITH f CALL algo.pageRank('Function','CALLS') YIELD node, score WHERE node = f RETURN f.name AS function, f.module AS module, f.language AS language, score ORDER BY score DESC LIMIT 10",
        "description": "Top 10 highest-risk functions by PageRank"
    },
    "blast radius": None,   # Requires function name — handled by NL
    "all functions": {
        "cypher": "MATCH (f:Function) RETURN f.name AS function, f.module AS module, f.language AS language, f.is_test AS is_test ORDER BY f.name LIMIT 50",
        "description": "All functions in the graph"
    },
    "all modules": {
        "cypher": "MATCH (m:Module) RETURN m.name AS module, m.path AS path, m.language AS language ORDER BY m.language, m.name",
        "description": "All modules in the graph"
    },
    "authors": {
        "cypher": "MATCH (a:Author)-[:AUTHORED]->(c:Commit) RETURN a.name AS author, count(DISTINCT c) AS commits ORDER BY commits DESC",
        "description": "Authors ranked by commit count"
    },
    "test functions": {
        "cypher": "MATCH (f:Function {is_test: true}) RETURN f.name AS function, f.module AS module ORDER BY f.module, f.name LIMIT 30",
        "description": "All test functions"
    },
    "sessions": {
        "cypher": "MATCH (s:AnalysisSession) RETURN s.function_name AS function, s.session_id AS session, s.timestamp AS when, s.risk_rank AS risk_rank, s.blast_radius_count AS blast_radius ORDER BY s.timestamp DESC LIMIT 20",
        "description": "All analysis sessions (memory)"
    },
    "python functions": {
        "cypher": "MATCH (f:Function {language: 'python'}) RETURN f.name AS function, f.module AS module ORDER BY f.name LIMIT 50",
        "description": "Python functions"
    },
    "sql functions": {
        "cypher": "MATCH (f:Function {language: 'sql'}) RETURN f.name AS function, f.module AS module ORDER BY f.name",
        "description": "SQL stored procedures and functions"
    },
}


def nl_to_cypher_with_gemini(query: str) -> tuple[str, str]:
    """
    Use Gemini to convert natural language to Cypher query.
    Returns (cypher_query, explanation)
    """
    import os, requests as req
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    if not model.startswith("models/"):
        model = f"models/{model}"

    schema_context = """
Graph schema:
- Node: Function {name, module, language, is_test, start_line, end_line}
- Node: Module {name, path, language}
- Node: Author {name, pseudonym_id}
- Node: Commit {sha, message, timestamp}
- Node: AnalysisSession {session_id, function_name, timestamp, risk_rank, blast_radius_count, tests_found, review_summary}
- Node: Project {name, language}
- Edge: CONTAINS (Module -> Function)
- Edge: IMPORTS (Module -> Module)
- Edge: CALLS (Function -> Function, confidence)
- Edge: TOUCHED (Commit -> Module)
- Edge: AUTHORED (Author -> Commit)
- Edge: ANALYZED (AnalysisSession -> Function)
- Edge: BELONGS_TO (Module -> Project)

Language values: 'python', 'typescript', 'dart', 'sql'
"""

    prompt = f"""Convert this natural language query to a FalkorDB Cypher query.
Return ONLY valid Cypher. No explanation, no markdown code blocks, just raw Cypher.
Limit results to 30 unless the user specifies otherwise.

{schema_context}

User query: {query}

Cypher:"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 512}
        }
        response = req.post(url, params={"key": api_key}, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            cypher = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Clean up any accidental markdown
            cypher = cypher.replace("```cypher", "").replace("```", "").strip()
            return cypher, f"Generated from: '{query}'"
    except Exception as e:
        pass

    return None, f"Could not generate Cypher for: {query}"


def _safe_serialize(val):
    """
    Safely convert any FalkorDB result value to a JSON-serializable type.
    Handles: strings, ints, floats, bools, None, lists, path objects, node objects.
    """
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, list):
        return [_safe_serialize(v) for v in val]
    if isinstance(val, dict):
        return {str(k): _safe_serialize(v) for k, v in val.items()}
    # FalkorDB Path object
    if hasattr(val, 'nodes') and hasattr(val, 'edges'):
        try:
            nodes = val.nodes()
            return " → ".join(
                n.properties.get('name', str(n)) for n in nodes
            )
        except Exception:
            return str(val)
    # FalkorDB Node object
    if hasattr(val, 'properties'):
        try:
            props = val.properties
            return props.get('name', str(props))
        except Exception:
            return str(val)
    # Fallback
    try:
        return str(val)
    except Exception:
        return "[unserializable]"


def _parse_columns(header) -> list:
    """
    Extract column name strings from FalkorDB result header.
    FalkorDB returns: [[type_code, 'col_name'], ...] not ['col_name', ...]
    """
    if not header:
        return []
    columns = []
    for col in header:
        if isinstance(col, (list, tuple)) and len(col) >= 2:
            columns.append(str(col[1]))   # [1, 'function'] → 'function'
        elif isinstance(col, str):
            columns.append(col)
        else:
            columns.append(str(col))
    return columns


def _result_to_rows(result, max_rows: int = 50) -> list:
    """Convert a FalkorDB query result to a list of plain dicts."""
    columns = _parse_columns(result.header if hasattr(result, 'header') else [])
    rows = []
    for row in result.result_set[:max_rows]:
        if columns:
            rows.append({col: _safe_serialize(val) for col, val in zip(columns, row)})
        else:
            rows.append({"value": _safe_serialize(row)})
    return rows


@app.post("/query/natural")
def natural_language_query(req: NaturalQueryRequest):
    """
    Convert natural language to Cypher and execute against the graph.
    First tries template matching (fast), falls back to Gemini (smart).
    """
    from db import get_graph
    import re

    query_lower = req.query.lower().strip()
    cypher = None
    description = ""
    method = "template"

    # 1. Template matching (fast path)
    for keyword, template in QUERY_TEMPLATES.items():
        if keyword in query_lower and template:
            cypher = template["cypher"]
            description = template["description"]
            break

    # 2. Handle "blast radius of <function>" pattern
    blast_match = re.search(r'blast radius (?:of |for )?(\w+)', query_lower)
    if blast_match:
        fn = blast_match.group(1)
        cypher = f"""
        MATCH (start:Function {{name: '{fn}'}})-[:CALLS*1..3]->(affected:Function)
        RETURN DISTINCT affected.name AS function, affected.module AS module,
               affected.language AS language
        ORDER BY function
        LIMIT 30
        """
        description = f"Blast radius of {fn} (3-hop traversal)"

    # 3. "calls X" pattern
    calls_match = re.search(r'calls? (\w+)', query_lower)
    if calls_match and not cypher:
        fn = calls_match.group(1)
        cypher = f"""
        MATCH (caller:Function)-[:CALLS]->(f:Function {{name: '{fn}'}})
        RETURN caller.name AS function, caller.module AS module, caller.language AS language
        ORDER BY function
        """
        description = f"Functions that call {fn}"

    # 4. "reviewers for <module>" pattern
    reviewers_match = re.search(r'reviewers? (?:for |of )?(\w+)', query_lower)
    if reviewers_match and not cypher:
        mod = reviewers_match.group(1)
        cypher = f"""
        MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(m:Module)
        WHERE m.name = '{mod}' OR m.path CONTAINS '{mod}'
        RETURN a.name AS author, count(DISTINCT c) AS commits
        ORDER BY commits DESC LIMIT 5
        """
        description = f"Reviewers for module {mod}"

    # 5. Gemini fallback for anything unrecognized
    if not cypher:
        cypher, description = nl_to_cypher_with_gemini(req.query)
        method = "gemini"

    if not cypher:
        raise HTTPException(status_code=422, detail=f"Could not understand query: {req.query}")

    # Execute query
    try:
        graph = get_graph()
        result = graph.query(cypher)
        rows = _result_to_rows(result, max_rows=req.max_results)

        return {
            "ok": True,
            "query": req.query,
            "cypher": cypher.strip(),
            "description": description,
            "method": method,
            "row_count": len(rows),
            "rows": rows
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}\nCypher: {cypher}")


# ── Graph Visualization Data ────────────────────────────────────────────────

@app.get("/graph/data")
def graph_data(limit: int = 80):
    """
    Return all nodes and edges in vis.js format for graph visualization.
    Nodes include type, language, risk score for coloring.
    """
    from db import get_graph

    try:
        graph = get_graph()

        # Get Function nodes
        fn_result = graph.query(f"""
        MATCH (f:Function)
        RETURN f.name AS name, f.module AS module,
               f.language AS language, f.is_test AS is_test
        LIMIT {limit}
        """)

        # Get Module nodes
        mod_result = graph.query("""
        MATCH (m:Module)
        RETURN m.name AS name, m.path AS path, m.language AS language
        LIMIT 30
        """)

        # Get Author nodes
        author_result = graph.query("""
        MATCH (a:Author)
        RETURN a.name AS name, a.pseudonym_id AS pid
        LIMIT 10
        """)

        # Get AnalysisSession nodes
        session_result = graph.query("""
        MATCH (s:AnalysisSession)
        RETURN s.session_id AS sid, s.function_name AS fn,
               s.timestamp AS ts, s.risk_rank AS risk
        ORDER BY s.timestamp DESC LIMIT 10
        """)

        # Get CALLS edges
        calls_result = graph.query(f"""
        MATCH (f1:Function)-[r:CALLS]->(f2:Function)
        RETURN f1.name AS from_name, f2.name AS to_name, r.confidence AS conf
        LIMIT {limit * 2}
        """)

        # Get CONTAINS edges
        contains_result = graph.query(f"""
        MATCH (m:Module)-[:CONTAINS]->(f:Function)
        RETURN m.name AS module_name, f.name AS func_name
        LIMIT {limit}
        """)

        # Get ANALYZED edges (memory)
        analyzed_result = graph.query("""
        MATCH (s:AnalysisSession)-[:ANALYZED]->(f:Function)
        RETURN s.session_id AS sid, f.name AS fn
        LIMIT 20
        """)

        # Get AUTHORED edges
        authored_result = graph.query("""
        MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(m:Module)
        RETURN a.name AS author, m.name AS module
        LIMIT 20
        """)

        # Build nodes list
        nodes = []
        node_ids = set()

        def add_node(node_id, label, group, title="", extra=None):
            if node_id not in node_ids:
                node_ids.add(node_id)
                n = {"id": node_id, "label": label, "group": group, "title": title}
                if extra:
                    n.update(extra)
                nodes.append(n)

        for row in fn_result.result_set:
            name, module, lang, is_test = row
            short_mod = (module or "").split("/")[-1]
            lang = lang or "python"
            group = f"{lang}_test" if is_test else lang
            add_node(
                f"fn_{name}",
                name,
                group,
                f"Function: {name}\nModule: {short_mod}\nLanguage: {lang}\nTest: {is_test}",
                {"node_type": "function", "language": lang, "is_test": is_test, "module": short_mod}
            )

        for row in mod_result.result_set:
            name, path, lang = row
            lang = lang or "python"
            add_node(
                f"mod_{name}",
                f"📁 {name}",
                f"module_{lang}",
                f"Module: {name}\nPath: {path}\nLanguage: {lang}",
                {"node_type": "module", "language": lang}
            )

        for row in author_result.result_set:
            name, pid = row
            add_node(
                f"author_{pid or name}",
                f"👤 {name}",
                "author",
                f"Author: {name}",
                {"node_type": "author"}
            )

        for row in session_result.result_set:
            sid, fn, ts, risk = row
            import time
            age_days = int((time.time() - (ts or 0)) / 86400)
            add_node(
                f"session_{sid}",
                f"📊 {sid}",
                "session",
                f"Session: {sid}\nFunction: {fn}\n{age_days}d ago\nRisk rank: {risk}",
                {"node_type": "session", "function_name": fn}
            )

        # Build edges list
        edges = []
        edge_ids = set()

        def add_edge(from_id, to_id, label="", color="#aaa", dashes=False):
            eid = f"{from_id}__{to_id}__{label}"
            if eid not in edge_ids and from_id in node_ids and to_id in node_ids:
                edge_ids.add(eid)
                edges.append({
                    "from": from_id,
                    "to": to_id,
                    "label": label,
                    "color": {"color": color},
                    "dashes": dashes
                })

        for row in calls_result.result_set:
            from_name, to_name, conf = row
            add_edge(f"fn_{from_name}", f"fn_{to_name}", "calls", "#4a9eff")

        for row in contains_result.result_set:
            mod_name, func_name = row
            add_edge(f"mod_{mod_name}", f"fn_{func_name}", "contains", "#888", dashes=True)

        for row in analyzed_result.result_set:
            sid, fn = row
            add_edge(f"session_{sid}", f"fn_{fn}", "analyzed", "#f0a500")

        for row in authored_result.result_set:
            author, module = row
            # find author node
            author_nodes = [n for n in nodes if n.get('node_type') == 'author' and author in n['title']]
            if author_nodes:
                add_edge(author_nodes[0]['id'], f"mod_{module}", "contributes", "#9c6")

        return {
            "ok": True,
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "functions": len([n for n in nodes if n.get("node_type") == "function"]),
                "modules": len([n for n in nodes if n.get("node_type") == "module"]),
                "sessions": len([n for n in nodes if n.get("node_type") == "session"]),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/expand")
def graph_expand(req: GraphExpandRequest):
    """
    Expand a node: return its immediate neighbors for progressive exploration.
    """
    from db import get_graph

    try:
        graph = get_graph()
        node_name = req.node_name

        if req.node_type == "Function":
            # Get what this function calls AND what calls it
            out_q = f"""
            MATCH (f:Function {{name: $name}})-[:CALLS]->(called:Function)
            RETURN 'calls' AS direction, called.name AS name, called.module AS module,
                   called.language AS language, 'function' AS type
            LIMIT {req.max_neighbors}
            """
            in_q = f"""
            MATCH (caller:Function)-[:CALLS]->(f:Function {{name: $name}})
            RETURN 'called_by' AS direction, caller.name AS name, caller.module AS module,
                   caller.language AS language, 'function' AS type
            LIMIT {req.max_neighbors}
            """
            neighbors = []
            for q in [out_q, in_q]:
                r = graph.query(q, {'name': node_name})
                for row in r.result_set:
                    neighbors.append({
                        'direction': row[0], 'name': row[1],
                        'module': row[2], 'language': row[3], 'type': row[4]
                    })

            # Also get session history
            sessions = get_session_history(node_name, limit=3)

            return {
                "ok": True,
                "node": node_name,
                "node_type": "Function",
                "neighbors": neighbors,
                "session_history": sessions.get('sessions', [])
            }

        elif req.node_type == "Module":
            q = """
            MATCH (m:Module {name: $name})-[:CONTAINS]->(f:Function)
            RETURN f.name AS name, f.language AS language, f.is_test AS is_test
            LIMIT 30
            """
            r = graph.query(q, {'name': node_name})
            functions = [{'name': row[0], 'language': row[1], 'is_test': row[2]}
                         for row in r.result_set]
            return {"ok": True, "node": node_name, "node_type": "Module", "functions": functions}

        else:
            return {"ok": True, "node": node_name, "neighbors": []}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Memory Endpoints ────────────────────────────────────────────────────────

@app.get("/memory/history")
def memory_history(function_name: str, limit: int = 5):
    """Get analysis session history for a specific function."""
    try:
        return {"ok": True, "result": get_session_history(function_name, limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory/all")
def memory_all(limit: int = 20):
    """Get all analyzed functions with their latest session — for the memory panel."""
    try:
        from memory import get_all_analyzed_functions, get_session_count
        functions = get_all_analyzed_functions(limit)
        count = get_session_count()
        return {
            "ok": True,
            "total_sessions": count,
            "analyzed_functions": functions
        }
    except Exception as e:
        return {"ok": True, "total_sessions": 0, "analyzed_functions": []}


# ── Multi-Agent Endpoints ───────────────────────────────────────────────────

class MultiAgentRequest(BaseModel):
    function_name: str


@app.post("/agents/analyze")
def multi_agent_analyze(req: MultiAgentRequest):
    """
    Run SecurityAgent + ComplexityAgent on a function.
    Agents share state through the graph — each reads the other's findings.
    """
    try:
        from agents.orchestrator import run_multi_agent_analysis
        result = run_multi_agent_analysis(req.function_name)
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents/findings")
def get_all_agent_findings(limit: int = 50):
    """Get all findings stored by all agents — for the findings panel in UI."""
    try:
        from agents.orchestrator import get_all_findings
        findings = get_all_findings(limit)
        return {"ok": True, "findings": findings, "total": len(findings)}
    except Exception as e:
        return {"ok": True, "findings": [], "total": 0}


if __name__ == "__main__":
    print("Starting Tremor MCP Server...")
    print("Docs:       http://localhost:8765/docs")
    print("Tools:      http://localhost:8765/tools")
    print("Analyze:    POST http://localhost:8765/analyze")
    print("NL Query:   POST http://localhost:8765/query/natural")
    print("Graph:      GET  http://localhost:8765/graph/data")
    print("Memory:     GET  http://localhost:8765/memory/all")
    print("Agents:     POST http://localhost:8765/agents/analyze")
    print("Findings:   GET  http://localhost:8765/agents/findings")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")

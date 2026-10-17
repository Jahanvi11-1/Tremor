# How Tremor Uses the Graph to Decide and Act

> **For judges:** Every decision in Tremor is computed by FalkorDB using graph algorithms.
> The LLM never guesses risk, scope, or reviewers — it only writes the prose.
> This document shows the exact graph operation behind each agent decision.

---

## Decision 1 — Is this change high risk?

**Graph operation:** Native PageRank algorithm inside FalkorDB

```cypher
CALL algo.pageRank('Function', 'CALLS')
YIELD node, score
RETURN node.name AS function, score
ORDER BY score DESC
LIMIT 10
```

**What this means:**
FalkorDB runs PageRank across every Function node using CALLS edges as the graph.
Functions called by many high-importance functions get a higher score.
A hub function (called from everywhere) is the highest risk to change.

**Why the graph is essential:**
PageRank requires iterative convergence across the entire connected graph.
It cannot be expressed in a single SQL query.
FalkorDB runs this natively inside the database engine, not in Python.

**Agent decision:**
`invoke` is ranked #2 → agent flags HIGH RISK in its review.
That ranking comes from the graph, not from the function's name or the LLM.

**Verify it yourself:**
```bash
# In FalkorDB browser at http://localhost:3000
CALL algo.pageRank('Function', 'CALLS') YIELD node, score
RETURN node.name, score ORDER BY score DESC LIMIT 10
```

---

## Decision 2 — What else breaks if this function changes?

**Graph operation:** Multi-hop CALLS traversal

```cypher
MATCH p = (start:Function {name: 'invoke'})-[:CALLS*1..3]->(affected:Function)
RETURN DISTINCT affected.name, affected.module, length(p) AS hops
ORDER BY hops ASC
```

**What this means:**
Start at `invoke`. Follow CALLS edges 1, 2, or 3 hops outward.
Every reachable function is in the blast radius — it could break if `invoke` changes.

**Why the graph is essential:**
Impact cascades 3+ levels deep. Without a graph:
- SQL needs recursive self-joins for variable-depth paths
- Application code would need loops with visited-set tracking
- FalkorDB does this in one Cypher query, returning the full path object

**Agent action:**
The agent receives the exact count (e.g., 17 functions) and the hop-by-hop list.
It includes this in the review: "17 functions in blast radius across 3 hops."
The LLM cannot inflate or deflate this number — it comes from the graph.

**Verify it yourself:**
```bash
MATCH p = (f:Function {name: 'invoke'})-[:CALLS*1..3]->(g:Function)
RETURN DISTINCT g.name, g.module, length(p) AS hops
ORDER BY hops, g.name
```

---

## Decision 3 — Who should review this change?

**Graph operation:** 2-hop path traversal across 3 entity types

```cypher
MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(m:Module)
WHERE m.name = 'core' OR m.path CONTAINS 'core'
RETURN a.name, count(DISTINCT c) AS commit_count
ORDER BY commit_count DESC
LIMIT 3
```

**What this means:**
Follow: Author → authored → Commit → touched → Module
Count how many commits each author has on this module.
Rank by familiarity (commit count = domain expertise).

**Why the graph is essential:**
This is a 2-hop traversal connecting 3 node types (Author, Commit, Module).
In a relational DB: two JOINs + GROUP BY + ORDER BY across 3 tables.
In a graph: one MATCH with two hops — natural, readable, extensible.
And it can extend to: "reviewers who also touched modules that IMPORT this one" (3-hop).

**Agent action:**
Reviewer suggestions are backed by actual commit history, not by LLM guessing.
"Rowlando13 has 27 commits touching core.py" — the graph proves this.

**Verify it yourself:**
```bash
MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(m:Module {name: 'core'})
RETURN a.name, count(DISTINCT c) AS commits
ORDER BY commits DESC
```

---

## Decision 4 — How did the agent reach this conclusion?

**Graph operation:** Shortest path between two functions

```cypher
MATCH (a:Function {name: 'invoke'}), (b:Function {name: 'fail'})
RETURN shortestPath((a)-[:CALLS*]->(b)) AS path
```

**What this means:**
Find the minimum-hop call chain connecting two functions.
Returns the full path object: every node and edge between them.

**Why the graph is essential:**
Shortest path is a built-in graph primitive.
In SQL: requires recursive CTEs with path accumulation and cycle detection.
FalkorDB's `shortestPath()` handles this in one expression.

**Agent action:**
Every claim of "function X affects function Y" includes the exact path:
`invoke → make_context → format_usage → fail`
Judges can reproduce any claimed relationship by running the same query.

**Verify it yourself:**
```bash
MATCH (a:Function {name: 'invoke'}), (b:Function {name: 'fail'})
RETURN shortestPath((a)-[:CALLS*]->(b))
```

---

## Decision 5 — Has risk changed since last analysis?

**Graph operation:** Query AnalysisSession nodes ordered by timestamp

```cypher
MATCH (s:AnalysisSession {function_name: 'invoke'})
RETURN s.session_id, s.timestamp, s.risk_rank, s.blast_radius_count
ORDER BY s.timestamp DESC
LIMIT 5
```

**What this means:**
Every agent run creates an `AnalysisSession` node in the graph.
The next run queries past sessions and compares metrics.
Memory is stored in the graph — not in a file, not in RAM.

**Why the graph is essential:**
Session nodes connect to Function nodes via ANALYZED edges.
This means memory is queryable like code:
  - "Find all functions whose blast radius grew between sessions"
  - "Show me sessions where risk_rank improved after a commit"
These are multi-hop queries across code + memory in the same graph.

**Agent action:**
"Risk rank moved #3 → #2 (higher risk). Blast radius grew by 5 functions since last analysis 2 days ago."
This comparison comes from two AnalysisSession nodes in FalkorDB, not from LLM memory.

**Verify it yourself:**
```bash
MATCH (s:AnalysisSession)
RETURN s.function_name, s.session_id, s.risk_rank, s.blast_radius_count
ORDER BY s.function_name, s.timestamp DESC
```

---

## Decision 6 — Combined risk from multiple agents

**Graph operation:** Cross-agent Finding node queries

```cypher
-- ComplexityAgent stores its findings:
CREATE (fi:Finding {
    agent_type: 'complexity',
    finding_type: 'high_complexity',
    severity: 'HIGH',
    message: 'invoke is structurally complex: PageRank rank #2, 17 functions in blast radius'
})-[:FLAGGED]->(f:Function {name: 'invoke'})

-- SecurityAgent reads ComplexityAgent's findings:
MATCH (fi:Finding)-[:FLAGGED]->(f:Function {name: 'invoke'})
WHERE fi.agent_type <> 'security'
RETURN fi.agent_type, fi.severity, fi.message
```

**What this means:**
Two agents (SecurityAgent and ComplexityAgent) run independently.
Each stores findings as `Finding` nodes connected to `Function` nodes.
Each agent reads the other's findings from the graph before synthesizing.
No direct API calls between agents — the graph IS the message bus.

**Why the graph is essential:**
Shared agent state through a graph = zero coordination overhead.
Any new agent can immediately access all prior agents' findings with one Cypher query.
The graph schema naturally represents "who found what about which function."

**Agent action:**
"Function is HIGH complexity AND touches security boundaries → CRITICAL risk."
This cross-agent conclusion is only possible because both agents write to and read from the same graph.

**Verify it yourself:**
```bash
MATCH (fi:Finding)-[:FLAGGED]->(f:Function)
RETURN fi.agent_type, fi.severity, f.name, fi.message
ORDER BY CASE fi.severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END
```

---

## Graph Schema: Every Node Type and Why It Exists

```
Function  ──CALLS──►  Function        (blast radius, path finding)
   ▲                     │
CONTAINS              ANALYZED
   │                     │
Module  ──IMPORTS──►  Module        AnalysisSession  (memory)
   │                                     │
BELONGS_TO                           PREVIOUS_SESSION
   │                                     │
Project                              AnalysisSession  (history chain)

Author  ──AUTHORED──►  Commit  ──TOUCHED──►  Module
                                              (reviewer finding)

Finding  ──FLAGGED──►  Function      (multi-agent shared state)
```

**Every edge is a reasoning step the agent can traverse.**
Remove any edge type and a decision capability disappears.

---

## File Index: Where Each Decision Is Implemented

| Decision | Graph Query | Agent Code | Tool Endpoint |
|----------|-------------|------------|---------------|
| Risk ranking | `queries.py:rank_risk()` | `agent.py:gather_evidence()` | `POST /tools/rank_risk` |
| Blast radius | `queries.py:blast_radius()` | `agent.py:gather_evidence()` | `POST /tools/blast_radius` |
| Reviewer finding | `queries.py:find_reviewers()` | `agent.py:gather_evidence()` | `POST /tools/find_reviewers` |
| Path explanation | `queries.py:explain_path()` | `agent.py:gather_evidence()` | `POST /tools/explain_path` |
| Session memory | `memory.py:create_session()` | `agent.py:run_agent()` | `GET /memory/history` |
| Memory comparison | `memory.py:compare_with_previous()` | `agent.py:run_agent()` | `GET /memory/all` |
| Complexity findings | `agents/complexity_agent.py` | `agents/orchestrator.py` | `POST /agents/analyze` |
| Security findings | `agents/security_agent.py` | `agents/orchestrator.py` | `POST /agents/analyze` |
| Natural language → Cypher | `mcp_server.py:nl_to_cypher_with_gemini()` | — | `POST /query/natural` |
| Graph visualization | `mcp_server.py:graph_data()` | — | `GET /graph/data` |

---

## Criterion-by-Criterion Mapping

| Hackathon Criterion | Implementation | File |
|---------------------|---------------|------|
| **Multi-hop reasoning** | `CALLS*1..3` blast radius, `shortestPath()` path evidence | `queries.py` |
| **Graph queries as tools** | 5 Cypher queries exposed via MCP server | `mcp_server.py`, `queries.py` |
| **Tool selection through MCP** | Agent reads `/tools` manifest, calls tools by name | `agent.py` |
| **Actions based on graph** | Risk rank, reviewer list, blast count — all from graph | `agent.py`, `queries.py` |
| **Explainable results** | Every claim includes Cypher query + graph path evidence | `agent.py:build_prompt()` |
| **Remember across sessions** | `AnalysisSession` nodes in FalkorDB, compared on each run | `memory.py` |
| **Share state between agents** | `Finding` nodes readable by all agents via Cypher | `agents/base_agent.py` |
| **Connect people/projects/decisions** | `Author→Commit→Module`, `Module→Project` edges | `git_loader.py`, `project_loader.py` |
| **Follow connections across data** | Code + git + memory + projects in one graph | `loader.py`, `multi_loader.py` |

---

*All queries in this document run against the live FalkorDB instance at `localhost:6379`, graph name `tremor`.*
*Start FalkorDB: `docker compose up -d`*
*Open browser: `http://localhost:3000`*

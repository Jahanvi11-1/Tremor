# ⚡ Tremor — PR Seismograph

**Graph Hacks 2024 · Track: Agents That Act on Connected Data**

Tremor loads any code repository into FalkorDB and uses multi-hop graph traversal to analyze changes. Given a function name, an AI agent traces the blast radius, finds reviewers from git history, ranks risk with PageRank, and writes a markdown review — every claim backed by a graph path.

---

## 🧠 How the Graph Drives Every Decision

> **The graph isn't just storage — it IS the reasoning engine.**
> Every agent decision is a FalkorDB query, not an LLM guess.

| Agent Decision | Graph Operation | Why graph is required |
|---------------|----------------|----------------------|
| **Is this high risk?** | `CALL algo.pageRank('Function','CALLS')` | PageRank needs iterative convergence across entire graph |
| **What else breaks?** | `MATCH (f)-[:CALLS*1..3]->(g)` | Variable-depth traversal; SQL can't express this cleanly |
| **Who should review?** | `MATCH (a:Author)-[:AUTHORED]->(c)-[:TOUCHED]->(m)` | 3-entity 2-hop path; natural in a graph |
| **How did I get here?** | `shortestPath((a)-[:CALLS*]->(b))` | Built-in graph primitive, not possible in SQL |
| **What did I find before?** | `MATCH (s:AnalysisSession {function_name:$fn})` | Memory stored as graph nodes, queryable like code |
| **What did other agents find?** | `MATCH (fi:Finding)-[:FLAGGED]->(f:Function)` | Agents share state via graph — no direct API calls |

**Full details with runnable Cypher → [`GRAPH_DECISIONS.md`](GRAPH_DECISIONS.md)**

---

## 🚀 Quick Start (any repo in 5 minutes)

### 1. Prerequisites
- Docker Desktop running
- Python 3.10+
- Gemini API key (free at [aistudio.google.com](https://aistudio.google.com/app/apikey))

### 2. Install
```bash
git clone <this-repo>
cd graphacks

docker compose up -d                   # Start FalkorDB

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env → set GEMINI_API_KEY=your_key_here
```

### 3. Load a repository (see repo-type guide below)

### 4. Start the server + open UI
```bash
lsof -ti:8765 | xargs kill -9 2>/dev/null   # clear port if needed
python src/mcp_server.py &

open http://localhost:8765/ui                # visual graph explorer
```

---

## 📦 Loading Any Repository

**The key insight:** Always skip virtual environments (`venv`, `.venv`, `node_modules`).  
Use `PYTHON_DIRS` / `SQL_DIRS` to point at source code only.

---

### Type 1 — Simple Python repo

Structure: `src/` or all Python files at root

```bash
REPO_PATH=/path/to/your/python-repo python src/loader.py
```

If it detects venv files, be explicit:
```bash
REPO_PATH=/path/to/repo \
  PYTHON_DIRS=src \
  LANGUAGES=python \
  python src/multi_loader.py
```

---

### Type 2 — FastAPI / Django / Flask backend

Structure: `app/`, `backend/`, or `api/` folder containing Python

```bash
REPO_PATH=/path/to/project \
  PYTHON_DIRS=backend/app,backend/alembic,backend/tests \
  LANGUAGES=python \
  python src/multi_loader.py
```

**Real example — Ecovia project:**
```bash
REPO_PATH=/Users/jahanvipankajjariwala/Ecovia \
  PYTHON_DIRS=backend/app,backend/alembic,backend/tests \
  LANGUAGES=python \
  python src/multi_loader.py
```

---

### Type 3 — Monorepo (Python backend + React/JS frontend)

Structure: `backend/` (Python) + `frontend/src/` (JS/JSX)

```bash
REPO_PATH=/path/to/monorepo \
  PYTHON_DIRS=backend/app,backend \
  LANGUAGES=python \
  python src/multi_loader.py
```

> TypeScript/JavaScript parsers require `tree_sitter_languages` (unavailable for Python 3.14).  
> Python parsing always works. JS/TS files will be skipped gracefully.

---

### Type 4 — Python + SQL (database layer)

Structure: `backend/` (Python) + `db/` or `migrations/` (SQL)

```bash
REPO_PATH=/path/to/project \
  PYTHON_DIRS=backend/app \
  SQL_DIRS=db,migrations \
  LANGUAGES=python,sql \
  python src/multi_loader.py
```

---

### Type 5 — The built-in demo (pallets/click)

```bash
python src/loader.py
# Loads: 590 functions, 1767 CALLS edges, 50 commits, 4 authors
```

---

### Type 6 — Auto-detect (simplest, may pick up venv)

Let Tremor scan and detect languages automatically:
```bash
REPO_PATH=/path/to/repo python src/multi_loader.py
```

⚠️ **If it parses thousands of files** — you've hit a `venv` or `node_modules`.  
Switch to explicit dirs (Type 1–4 above).

**How to find the right dirs:**
```bash
# See top-level structure of any repo
ls /path/to/repo

# Find actual source Python files (excluding venv)
find /path/to/repo -name "*.py" \
  -not -path "*/.venv/*" \
  -not -path "*/venv/*" \
  -not -path "*/__pycache__/*" \
  | head -20
```

---

### After loading — verify it worked

```bash
python3 -c "
import sys; sys.path.insert(0,'src')
from db import get_graph; g = get_graph()
r = g.query('MATCH (m:Module) RETURN m.name, m.path ORDER BY m.path LIMIT 15')
print('Modules loaded:')
for row in r.result_set: print(f'  {row[1]}')
r2 = g.query('MATCH (f:Function) RETURN count(f) AS c')
print(f'Total functions: {r2.result_set[0][0]}')
"
```

Expected output: your project's files listed, not library files.

---

## 🖥️ Using the Visual UI

**Always open via localhost — never open the HTML file directly.**

```
http://localhost:8765/ui
```

Opening `frontend/explorer.html` as a file:// URL will fail (browser blocks API calls).

### UI walkthrough

| What | Where |
|------|-------|
| Search in natural language | Left sidebar → type anything → Enter |
| See graph nodes | Center canvas (dots = functions, squares = modules) |
| Click a node | Right panel shows details + session history |
| Generate AI review | Click node → right panel → ⚡ Generate AI Review |
| See graph evidence | Right panel → 🔬 Evidence tab |
| Run multi-agent analysis | Right panel → 🤝 Agents tab → Run Multi-Agent Analysis |
| Session memory | Left sidebar → 🧠 Memory tab |
| How graph makes decisions | Left sidebar → ⚡ How tab |
| FalkorDB browser | http://localhost:3000 |

### Quick search examples

```
high risk functions          → PageRank top 10
blast radius of <funcname>   → what breaks if you change it
find reviewers for <module>  → who owns this code
all modules                  → list every file loaded
authors                      → commit history by person
sessions                     → past analysis memory
```

---

## 🤖 Run the Agent (terminal)

```bash
source .venv/bin/activate
python src/mcp_server.py &        # must be running first

# Analyze any function from your loaded repo
python src/agent.py --function <function_name>

# Examples
python src/agent.py --function apply_eco          # Ecovia
python src/agent.py --function invoke             # click demo
python src/agent.py --function authenticate_user  # any auth function
```

Second run on the same function will show memory comparison:
```
📊 Session Memory (vs analysis earlier today):
  - 📈 Risk rank moved #4 → #2 (higher risk)
  - ⚠ Blast radius grew by 5 functions
```

---

## 🔍 FalkorDB Browser Queries

Open `http://localhost:3000`, connect to `falkordb:6379`, graph `tremor`.

```cypher
-- See everything loaded
MATCH (m:Module) RETURN m.name, m.path, m.language ORDER BY m.path

-- Risk ranking (PageRank)
CALL algo.pageRank('Function', 'CALLS') YIELD node, score
RETURN node.name, score ORDER BY score DESC LIMIT 10

-- Blast radius of any function
MATCH (f:Function {name:'apply_eco'})-[:CALLS*1..3]->(g:Function)
RETURN DISTINCT g.name, g.module

-- Who wrote what
MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(m:Module)
RETURN a.name, count(DISTINCT m) AS modules, count(DISTINCT c) AS commits
ORDER BY commits DESC

-- Session memory
MATCH (s:AnalysisSession)
RETURN s.function_name, s.session_id, s.risk_rank, s.blast_radius_count
ORDER BY s.timestamp DESC

-- Agent findings (multi-agent)
MATCH (fi:Finding)-[:FLAGGED]->(f:Function)
RETURN fi.agent_type, fi.severity, f.name, fi.message
ORDER BY fi.timestamp DESC
```

---

## 📁 Project Structure

```
graphacks/
├── docker-compose.yml          # FalkorDB + browser
├── requirements.txt            # Python deps
├── .env                        # GEMINI_API_KEY goes here
├── Dockerfile                  # For Railway deployment
├── railway.json                # Railway config
│
├── src/
│   ├── db.py                   # FalkorDB connection
│   ├── parser.py               # Original Python AST parser
│   ├── git_loader.py           # Git history + SHA256 pseudonymization
│   ├── loader.py               # Single-language loader (click demo)
│   ├── multi_loader.py         # Multi-language loader (use for any repo)
│   ├── project_loader.py       # Auto-detect project structure
│   ├── queries.py              # 5 core Cypher queries + session history
│   ├── memory.py               # Session memory (store/compare runs)
│   ├── mcp_server.py           # FastAPI MCP server (port 8765) + /ui endpoint
│   ├── agent.py                # Gemini agent loop with memory
│   │
│   ├── parsers/                # Multi-language parser system
│   │   ├── base.py             # Abstract LanguageParser interface
│   │   ├── python_parser.py    # Python AST (always works)
│   │   ├── typescript_parser.py # TS/JS (needs tree_sitter_languages)
│   │   ├── dart_parser.py      # Dart (needs tree_sitter_languages)
│   │   ├── sql_parser.py       # SQL stored procedures (always works)
│   │   └── __init__.py         # Auto-detection + factory
│   │
│   └── agents/                 # Multi-agent system
│       ├── base_agent.py       # Shared graph state interface
│       ├── security_agent.py   # Flags security-sensitive functions
│       ├── complexity_agent.py # Flags high-complexity functions (PageRank)
│       └── orchestrator.py     # Runs both, combines via graph
│
├── frontend/
│   ├── explorer.html           # Visual graph explorer (serve via /ui)
│   └── index.html              # Original PR review UI
│
├── data/
│   └── click/                  # Built-in demo repo (pallets/click)
│
├── GRAPH_DECISIONS.md          # Every graph decision with runnable Cypher
├── DEPLOY.md                   # Free deployment guide (Railway + Netlify)
├── flow.md                     # Architecture living doc
└── decision.md                 # Decision log + AI disclosure
```

---

## 🌐 Supported Languages

| Language | Parser | Status |
|----------|--------|--------|
| **Python** | Built-in AST | ✅ Always works |
| **SQL** | sqlparse | ✅ Always works |
| **TypeScript/JS** | tree-sitter | ⚠️ Needs `tree_sitter_languages` |
| **Dart/Flutter** | tree-sitter | ⚠️ Needs `tree_sitter_languages` |

`tree_sitter_languages` is not yet available for Python 3.14. Python + SQL work out of the box. TypeScript and Dart files are skipped gracefully.

---

## 🚧 Limitations

- **Static analysis only** — misses dynamic calls (`getattr`, `exec`)
- **Intra-module CALLS** — cross-module call tracking coming soon
- **Python 3.14** — tree-sitter TS/Dart parsers unavailable until library updates
- **Git depth** — loads last 50 commits; older authors won't appear as reviewers
- **Skip your venv** — always use `PYTHON_DIRS` to point at source, not site-packages

---

## 🚀 Deploy for Free

See [`DEPLOY.md`](DEPLOY.md) — Railway (backend + FalkorDB) + Netlify (frontend) = $0.

---

## AI Assistance Disclosure

Built with Kiro AI as a pair-programmer. All architectural decisions, Cypher queries, and graph model choices were reviewed and approved by the author. See [`decision.md`](decision.md) for the full log.

---

## Track

**Graph Hacks 2024 — Agents That Act on Connected Data**

Tremor demonstrates all five criteria:
- ✅ **Multi-hop reasoning** — blast radius, path evidence, PageRank
- ✅ **Graph queries as tools** — 5 Cypher queries via MCP
- ✅ **Remember across sessions** — AnalysisSession nodes in FalkorDB
- ✅ **Share state between agents** — Finding nodes readable by all agents
- ✅ **Show the path behind an answer** — every claim includes Cypher + graph path

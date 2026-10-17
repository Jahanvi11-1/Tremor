# Quick Start: Multi-Language Demo

This guide walks you through running the multi-language demo from scratch.

---

## Prerequisites

- **Docker** (for FalkorDB)
- **Python 3.8+** (Python 3.14 used in development)
- **Git** (for git history tracking)

---

## Step-by-Step Instructions

### Step 1: Start FalkorDB

```bash
# Navigate to project directory
cd /Users/jahanvipankajjariwala/development/graphacks

# Start FalkorDB with Docker Compose
docker compose up -d

# Verify it's running
docker ps | grep falkordb
```

Expected output: You should see `falkordb/falkordb` container running on port 6379.

---

### Step 2: Set Up Python Environment

```bash
# Create virtual environment (if not already created)
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# OR
.venv\Scripts\activate     # On Windows

# Install dependencies
pip install -r requirements.txt
```

Expected output: All packages installed successfully (falkordb, python-dotenv, gitpython, sqlparse, etc.)

---

### Step 3: Verify Demo Repository

```bash
# Check demo repository structure
ls -la demo-multi-lang/

# Should show:
# backend/
#   ├── api.py         (Python FastAPI endpoints)
#   └── database.py    (Python database layer)
# db/
#   └── procedures.sql (PostgreSQL stored procedures)
```

---

### Step 4: Load Multi-Language Repository

```bash
# Load the demo repository into FalkorDB
REPO_PATH=./demo-multi-lang python src/multi_loader.py
```

**Expected output:**
```
TREMOR: Multi-Language Code Analysis
============================================================
Repository: ./demo-multi-lang
Languages:  Auto-detect

Language Detection Results:
------------------------------------------------------------
  python       (.py   ):    2 files
  sql          (.sql  ):    1 files
------------------------------------------------------------
Detected languages: python, sql

✓ Created python parser
✓ Created sql parser

PARSING COMPLETE
============================================================
Total modules:   3
Total functions: 13

Breakdown by language:
  python      :    2 modules,     9 functions
  sql         :    1 modules,     4 functions

LOADING INTO FALKORDB
============================================================
✓ Loaded 3 modules
✓ Loaded 13 functions
✓ Created 13 CONTAINS edges
✓ Created 2 IMPORTS edges
✓ Created 8 CALLS edges (intra-module)

GRAPH STATISTICS
============================================================
Modules:        3
Functions:      13
  (tests):      0
Commits:        1
Authors:        1 (pseudonymized)

Modules by language:
  python      :    2 modules
  sql         :    1 modules

Functions by language:
  python      :     9 functions
  sql         :     4 functions

✓ Multi-language graph loaded successfully!
```

---

### Step 5: Explore the Graph (Option 1: FalkorDB Browser)

```bash
# Open FalkorDB browser
open http://localhost:3000

# OR visit in your browser:
# http://localhost:3000
```

#### Try These Queries in the Browser:

**1. View all modules with their languages:**
```cypher
MATCH (m:Module)
RETURN m.name, m.language, m.path
```

**2. View all functions with their languages:**
```cypher
MATCH (f:Function)
RETURN f.name, f.language, f.module, f.start_line
ORDER BY f.language, f.name
```

**3. View Python functions only:**
```cypher
MATCH (f:Function {language:'python'})
RETURN f.name, f.module
ORDER BY f.name
```

**4. View SQL functions (stored procedures):**
```cypher
MATCH (f:Function {language:'sql'})
RETURN f.name, f.module, f.start_line, f.end_line
```

**5. View function call relationships:**
```cypher
MATCH (f1:Function)-[:CALLS]->(f2:Function)
RETURN f1.name, f1.language, f2.name, f2.language
```

**6. View module imports:**
```cypher
MATCH (m1:Module)-[:IMPORTS]->(m2:Module)
RETURN m1.name, m1.language, m2.name, m2.language
```

**7. Count functions by language:**
```cypher
MATCH (f:Function)
RETURN f.language AS language, count(f) AS count
ORDER BY count DESC
```

**8. Find all SQL procedures and their calls:**
```cypher
MATCH (sql:Function {language:'sql'})-[:CALLS]->(called:Function)
RETURN sql.name AS procedure, 
       collect(called.name) AS calls_to
```

---

### Step 6: Explore the Graph (Option 2: Command Line)

```bash
# Connect to FalkorDB via redis-cli
docker exec -it graphacks-falkordb-1 redis-cli

# In redis-cli, run Cypher queries:
GRAPH.QUERY tremor "MATCH (m:Module) RETURN m.name, m.language"
GRAPH.QUERY tremor "MATCH (f:Function) RETURN f.name, f.language LIMIT 10"
```

---

### Step 7: Use the MCP Server (Optional)

```bash
# In a new terminal, activate venv
source .venv/bin/activate

# Start MCP server
python src/mcp_server.py

# Expected output:
# INFO:     Started server process
# INFO:     Uvicorn running on http://0.0.0.0:8765
```

#### Test MCP Tools:

```bash
# In another terminal, test blast radius for a Python function
curl -X POST http://localhost:8765/tools/blast_radius \
  -H "Content-Type: application/json" \
  -d '{"function_name": "authenticate", "max_hops": 2}'

# Test find_reviewers for database.py module
curl -X POST http://localhost:8765/tools/find_reviewers \
  -H "Content-Type: application/json" \
  -d '{"module_name": "database"}'
```

---

### Step 8: Use the AI Agent (Optional)

Make sure you have a Gemini API key in your `.env` file:

```bash
# Check .env file
cat .env | grep GEMINI_API_KEY

# If not set, add it:
echo "GEMINI_API_KEY=your-key-here" >> .env
```

Run the agent:

```bash
# Analyze a function
python src/agent.py --function authenticate

# Expected output: Markdown review with blast radius, reviewers, and risk analysis
```

---

### Step 9: Use the Web UI (Optional)

```bash
# Open the single-file UI
open frontend/index.html

# OR visit in browser:
# file:///Users/jahanvipankajjariwala/development/graphacks/frontend/index.html
```

1. Enter function name: `authenticate`
2. Click "Generate Review"
3. View AI-generated review with graph evidence

---

## What's in the Demo Repo?

### Python Files (`backend/`)

**`api.py`** (9 LOC, 3 functions):
- `authenticate()` — Validates credentials
- `get_user_profile()` — Fetches user data
- `health_check()`, `login()`, `get_user()` — FastAPI endpoints

**`database.py`** (6 functions):
- `get_connection()` — Database connection
- `check_credentials()` — Calls SQL `authenticate_user` procedure
- `fetch_user()` — Calls SQL `get_user_profile` function
- `save_user()` — Inserts user into database

### SQL Files (`db/`)

**`procedures.sql`** (4 procedures/functions):
- `authenticate_user()` — Validates user credentials
- `validate_password()` — Password hashing check
- `log_auth_attempt()` — Logs authentication attempts
- `get_user_profile()` — Returns user profile

### What Tremor Extracts:

- **3 modules**: 2 Python files + 1 SQL file
- **13 functions**: 9 Python + 4 SQL
- **8 CALLS edges**: Intra-module function calls
- **2 IMPORTS edges**: Python `database.py` imports logic
- **Language tags**: Every node has `language` property

---

## Testing with Your Own Multi-Language Repo

### Option A: Python + SQL Repo
```bash
REPO_PATH=/path/to/your/python-sql-project python src/multi_loader.py
```

### Option B: Specify Source Directories
```bash
REPO_PATH=/path/to/your/fullstack-app \
  PYTHON_DIRS=backend,api,server \
  SQL_DIRS=db,migrations,sql \
  python src/multi_loader.py
```

### Option C: Force Specific Languages
```bash
REPO_PATH=/path/to/your/repo \
  LANGUAGES=python,sql \
  python src/multi_loader.py
```

---

## Troubleshooting

### Issue: "tree_sitter_languages not installed"
**This is expected for Python 3.14.** TypeScript and Dart parsing will be skipped, but Python and SQL work fine.

**Solution**: This is not an error — system gracefully falls back to supported languages.

---

### Issue: "InvalidGitRepositoryError"
**Cause**: Demo folder is not a git repository.

**Solution**:
```bash
cd demo-multi-lang
git init
git config user.email "demo@example.com"
git config user.name "Demo User"
git add -A
git commit -m "Initial commit"
cd ..
REPO_PATH=./demo-multi-lang python src/multi_loader.py
```

---

### Issue: "No supported languages detected"
**Cause**: No `.py` or `.sql` files found.

**Solution**: 
- Check file extensions
- Specify source directories: `PYTHON_DIRS=src,app`
- Use absolute path: `REPO_PATH=/full/path/to/repo`

---

### Issue: "Connection refused" when querying FalkorDB
**Cause**: FalkorDB not running.

**Solution**:
```bash
docker compose up -d
docker ps | grep falkordb
```

---

### Issue: SQL functions not extracted
**Cause**: SQL file doesn't contain `CREATE FUNCTION` or `CREATE PROCEDURE`.

**Note**: Plain SELECT/INSERT statements are not extracted (only reusable procedures/functions).

**Solution**: Check that SQL file has:
```sql
CREATE OR REPLACE FUNCTION my_function(...)
RETURNS ... AS $$
BEGIN
  ...
END;
$$ LANGUAGE plpgsql;
```

---

## Clean Up

```bash
# Stop FalkorDB
docker compose down

# Deactivate Python environment
deactivate

# Clear graph data (optional)
docker compose down -v  # Remove volumes
```

---

## Next Steps

1. **Load your own repo**: Try with a real Python + SQL project
2. **Explore queries**: Check `MULTI_LANGUAGE.md` for advanced Cypher examples
3. **Add more languages**: When tree_sitter_languages supports Python 3.14
4. **Extend the system**: Add Go, Rust, Java parsers (see `MULTI_LANGUAGE.md` guide)

---

## Summary

You've successfully:
- ✅ Started FalkorDB
- ✅ Loaded a multi-language repo (Python + SQL)
- ✅ Queried the graph by language
- ✅ Verified cross-language imports and calls
- ✅ Explored the unified graph schema

**The multi-language foundation is ready for your real projects!** 🚀

# Multi-Language Demo Repository

This is a sample multi-language repository demonstrating Tremor's ability to parse **Python and SQL** in the same graph.

## Project Structure

```
demo-multi-lang/
├── backend/          # Python backend
│   ├── api.py        # FastAPI REST endpoints
│   └── database.py   # Database access layer
└── db/               # SQL database
    └── procedures.sql # PostgreSQL stored procedures
```

## What's Inside

### Python Backend (`backend/`)

**File: `api.py`** (FastAPI web service)
- `authenticate(username, password)` — Validates user credentials
- `get_user_profile(user_id)` — Fetches user data
- `health_check()` — Health endpoint
- `login(username, password)` — POST /login
- `get_user(user_id)` — GET /users/{user_id}

**File: `database.py`** (Database layer)
- `get_connection()` — PostgreSQL connection
- `check_credentials(username, password)` — Calls SQL procedure
- `fetch_user(user_id)` — Calls SQL function
- `save_user(user_data)` — Inserts new user

### SQL Database (`db/`)

**File: `procedures.sql`** (PostgreSQL stored procedures)
- `authenticate_user(username, password)` — Authenticates user
- `validate_password(plain, hashed)` — Password validation
- `log_auth_attempt(username, success)` — Logs auth attempts
- `get_user_profile(user_id)` — Returns user data

## Tech Stack

- **Backend**: Python 3.x, FastAPI
- **Database**: PostgreSQL
- **ORM**: Direct SQL (psycopg2)

## What Tremor Extracts

When you run `REPO_PATH=./demo-multi-lang python src/multi_loader.py`, Tremor extracts:

### Modules (3)
- `backend/api.py` (language: `python`)
- `backend/database.py` (language: `python`)
- `db/procedures.sql` (language: `sql`)

### Functions (13)
- **9 Python functions**: authenticate, get_user_profile, health_check, login, get_user, get_connection, check_credentials, fetch_user, save_user
- **4 SQL procedures**: authenticate_user, validate_password, log_auth_attempt, get_user_profile

### Relationships
- **IMPORTS**: `api.py` → `database.py`
- **CALLS**: Intra-module function calls (e.g., `authenticate()` → `database.check_credentials()`)
- **Language tags**: Every node has `language` property for filtering

## How to Run

### Quick Start (One Command)
```bash
# From project root
./run-multilang-demo.sh
```

### Manual Steps
```bash
# 1. Start FalkorDB
docker compose up -d

# 2. Activate Python environment
source .venv/bin/activate

# 3. Load this demo repo
REPO_PATH=./demo-multi-lang python src/multi_loader.py
```

## Expected Output

```
TREMOR: Multi-Language Code Analysis
============================================================
Repository: ./demo-multi-lang

Language Detection Results:
------------------------------------------------------------
  python       (.py   ):    2 files
  sql          (.sql  ):    1 files
------------------------------------------------------------
Detected languages: python, sql

PARSING COMPLETE
============================================================
Total modules:   3
Total functions: 13

Breakdown by language:
  python      :    2 modules,     9 functions
  sql         :    1 modules,     4 functions

GRAPH STATISTICS
============================================================
Modules:        3
Functions:      13
  (tests):      0

Functions by language:
  python      :     9 functions
  sql         :     4 functions

✓ Multi-language graph loaded successfully!
```

## Query Examples

Open FalkorDB Browser at http://localhost:3000 and try:

### View all modules
```cypher
MATCH (m:Module)
RETURN m.name, m.language, m.path
```

### View Python functions
```cypher
MATCH (f:Function {language:'python'})
RETURN f.name, f.module
ORDER BY f.name
```

### View SQL procedures
```cypher
MATCH (f:Function {language:'sql'})
RETURN f.name, f.module, f.start_line, f.end_line
```

### View function calls
```cypher
MATCH (f1:Function)-[:CALLS]->(f2:Function)
RETURN f1.name AS caller, 
       f1.language AS caller_lang,
       f2.name AS called,
       f2.language AS called_lang
```

### Count by language
```cypher
MATCH (f:Function)
RETURN f.language AS language, count(f) AS count
ORDER BY count DESC
```

### Find authentication-related functions
```cypher
MATCH (f:Function)
WHERE f.name CONTAINS 'auth'
RETURN f.name, f.language, f.module
```

## Extending This Demo

Want to add more languages?

### Add TypeScript Frontend
```typescript
// frontend/app.ts
import { authenticate } from '../backend/api';

async function login(username: string, password: string) {
    const result = await authenticate(username, password);
    return result;
}
```

Then run:
```bash
REPO_PATH=./demo-multi-lang LANGUAGES=python,typescript,sql python src/multi_loader.py
```

### Add Dart/Flutter Mobile
```dart
// mobile/lib/auth.dart
import 'package:http/http.dart' as http;

Future<bool> authenticate(String username, String password) async {
  final response = await http.post('/login', body: {
    'username': username,
    'password': password,
  });
  return response.statusCode == 200;
}
```

Then run:
```bash
REPO_PATH=./demo-multi-lang \
  PYTHON_DIRS=backend \
  TYPESCRIPT_DIRS=frontend \
  DART_DIRS=mobile \
  SQL_DIRS=db \
  python src/multi_loader.py
```

## Use Cases

This demo shows Tremor's ability to:

1. **Parse multiple languages** in one pass
2. **Track cross-language dependencies** (Python calls SQL procedures)
3. **Filter by language** in Cypher queries
4. **Analyze blast radius** across languages
5. **Find reviewers** for mixed-language modules

## Real-World Application

Use Tremor with your production repos:

- **Full-stack monorepo**: Python backend + React frontend + PostgreSQL
- **Microservices**: Multiple languages (Python, Go, Node.js) + shared SQL
- **Mobile + backend**: Flutter app + Python API + SQL database
- **Data pipeline**: SQL transforms + Python ETL + TypeScript dashboard

## Learn More

- **Full guide**: `../QUICKSTART_MULTILANG.md`
- **Advanced examples**: `../MULTI_LANGUAGE.md`
- **Main README**: `../README.md`

---

**This demo was created to showcase Tremor's multi-language graph analysis capabilities for Graph Hacks 2024.**

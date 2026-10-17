# 🚀 Run the Multi-Language Demo in 3 Steps

## Option 1: One-Line Command (Easiest)

```bash
./run-multilang-demo.sh
```

That's it! The script does everything automatically.

---

## Option 2: Manual Steps (3 minutes)

### Step 1: Start FalkorDB
```bash
docker compose up -d
```

### Step 2: Activate Python Environment
```bash
source .venv/bin/activate
```

### Step 3: Load Demo Repo
```bash
REPO_PATH=./demo-multi-lang python src/multi_loader.py
```

---

## ✅ What Gets Loaded

- **3 modules**: 2 Python files + 1 SQL file
- **13 functions**: 9 Python + 4 SQL procedures
- **Language tags**: Every node has `language` property
- **Cross-language links**: Python → SQL imports tracked

---

## 🔍 Explore the Graph

### Open FalkorDB Browser
```bash
open http://localhost:3000
```

### Try These Queries

**View all modules:**
```cypher
MATCH (m:Module)
RETURN m.name, m.language, m.path
```

**Count functions by language:**
```cypher
MATCH (f:Function)
RETURN f.language, count(f) AS count
ORDER BY count DESC
```

**View SQL procedures:**
```cypher
MATCH (f:Function {language:'sql'})
RETURN f.name, f.module
```

**View Python functions:**
```cypher
MATCH (f:Function {language:'python'})
RETURN f.name, f.module
ORDER BY f.name
```

**View function calls:**
```cypher
MATCH (f1:Function)-[:CALLS]->(f2:Function)
RETURN f1.name, f1.language, f2.name, f2.language
```

---

## 📁 Demo Repository Contents

```
demo-multi-lang/
├── backend/
│   ├── api.py         ← 5 Python functions (FastAPI endpoints)
│   └── database.py    ← 4 Python functions (DB layer)
└── db/
    └── procedures.sql ← 4 SQL procedures (PostgreSQL)
```

**Total**: 13 functions across 2 languages!

---

## 🎯 Try With Your Own Repo

### Python + SQL Project
```bash
REPO_PATH=/path/to/your/project python src/multi_loader.py
```

### Specify Source Directories
```bash
REPO_PATH=/your/repo \
  PYTHON_DIRS=backend,api \
  SQL_DIRS=db,migrations \
  python src/multi_loader.py
```

### Force Specific Languages
```bash
REPO_PATH=/your/repo LANGUAGES=python,sql python src/multi_loader.py
```

---

## 📚 Full Documentation

- **Quick Start**: `QUICKSTART_MULTILANG.md` — Step-by-step guide with screenshots
- **Multi-Language Guide**: `MULTI_LANGUAGE.md` — Complete reference
- **Demo README**: `demo-multi-lang/README.md` — Demo repo details

---

## 🐛 Troubleshooting

**Issue**: "tree_sitter_languages not installed"  
**Fix**: This is expected for Python 3.14. Python and SQL still work!

**Issue**: "InvalidGitRepositoryError"  
**Fix**: Demo folder needs git:
```bash
cd demo-multi-lang
git init && git add -A && git commit -m "Init"
cd .. && REPO_PATH=./demo-multi-lang python src/multi_loader.py
```

**Issue**: "Connection refused"  
**Fix**: Start FalkorDB: `docker compose up -d`

---

## 🎉 Success Looks Like

```
✓ Created python parser
✓ Created sql parser
✓ Loaded 3 modules
✓ Loaded 13 functions
✓ Created 13 CONTAINS edges
✓ Created 2 IMPORTS edges
✓ Created 8 CALLS edges

Modules by language:
  python      :    2 modules
  sql         :    1 modules

Functions by language:
  python      :     9 functions
  sql         :     4 functions

✓ Multi-language graph loaded successfully!
```

---

**You're ready to analyze multi-language codebases with Tremor!** 🚀

# Multi-Language Support Guide

Tremor now supports **Python, TypeScript/JavaScript, Dart/Flutter, and SQL** repositories!

## Quick Start

### Auto-detect all languages
```bash
REPO_PATH=./path/to/your/repo python src/multi_loader.py
```

### Specify languages
```bash
REPO_PATH=./my-app LANGUAGES=python,sql python src/multi_loader.py
```

### Specify source directories per language
```bash
REPO_PATH=./my-fullstack-app \
  PYTHON_DIRS=backend,api \
  TYPESCRIPT_DIRS=frontend,web \
  DART_DIRS=mobile \
  SQL_DIRS=db,migrations \
  python src/multi_loader.py
```

---

## Supported Languages

| Language | Parser | File Extensions | Status |
|----------|--------|-----------------|--------|
| **Python** | Built-in AST | `.py` | ✅ Always available |
| **TypeScript/JavaScript** | tree-sitter | `.ts`, `.tsx`, `.js`, `.jsx` | ⚠️ Requires `tree_sitter_languages` |
| **Dart/Flutter** | tree-sitter | `.dart` | ⚠️ Requires `tree_sitter_languages` |
| **SQL** | sqlparse | `.sql` | ✅ Always available |

**Note**: `tree_sitter_languages` is currently unavailable for Python 3.14. The system gracefully skips TypeScript and Dart if the dependency is missing. Python and SQL parsing work out of the box.

---

## Graph Schema

All languages use the **same unified schema**:

### Nodes
- **Module**: Source file
  - Properties: `path`, `name`, `language` ← NEW!
- **Function**: Callable unit (function/method/procedure)
  - Properties: `name`, `module`, `language` ← NEW!, `is_test`, `start_line`, `end_line`
- **Commit**: Git commit (unchanged)
- **Author**: Pseudonymized contributor (unchanged)

### Edges
- **CONTAINS**: Module → Function (unchanged)
- **IMPORTS**: Module → Module (now works cross-language!)
- **CALLS**: Function → Function (unchanged, intra-module)
- **TOUCHED**: Commit → Module (unchanged)
- **AUTHORED**: Author → Commit (unchanged)

---

## Example Queries

### Count functions by language
```cypher
MATCH (f:Function)
RETURN f.language AS language, count(f) AS count
ORDER BY count DESC
```

### Find Python backend functions
```cypher
MATCH (m:Module {language:'python'})-[:CONTAINS]->(f:Function)
WHERE m.path CONTAINS 'backend'
RETURN f.name, f.module
```

### Find SQL procedures called by Python
```cypher
MATCH (py:Function {language:'python'})-[:CALLS]->(sql:Function {language:'sql'})
RETURN py.name AS python_function, sql.name AS sql_procedure
```

### Cross-language imports
```cypher
MATCH (m1:Module)-[:IMPORTS]->(m2:Module)
WHERE m1.language <> m2.language
RETURN m1.name, m1.language, m2.name, m2.language
```

### Blast radius across all languages
```cypher
MATCH (f:Function {name:'authenticate'})-[:CALLS*1..3]->(g:Function)
RETURN DISTINCT g.name, g.language, g.module, length(path) AS hops
ORDER BY hops, g.name
```

---

## Parser Architecture

```
src/parsers/
├── base.py              # Abstract LanguageParser interface
├── python_parser.py     # Python AST parser (no dependencies)
├── typescript_parser.py # TypeScript/JS parser (tree-sitter)
├── dart_parser.py       # Dart/Flutter parser (tree-sitter)
├── sql_parser.py        # SQL parser (sqlparse)
└── __init__.py          # Auto-detection + factory
```

### Key Design Principles

1. **Plugin architecture**: Each language implements the same `LanguageParser` interface
2. **Unified output**: All parsers return `ModuleInfo` and `FunctionInfo` objects
3. **Graceful degradation**: Missing dependencies don't crash the system
4. **Language-agnostic graph**: Same schema for all languages

---

## What Each Parser Extracts

### Python Parser (`python_parser.py`)
- **Modules**: Python files (`.py`)
- **Functions**: `def`, `async def`, methods in classes
- **Imports**: `import foo`, `from foo import bar`
- **Calls**: Function calls extracted from AST
- **Parameters**: Function arguments
- **Return types**: Type annotations if present

### TypeScript Parser (`typescript_parser.py`)
- **Modules**: TypeScript/JavaScript files (`.ts`, `.tsx`, `.js`, `.jsx`)
- **Functions**: `function`, arrow functions (`const foo = () => {}`), class methods
- **Imports**: `import foo from 'bar'`, `require('foo')`
- **Calls**: Function/method calls extracted from AST
- **Exports**: Named exports for metadata

### Dart Parser (`dart_parser.py`)
- **Modules**: Dart files (`.dart`)
- **Functions**: Top-level functions, class methods
- **Imports**: `import 'package:foo/bar.dart'`
- **Calls**: Function/method calls extracted from AST
- **Classes**: Class names for metadata
- **Fallback**: Regex-based parsing when tree-sitter unavailable

### SQL Parser (`sql_parser.py`)
- **Modules**: SQL files (`.sql`)
- **Functions**: `CREATE FUNCTION`, `CREATE PROCEDURE`
- **Imports**: Table references from `FROM`, `JOIN`, `INSERT INTO`, `UPDATE`
- **Calls**: Procedure calls (`CALL`, `EXEC`), function calls in queries
- **Parameters**: Procedure/function parameters

---

## Adding a New Language

Want to add Go, Rust, Java, C++, or another language?

### Step 1: Create Parser

Create `src/parsers/your_language_parser.py`:

```python
from .base import LanguageParser, FunctionInfo, ModuleInfo
from pathlib import Path
from typing import List, Optional

class YourLanguageParser(LanguageParser):
    def get_file_extensions(self) -> List[str]:
        return ['.ext']  # e.g., ['.go'], ['.rs']
    
    def get_language_name(self) -> str:
        return 'your_language'  # e.g., 'go', 'rust'
    
    def parse_file(self, file_path: Path) -> Optional[ModuleInfo]:
        # Your parsing logic here
        # Return ModuleInfo with language='your_language'
        pass
```

### Step 2: Register Parser

Edit `src/parsers/__init__.py`:

```python
from .your_language_parser import YourLanguageParser

PARSER_REGISTRY: Dict[str, type] = {
    'python': PythonParser,
    'typescript': TypeScriptParser,
    'dart': DartParser,
    'sql': SQLParser,
    'your_language': YourLanguageParser,  # ← Add this line
}
```

### Step 3: Test

```bash
REPO_PATH=./path/to/your/language/repo python src/multi_loader.py
```

The graph schema and all queries already work with your new language — no changes needed!

---

## Migration from Single-Language

### Old Approach (Python only)
```bash
REPO_PATH=./python-repo python src/loader.py
```

### New Approach (Multi-language)
```bash
REPO_PATH=./mixed-repo python src/multi_loader.py
```

**Both loaders create the same graph schema** (module.py just doesn't set `language` property). The old loader still works for Python-only repos and has minimal dependencies.

---

## Demo: Multi-Language Repository

A sample multi-language repo is included in `demo-multi-lang/`:

```
demo-multi-lang/
├── backend/
│   ├── api.py         (Python FastAPI endpoints)
│   └── database.py    (Python database layer)
└── db/
    └── procedures.sql (PostgreSQL stored procedures)
```

### Load it:
```bash
REPO_PATH=./demo-multi-lang python src/multi_loader.py
```

### Output:
- 3 modules: 2 Python + 1 SQL
- 13 functions: 9 Python + 4 SQL
- Cross-language imports detected
- All functions have `language` property in graph

### Query it:
```bash
# In FalkorDB browser (http://localhost:3000)
MATCH (m:Module)
RETURN m.name, m.language, m.path

MATCH (f:Function)
WHERE f.language = 'sql'
RETURN f.name, f.module
```

---

## Troubleshooting

### "tree_sitter_languages not installed"
- Expected for Python 3.14 (package not yet available)
- Python and SQL parsing will continue to work
- TypeScript and Dart files will be skipped

**Solution**: Wait for `tree_sitter_languages` to support Python 3.14, or downgrade Python to 3.11-3.13.

### "No supported languages detected"
- Check that your repo has files with supported extensions
- Try specifying `LANGUAGES=python,sql` explicitly
- Check that source directories exist

### "0 functions extracted from SQL file"
- SQL parser expects `CREATE FUNCTION` or `CREATE PROCEDURE`
- Plain SELECT/INSERT/UPDATE statements are not extracted (they're not reusable functions)
- Table references from these queries are still extracted as imports

### Cross-language IMPORTS not created
- Import matching is best-effort and may fail for ambiguous names
- Only creates edges if both modules exist in the parsed set
- External dependencies (npm packages, pip packages) are intentionally ignored

---

## Limitations

### Current Limitations
- **Static analysis only**: No runtime tracing
- **Intra-module CALLS only**: Cross-module call graph requires import resolution (future work)
- **Tree-sitter dependencies**: TypeScript and Dart unavailable for Python 3.14
- **Best-effort imports**: Cross-language dependency resolution is approximate

### Not Supported (Yet)
- **Generated code**: Protobuf, GraphQL codegen, etc.
- **Dynamic imports**: `importlib.import_module()`, `import()`
- **Macros/templates**: C macros, Jinja templates
- **Runtime calls**: Reflection, eval, getattr

---

## Roadmap

### Short-term
- [ ] Support tree_sitter_languages on Python 3.14 when available
- [ ] Test with real-world multi-language repos
- [ ] Add more file extensions (`.mjs`, `.cjs`, etc.)

### Medium-term
- [ ] Cross-module CALLS edges (requires import resolution)
- [ ] More languages: Go, Rust, Java, C#, Ruby, PHP
- [ ] Better SQL parsing (CTEs, subqueries, window functions)
- [ ] Cross-language type analysis

### Long-term
- [ ] IDE integration (VSCode extension)
- [ ] Real-time graph updates (file watcher)
- [ ] Hybrid static + dynamic analysis
- [ ] Support for generated code and build systems

---

## Contributing

Want to add a language or improve a parser?

1. Fork the repo
2. Create your parser in `src/parsers/`
3. Add tests
4. Update this documentation
5. Submit a PR

All parsers must implement the `LanguageParser` interface and return `ModuleInfo`/`FunctionInfo` objects.

---

## License

Same as main project (see root README.md)

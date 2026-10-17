# Tremor: Decision Log

---

## Step 1: Environment Setup

**Decision:** Use FalkorDB official Docker image; clone `click` repo as target  
**Options considered:**
- FalkorDB Docker vs local build (chose Docker: faster, handles arm64)
- Target repo: `flask`, `requests`, `click` (chose `click`: small, clean structure, <500 functions)

**Why chosen:**  
- Docker image works on M1 Mac with no extra config
- `click` has clear test structure, pure Python, known issue history for backtest

**Trade-offs:**  
- Docker adds slight startup time vs native binary
- `click` is small — blast radius demo may be less dramatic than larger repo, but fits 16-hour constraint

---

---

## Step 2: Python Connection to FalkorDB

**Decision:** Use `falkordb` Python driver (v1.0.9); virtual env for dependencies  
**Options considered:**
- System-wide pip install vs venv (chose venv: avoids externally-managed-environment error, keeps project isolated)
- Connection pooling now vs later (chose simple connection: premature for single-user tool)

**Why chosen:**  
- FalkorDB driver is the official client; includes graph query interface
- Virtual env required by macOS Python security (PEP 668)

**Trade-offs:**  
- Must activate `.venv` before running any script (adds setup step but standard practice)

---

## Step 3: Graph Schema + AST Parser

**Decision:** Python AST for static analysis; intra-module CALLS only in Step 3  
**Options considered:**
- AST vs regex parsing (chose AST: accurate, structured, handles nested scopes)
- Track all calls vs intra-module only (chose intra-module first: simpler, covers 80% of blast radius; cross-module can be added in Step 5 if time permits)
- CALLS edge direction: caller→callee vs bidirectional (chose caller→callee: natural for traversal, matches "X calls Y" semantics)

**Why chosen:**  
- AST gives precise line numbers, function boundaries, and call sites
- Intra-module calls are most impactful for blast radius (same file changes are highest risk)
- `confidence` property (=1.0 for static analysis) leaves room for heuristic scoring later

**Trade-offs:**  
- Static analysis misses: `getattr`, `exec`, dynamic imports, decorator-generated methods
- No cross-module CALLS yet (e.g., `core.py:foo()` calling `utils.py:bar()`) — impacts cross-file blast radius
- Test function detection is heuristic (`test_` prefix + path check) — may miss some tests

**Judge disclosure:**  
- Documented limitations in `src/parser.py` docstring
- CALLS edges are approximations; real call graph includes runtime behavior we can't capture statically

---

## Step 4: Git History + Pseudonymized Authors

**Decision:** SHA256 hash for email pseudonymization; TOUCHED at module-level only  
**Options considered:**
- Email hashing: SHA256 vs UUID mapping (chose SHA256: deterministic, no need to store mapping, one-way secure)
- TOUCHED granularity: module-level vs function-level (chose module: simpler, git diffs don't reliably give function-level changes for all commits)
- Commit depth: 50 vs 100 vs full history (chose 50: enough for reviewer suggestions, fast to load)

**Why chosen:**  
- SHA256 is cryptographically secure, irreversible, and consistent (same email always produces same pseudonym_id)
- Module-level TOUCHED edges are sufficient for "who has worked on this file" queries
- 50 commits covers recent contributors without overloading the graph

**Trade-offs:**  
- Cannot identify authors by email later (by design for privacy)
- Function-level git blame would be more precise but requires parsing diffs (complex, out of scope for 16 hours)
- Limited history depth means very old contributors won't appear in "find reviewers"

**Privacy guarantee:**  
- Author emails are never stored
- SHA256 hash cannot be reversed to reveal email
- Author names are stored (less sensitive, often public in git logs)

---

## Step 5: Core Cypher Queries

**Decision:** Inline variable hops (f-string) rather than parameterized; shortestPath in RETURN clause  
**Options considered:**
- Parameterized hop count (`$hops`) vs f-string inline (FalkorDB rejected parameterized variable-length paths — required f-string workaround)
- shortestPath in MATCH vs RETURN (FalkorDB only supports it in WITH/RETURN — documented quirk)
- PageRank vs in-degree centrality (PageRank works natively via `algo.pageRank()`; kept in-degree as fallback)

**Why chosen:**  
- All 5 queries run as Cypher inside FalkorDB — no Python loops over graph data
- PageRank via `algo.pageRank('Function','CALLS')` is one-line native algorithm execution
- `find_tests` uses reverse traversal — a graph-native pattern that would need recursive SQL CTEs otherwise

**Trade-offs:**  
- `find_tests` returns 0 for `invoke` — the CALLS graph is intra-module only, so test files don't have CALLS edges into core functions yet. Cross-module CALLS would fix this but was out of scope for Step 3.
- `explain_path` returns no path for some pairs — only works when a direct CALLS chain exists
- PageRank scores are relative (not absolute risk percentages) — needs normalization for display

**Judge explanations (Cypher):**
- `blast_radius`: `MATCH (f)-[:CALLS*1..3]->(g)` — multi-hop traversal, impossible in one SQL query
- `find_tests`: reverse reachability from test nodes — graph direction makes this natural
- `find_reviewers`: 2-hop `Author→Commit→Module` — joins across 3 entity types in one query
- `rank_risk`: `CALL algo.pageRank(...)` — graph algorithm inside database engine, not Python
- `explain_path`: `shortestPath(a-[:CALLS*]->b)` — built-in graph primitive

---

## AI Assistance Log

**Step 1:**  
- AI generated: `docker-compose.yml`, `.env.example`, `.gitignore`, `flow.md`, `decision.md`
- Human reviewed: Docker started successfully; click repo cloned

**Step 2:**  
- AI generated: `requirements.txt`, `src/db.py`, venv setup
- Human reviewed: Connection test successful; FalkorDB browser added to docker-compose

**Step 3:**  
- AI generated: `src/parser.py`, `src/loader.py`
- Human reviewed: Graph visible in browser; 17 modules, 590 functions loaded

**Step 4:**  
- AI generated: `src/git_loader.py`, updated `src/loader.py`
- Human reviewed: Verified git history; 50 commits, 4 pseudonymized authors visible

**Step 5:**  
- AI generated: `src/queries.py`
- Human reviewed: All 5 queries verified; PageRank working natively in FalkorDB

**Step 8:**  
- AI generated: `src/mcp_server.py`
- Human reviewed: All 5 tool endpoints verified via Swagger UI

**Step 9:**  
- AI generated: `src/agent.py`, `sample_review.md`
- Human reviewed: Agent works end-to-end; gemini-3.5-flash confirmed working

**Step 10:**  
- AI generated: `frontend/index.html`, updated `src/mcp_server.py` with `/analyze`
- Human reviewed: [pending — verify UI opens and renders review]

---

## Step 10: React UI

**Decision:** Single-file HTML (CDN React + marked.js) instead of Vite project  
**Options considered:**
- Vite/React project vs single HTML file (chose single file: no build step, opens instantly, fewer failure points for a demo)
- Separate frontend server vs file:// (use `python3 -m http.server` if needed to avoid CORS)

**Trade-offs:**  
- Not production-grade; but for a hackathon demo, reliability matters more than scaffolding
- `marked.js` renders markdown well enough for the review output

---

## Step 11: README + Submission

**Decision:** Write README that explains graph model, Cypher queries, and limitations honestly  
**Why:** Submission requires graph model + queries + AI disclosure. Judges read README first.

**AI use disclosed:** All generated code was reviewed step-by-step. Author understands and can explain every Cypher query, graph schema choice, and architectural decision.

---

## Post-Hackathon Roadmap

**Multi-language support** (planned, not built):
- Python: done (AST)
- TypeScript/React: needs tree-sitter or babel AST
- Dart/Flutter: needs tree-sitter-dart
- The graph schema (Module, Function, CALLS, IMPORTS) is language-agnostic — only parsers change

**Motivation:** Author's own projects (FastAPI + React + PostgreSQL + Flutter) would benefit directly from Tremor's blast radius and reviewer analysis.

---

## AI Assistance Log

**Step 1:** AI generated: `docker-compose.yml`, `.env.example`, `.gitignore`, `flow.md`, `decision.md` · Human reviewed: Docker started, click repo cloned  
**Step 2:** AI generated: `requirements.txt`, `src/db.py` · Human reviewed: Connection verified  
**Step 3:** AI generated: `src/parser.py`, `src/loader.py` · Human reviewed: Graph visible in browser  
**Step 4:** AI generated: `src/git_loader.py`, updated `src/loader.py` · Human reviewed: Git history queryable  
**Step 5:** AI generated: `src/queries.py` · Human reviewed: All 5 queries working; PageRank confirmed  
**Step 8:** AI generated: `src/mcp_server.py` · Human reviewed: All endpoints verified via Swagger  
**Step 9:** AI generated: `src/agent.py` · Human reviewed: Full review output confirmed end-to-end  
**Step 10:** AI generated: `frontend/index.html`, updated `src/mcp_server.py` · Human reviewed: UI renders review  
**Step 11:** AI generated: `README.md`, final `flow.md`, `decision.md` · Human reviewed: [pending final check]


---

## Post-Hackathon: Multi-Language Support (Step 12)

**Date**: 2026-10-15 (post-submission)

**Decision**: Implement multi-language support (Python, TypeScript, Dart, SQL) with unified graph schema

### Context
User requested: "make this project reliable to work with any technology and techstack, after we finish our current modules"

Original system was Python-only (AST parser). For real-world use, Tremor needs to handle:
- Full-stack apps (Python backend + TypeScript frontend)
- Mobile apps (Flutter/Dart)
- Database code (SQL stored procedures)

### Approach Chosen: Plugin Architecture with Abstract Base Class

**Created**:
- `src/parsers/base.py` — Abstract `LanguageParser` interface + unified `ModuleInfo`/`FunctionInfo` data classes
- `src/parsers/python_parser.py` — Refactored original parser to implement interface
- `src/parsers/typescript_parser.py` — tree-sitter parser for TS/JS (.ts, .tsx, .js, .jsx)
- `src/parsers/dart_parser.py` — tree-sitter parser for Dart/Flutter (.dart) with regex fallback
- `src/parsers/sql_parser.py` — sqlparse parser for SQL (.sql) — extracts procedures, functions, table refs
- `src/parsers/__init__.py` — Auto-detection factory + `parse_multi_language_repo()` entry point
- `src/multi_loader.py` — Multi-language graph loader (replaces `loader.py` for mixed repos)

### Technical Decisions

#### Parser Dependencies
- **Python**: Built-in `ast` module → no dependencies, always works
- **TypeScript/Dart**: `tree_sitter_languages` package → **unavailable for Python 3.14** (too new)
- **SQL**: `sqlparse` → works with Python 3.14

**Fallback strategy**: Graceful degradation. If tree-sitter unavailable:
- Detection prints warning and skips that language
- Python and SQL parsing continue to work
- System does NOT fail — just processes subset of languages

#### File Extension Mapping
- Python: `.py`
- TypeScript/JavaScript: `.ts`, `.tsx`, `.js`, `.jsx`
- Dart: `.dart`
- SQL: `.sql`

Auto-detection scans repo for these extensions and creates parsers only for detected languages.

#### Graph Schema: Language Property Added
- **Module**: added `language` property (`'python'`, `'typescript'`, `'dart'`, `'sql'`)
- **Function**: added `language` property
- All other properties unchanged

**Backward compatible**: Old graphs without `language` property still work (queries can filter or not)

#### Import/Dependency Resolution
**Challenge**: Cross-language imports are hard to resolve statically
- Python `import foo` vs TypeScript `import foo from './foo'` vs SQL `USE schema`

**Solution**: Best-effort matching
1. Try same-language lookup first (name + language key)
2. Fall back to simple name match (cross-language)
3. Fall back to path substring match

**Limitation documented**: Only creates IMPORTS edge if both modules exist in parsed set. External dependencies (npm packages, pip packages) are ignored.

#### Call Graph: Intra-Module Only (Same as Original)
**No change**: Still extract CALLS edges only within same module (file).

**Why**: Cross-module call resolution requires:
- Resolving import aliases
- Tracking symbol renames
- Handling dynamic imports

This is AST analysis, not runtime tracing. Intra-module is reliable; cross-module is future work.

### Why tree-sitter (Not Hand-Written Regex)
- **Accurate**: Proper AST, not fragile string matching
- **Maintained**: tree-sitter grammars are widely used (VSCode, Neovim, GitHub)
- **Extensible**: Adding more languages (Go, Rust, Java) just needs new grammar

**Trade-off**: Dependency on `tree_sitter_languages` package, which isn't available for Python 3.14 yet.

### Why Keep Original `loader.py`
- **Minimal dependencies**: Python-only repos don't need tree-sitter or sqlparse
- **Simpler**: Single-language loader is easier to understand
- **Backward compatible**: Existing workflows don't break

Users can choose:
- `python src/loader.py` for Python-only repos (original, minimal deps)
- `python src/multi_loader.py` for multi-language repos (new, more deps)

### Testing
Tested with `click` repo (Python-only):
```bash
python src/multi_loader.py
# Result: Detected python, skipped typescript/dart (missing deps), loaded 91 modules, 1897 functions
```

**Verified**:
- Auto-detection works
- Graceful fallback when tree-sitter missing
- Graph loaded successfully with `language` property
- Queries still work: `MATCH (f:Function) RETURN f.name, f.language`

### Rejected Alternatives

**1. Use language-specific libraries**
- Python: `ast` (chosen) ✅
- TypeScript: `typescript` npm package → requires Node.js, not Python
- Dart: `analyzer` package → Dart SDK dependency
- SQL: raw regex → too fragile

**Why rejected**: Can't easily call from Python. tree-sitter is Python-native and handles multiple languages.

**2. External service (GitHub API, Sourcegraph, etc.)**
- **Pro**: No parsing, just query their API
- **Con**: Requires internet, API keys, not local, not submission-legal

**Why rejected**: Hackathon requires local processing. Can't rely on external services.

**3. Runtime analysis (profiling, tracing)**
- **Pro**: Captures actual calls, not just static analysis
- **Con**: Requires running the code, instrumentation, test coverage

**Why rejected**: Static analysis is safer and works on any repo (even broken code).

### Future Enhancements

**Short term** (when tree_sitter_languages supports Python 3.14):
- Install tree-sitter dependencies
- Test TypeScript/Dart parsers with real repos
- Add more file extensions (.jsx, .mjs, etc.)

**Medium term**:
- Cross-module CALLS edges (requires import resolution)
- More languages: Go, Rust, Java, C#, Ruby, PHP
- Better SQL parsing (CTEs, subqueries, window functions)

**Long term**:
- IDE integration (VSCode extension)
- Real-time graph updates (file watcher)
- Hybrid static + dynamic analysis (combine AST + runtime traces)

### AI Disclosure
This entire multi-language feature was designed and implemented by Claude Sonnet 4.5 in response to user request: "Yes Now implement , multi tech stack"

**Human decisions**:
- Request for multi-language support (user)

**AI decisions**:
- Plugin architecture with abstract base class
- tree-sitter for TypeScript/Dart (vs language-specific tools)
- Graceful fallback strategy (vs hard fail)
- Keep original loader.py (vs replace it)
- SQL support via sqlparse (vs skip SQL entirely)
- File structure (`src/parsers/` subdirectory)
- Auto-detection logic (scan file extensions)

**Implementation**: 100% AI-generated code
- 6 new files created: base.py, python_parser.py, typescript_parser.py, dart_parser.py, sql_parser.py, multi_loader.py
- 1 file refactored: requirements.txt (added dependencies)
- 2 docs updated: README.md (added Multi-Language section), decision.md (this section)

---


### ⚡ Tremor Code Review: `invoke` in `click`

### Impact
Modifying `invoke` has a blast radius affecting **72 downstream functions** across up to 3 hops in the call graph. Direct (Hop 1) dependents in `core.py` include:
- `_format_deprecated_suffix`
- `_make_sub_context`
- `_process_result`
- `augment_usage_errors`
- `fail`
- `get_default`

Additionally, test utilities `flush` and `get_default_prog_name` in `testing.py` are directly impacted in Hop 1.

### Risk Level
**Medium**: While the function is **not in the top 20 riskiest functions** based on graph risk scoring, its 72-function blast radius warrants cautious review.

### Tests to Run
Static call graph analysis found **0 test functions** reachable directly via structural call paths. Because static analysis did not isolate specific test targets, run the entire test suite to prevent regressions.

### Suggested Reviewers
Based on git history for this module stored in the graph:
- **Kevin Deldycke** (9 commits to this module)
- **Rowlando13** (9 commits to this module)

### Evidence
- **Graph Database**: FalkorDB
- **Blast Radius**: 72 functions (3 hops)
- **Direct Test Path**: No direct shortest call path found to test entrypoints

```bash
pytest tests/
```
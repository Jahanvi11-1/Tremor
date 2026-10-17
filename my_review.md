### ⚡ Tremor Code Review: `invoke`

Modifying `invoke` creates a broad blast radius affecting **72 downstream functions** across up to 3 hops in the FalkorDB call graph.

#### Impact
Hop 1 direct dependencies include core execution logic and test helpers:
- **`core.py`**: `_format_deprecated_suffix`, `_make_sub_context`, `_process_result`, `augment_usage_errors`, `fail`, `get_default`
- **`testing.py`**: `flush`, `get_default_prog_name`

#### Tests to Run
- **0 tests** were found directly reaching `invoke` via static call graph analysis. Because structural reachability did not map specific test callers, execute the full test suite to prevent untracked regressions.

#### Risk Level
- **Moderate**: Despite the 72-function blast radius, `invoke` is **not in the top 20 riskiest functions** based on graph risk scoring.

#### Suggested Reviewers
Based on module commit history in the graph:
- **Kevin Deldycke** (9 commits to this module)
- **Rowlando13** (9 commits to this module)

#### Evidence
- **Graph Analysis**: 72 functions affected (up to 3 hops).
- **Call Path**: No direct shortest path to specific test cases found via static reachability.
- **Engine**: FalkorDB graph database evidence.

```bash
pytest tests/
```
"""
Tremor agent loop: Gemini + MCP tool calls -> markdown review output.

HOW IT WORKS:
1. Receive a function name or commit SHA to analyze
2. Call MCP tools (blast_radius, find_tests, find_reviewers, rank_risk)
   via HTTP to the running MCP server
3. Collect all graph results
4. Send a structured prompt + results to Gemini REST API (no SDK — uses requests)
5. Gemini synthesizes a markdown code review comment
6. Output includes: impact summary, risk level, suggested tests, reviewers, evidence paths

WHY THE AGENT MATTERS:
The agent is not just calling Gemini to generate text. It first gathers
real graph evidence from FalkorDB, then asks Gemini to reason about it.
Every claim in the output is backed by an actual graph path.
The LLM cannot hallucinate the blast radius — it comes from the graph.
"""

import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8765")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


def call_gemini(prompt: str) -> str:
    """
    Call Gemini REST API directly with requests (no SDK, no protobuf dependency).
    Uses generateContent endpoint with retry on 503 (overload).
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set in .env file")

    model_id = GEMINI_MODEL if GEMINI_MODEL.startswith("models/") else f"models/{GEMINI_MODEL}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096
        }
    }

    import time
    for attempt in range(3):
        try:
            response = requests.post(
                url,
                params={"key": GEMINI_API_KEY},
                json=payload,
                timeout=60
            )
        except requests.exceptions.Timeout:
            wait = 5 * (attempt + 1)
            print(f"[Agent] Gemini timed out, retrying in {wait}s... (attempt {attempt+1}/3)")
            time.sleep(wait)
            continue

        if response.status_code == 503:
            wait = 5 * (attempt + 1)
            print(f"[Agent] Gemini overloaded, retrying in {wait}s... (attempt {attempt+1}/3)")
            time.sleep(wait)
            continue

        if response.status_code != 200:
            raise RuntimeError(
                f"Gemini API error {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected Gemini response format: {data}")

    raise RuntimeError("Gemini API unavailable after 3 retries")

def call_tool(tool_name: str, args: dict) -> dict:
    """
    Call a tool on the MCP server and return the result.

    Args:
        tool_name: One of blast_radius, find_tests, find_reviewers, rank_risk, explain_path
        args: Tool input arguments

    Returns:
        Tool result dict
    """
    url = f"{MCP_BASE_URL}/tools/{tool_name}"
    response = requests.post(url, json=args, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"Tool {tool_name} failed: {response.status_code} {response.text}")

    data = response.json()
    return data.get("result", data)


def get_tool_manifest() -> list:
    """Fetch the list of available tools from MCP server."""
    response = requests.get(f"{MCP_BASE_URL}/tools", timeout=10)
    return response.json().get("tools", [])


# --- Graph evidence gathering ---

def gather_evidence(function_name: str, module_name: str = None) -> dict:
    """
    Call all relevant MCP tools and collect graph evidence.

    Args:
        function_name: The function being analyzed
        module_name: Optional module to get reviewers for (auto-detected if None)

    Returns:
        Dictionary of all tool results
    """
    print(f"\n[Agent] Gathering graph evidence for: {function_name}")
    evidence = {}

    # 1. blast_radius — what does this change affect?
    print("[Agent] → Calling blast_radius...")
    try:
        evidence["blast_radius"] = call_tool("blast_radius", {
            "function_name": function_name,
            "max_hops": 3
        })
        affected = evidence["blast_radius"].get("affected_count", 0)
        print(f"         {affected} functions in blast radius")
    except Exception as e:
        print(f"         WARNING: {e}")
        evidence["blast_radius"] = {"error": str(e)}

    # 2. find_tests — which tests cover this?
    print("[Agent] → Calling find_tests...")
    try:
        evidence["find_tests"] = call_tool("find_tests", {
            "function_name": function_name,
            "max_hops": 4
        })
        tests = evidence["find_tests"].get("tests_found", 0)
        print(f"         {tests} tests found")
    except Exception as e:
        print(f"         WARNING: {e}")
        evidence["find_tests"] = {"error": str(e)}

    # 3. find_reviewers — who knows this code?
    target_module = module_name or _guess_module(function_name)
    print(f"[Agent] → Calling find_reviewers (module: {target_module})...")
    try:
        evidence["find_reviewers"] = call_tool("find_reviewers", {
            "module_name": target_module,
            "top_n": 3
        })
        reviewers = evidence["find_reviewers"].get("reviewers_found", 0)
        print(f"         {reviewers} reviewers found")
    except Exception as e:
        print(f"         WARNING: {e}")
        evidence["find_reviewers"] = {"error": str(e)}

    # 4. rank_risk — where does this function rank?
    print("[Agent] → Calling rank_risk...")
    try:
        evidence["rank_risk"] = call_tool("rank_risk", {"top_n": 20})
        # Find where our function ranks
        ranked = evidence["rank_risk"].get("ranked", [])
        rank = next(
            (i + 1 for i, r in enumerate(ranked) if r["function"] == function_name),
            None
        )
        evidence["rank_risk"]["target_rank"] = rank
        if rank:
            print(f"         {function_name} is ranked #{rank} by risk")
        else:
            print(f"         {function_name} not in top 20 by risk")
    except Exception as e:
        print(f"         WARNING: {e}")
        evidence["rank_risk"] = {"error": str(e)}

    # 5. explain_path — for first few affected functions
    blast = evidence.get("blast_radius", {})
    affected = blast.get("affected", [])
    if affected:
        first_affected = affected[0]["function"]
        print(f"[Agent] → Calling explain_path ({function_name} -> {first_affected})...")
        try:
            evidence["explain_path"] = call_tool("explain_path", {
                "from_function": function_name,
                "to_function": first_affected
            })
            found = evidence["explain_path"].get("found", False)
            print(f"         Path found: {found}")
        except Exception as e:
            print(f"         WARNING: {e}")
            evidence["explain_path"] = {"error": str(e)}

    print("[Agent] Evidence gathering complete.\n")
    return evidence


def _guess_module(function_name: str) -> str:
    """
    Best-effort guess at which module a function lives in.
    Falls back to 'core' which is the most important module.
    """
    # Common click module mappings
    module_hints = {
        "invoke": "core", "make_context": "core", "main": "core",
        "convert": "types", "fail": "types",
        "echo": "utils", "open_file": "utils",
        "option": "decorators", "command": "decorators",
        "format_usage": "formatting", "wrap_text": "formatting",
    }
    return module_hints.get(function_name, "core")


# --- Gemini synthesis ---

def build_prompt(function_name: str, evidence: dict, memory_context: dict = None) -> str:
    """
    Build the prompt for Gemini with all graph evidence embedded.
    Includes session memory comparison if available.
    """
    blast = evidence.get("blast_radius", {})
    tests = evidence.get("find_tests", {})
    reviewers = evidence.get("find_reviewers", {})
    risk = evidence.get("rank_risk", {})
    path = evidence.get("explain_path", {})

    # Format blast radius
    affected = blast.get("affected", [])
    affected_str = "\n".join(
        f"  - hop {f['hops']}: {f['function']} ({f.get('module','?').split('/')[-1]})"
        + (" [TEST]" if f.get("is_test") else "")
        for f in affected[:8]
    )
    if len(affected) > 8:
        affected_str += f"\n  ... and {len(affected) - 8} more"

    # Format tests
    test_list = tests.get("tests", [])
    test_str = "\n".join(
        "  - " + t["test_function"] + " (" + t.get("test_module","?").split("/")[-1] + ") "
        + f"[{t['hops']} hops away]"
        for t in test_list[:10]
    ) if test_list else "  No test functions found via static call graph."

    # Format reviewers
    reviewer_list = reviewers.get("reviewers", [])
    reviewer_str = "\n".join(
        f"  - {r['author']} ({r['commit_count']} commits to this module)"
        for r in reviewer_list
    ) if reviewer_list else "  No reviewer history found."

    # Format risk
    ranked = risk.get("ranked", [])
    target_rank = risk.get("target_rank")
    risk_str = f"Ranked #{target_rank} out of top 20 riskiest functions (PageRank)" \
        if target_rank else "Not in top 20 riskiest functions"

    # Format path
    path_str = path.get("path", "No direct call path found") if path.get("found") else \
        "No direct shortest path found"

    pytest_functions = [t["test_function"] for t in test_list[:5]]
    pytest_cmd = "pytest " + " ".join(f"-k {fn}" for fn in pytest_functions) \
        if pytest_functions else "pytest tests/  # No specific tests identified by call graph"

    # Session memory context
    memory_str = ""
    if memory_context and memory_context.get('summary'):
        memory_str = f"\nSESSION MEMORY (from graph - previous analyses):\n{memory_context['summary']}\n"

    return f"""You are Tremor, a code review assistant powered by FalkorDB graph analysis.
Analyze the function `{function_name}` from the `click` Python library using the graph evidence below.

Write a GitHub PR review comment in markdown. Be concise — max 200 words total.
Required sections (use ### headings): Impact, Tests to Run, Risk Level, Suggested Reviewers, Evidence.
{f"Include a ### Session Memory section summarizing how risk changed over time." if memory_str else ""}
End with a ```bash pytest command```. Every claim must reference the graph evidence.

GRAPH EVIDENCE (real data from FalkorDB):

BLAST RADIUS: {blast.get('affected_count', 0)} functions affected (up to 3 hops)
Top affected:
{affected_str if affected_str else '  None found'}

TEST COVERAGE: {tests.get('tests_found', 0)} tests via call graph
{test_str}

REVIEWERS (git history via graph):
{reviewer_str}

RISK SCORE: {risk_str}

CALL PATH: {path_str}
{memory_str}
PYTEST: {pytest_cmd}
"""


def run_agent(function_name: str, module_name: str = None) -> dict:
    """
    Main agent loop: gather evidence -> call Gemini -> store session -> return review.

    Returns dict with review markdown + session info + memory comparison.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set in .env file")

    # Import memory module
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from memory import create_session, compare_with_previous
        memory_enabled = True
    except ImportError:
        memory_enabled = False

    # Step 1: Load previous session history for comparison
    memory_context = None
    if memory_enabled:
        try:
            from memory import get_session_history
            history = get_session_history(function_name, limit=3)
            if history['sessions']:
                print(f"[Agent] Found {len(history['sessions'])} previous session(s) in memory")
        except Exception as e:
            print(f"[Agent] Memory read skipped: {e}")

    # Step 2: Gather evidence from graph via MCP
    evidence = gather_evidence(function_name, module_name)

    # Step 3: Build memory comparison context
    blast = evidence.get("blast_radius", {})
    risk = evidence.get("rank_risk", {})
    tests_data = evidence.get("find_tests", {})
    reviewers_data = evidence.get("find_reviewers", {})

    current_metrics = {
        'blast_radius_count': blast.get('affected_count', 0),
        'tests_found': tests_data.get('tests_found', 0),
        'risk_rank': risk.get('target_rank'),
    }

    session_id = None
    if memory_enabled:
        try:
            # Store this session BEFORE getting comparison (so history includes it)
            reviewer_names = [r['author'] for r in reviewers_data.get('reviewers', [])]
            session_id = create_session(
                function_name=function_name,
                blast_radius_count=current_metrics['blast_radius_count'],
                tests_found=current_metrics['tests_found'],
                risk_rank=current_metrics['risk_rank'],
                reviewers=reviewer_names,
                review_summary=""  # Will update after Gemini call
            )
            print(f"[Agent] Session stored: {session_id}")

            # Compare with previous
            memory_context = compare_with_previous(function_name, current_metrics)
            print(f"[Agent] Memory: {memory_context.get('risk_change', 'new')}")
        except Exception as e:
            print(f"[Agent] Memory write skipped: {e}")

    # Step 4: Build prompt with graph evidence + memory context
    prompt = build_prompt(function_name, evidence, memory_context)

    # Step 5: Call Gemini
    print("[Agent] Sending evidence to Gemini for synthesis...")
    review = call_gemini(prompt)

    # Step 6: Update session with review summary
    if memory_enabled and session_id:
        try:
            from db import get_graph
            graph = get_graph()
            graph.query(
                "MATCH (s:AnalysisSession {session_id: $sid}) SET s.review_summary = $summary",
                {'sid': session_id, 'summary': review[:300]}
            )
        except Exception:
            pass

    return {
        'review': review,
        'session_id': session_id,
        'memory': memory_context,
        'evidence': evidence
    }


def main():
    parser = argparse.ArgumentParser(
        description="Tremor: Graph-powered code review agent"
    )
    parser.add_argument(
        "--function", "-f",
        required=True,
        help="Function name to analyze (e.g. 'invoke', 'convert')"
    )
    parser.add_argument(
        "--module", "-m",
        default=None,
        help="Module name for reviewer lookup (optional, auto-detected)"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Save review to this file (optional)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("TREMOR — Graph-Powered PR Review Agent")
    print("=" * 60)
    print(f"Analyzing: {args.function}")
    print(f"MCP server: {MCP_BASE_URL}")
    print(f"LLM: {GEMINI_MODEL}")

    # Check MCP server is up
    try:
        resp = requests.get(f"{MCP_BASE_URL}/", timeout=5)
        info = resp.json()
        print(f"Graph: {info.get('functions_in_graph', '?')} functions loaded")
    except Exception as e:
        print(f"\nERROR: MCP server not reachable at {MCP_BASE_URL}")
        print("Start it first: source .venv/bin/activate && python src/mcp_server.py")
        sys.exit(1)

    print()

    # Run agent
    result = run_agent(args.function, args.module)

    # Handle both dict (new) and str (legacy) return
    if isinstance(result, dict):
        review = result['review']
        session_id = result.get('session_id')
        memory = result.get('memory')
    else:
        review = result
        session_id = None
        memory = None

    print("\n" + "=" * 60)
    print("TREMOR REVIEW OUTPUT")
    print("=" * 60)
    print(review)
    print("=" * 60)

    if session_id:
        print(f"\nSession stored: {session_id}")
    if memory and memory.get('summary'):
        print("\nMemory context:")
        print(memory['summary'])

    # Save if requested
    if args.output:
        with open(args.output, "w") as f:
            f.write(review)
        print(f"\nSaved to: {args.output}")


if __name__ == "__main__":
    main()

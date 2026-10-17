"""
Session memory for Tremor agent.

Stores every analysis run as a graph node so the agent can:
  - Remember what it found in previous sessions
  - Compare risk scores over time ("risk went from 4 to 7")
  - Show the full history of changes to a function
  - Answer: "What did I know about this function before?"

GRAPH SCHEMA ADDITIONS:
  Node: AnalysisSession
    - session_id: str (UUID)
    - function_name: str
    - timestamp: int (unix epoch)
    - risk_rank: int or null
    - blast_radius_count: int
    - tests_found: int
    - reviewers: str (comma-separated)
    - review_summary: str (first 200 chars of Gemini output)

  Edge: ANALYZED (AnalysisSession -> Function)
    - confidence: float (1.0 = full analysis, 0.5 = partial)

  Edge: PREVIOUS_SESSION (AnalysisSession -> AnalysisSession)
    - Used to chain sessions chronologically for the same function

WHY IN THE GRAPH (not a separate DB):
  - Memory is connected data: Sessions link to Functions, Authors, Modules
  - Multi-hop: "Find sessions where risk increased AND blast radius grew"
  - Same query interface: agents query memory just like code structure
  - Shared state: Multiple agents can read each other's sessions
"""

import time
import uuid
from typing import Optional, Dict, Any

from db import get_graph


def create_session(
    function_name: str,
    blast_radius_count: int,
    tests_found: int,
    risk_rank: Optional[int],
    reviewers: list,
    review_summary: str = ""
) -> str:
    """
    Store a new analysis session in the graph.

    Returns:
        session_id: Unique identifier for this session
    """
    graph = get_graph()
    session_id = str(uuid.uuid4())[:8]  # Short 8-char ID for readability
    timestamp = int(time.time())
    reviewer_names = ",".join(reviewers[:3]) if reviewers else ""

    # Create AnalysisSession node
    query = """
    CREATE (s:AnalysisSession {
        session_id: $session_id,
        function_name: $function_name,
        timestamp: $timestamp,
        risk_rank: $risk_rank,
        blast_radius_count: $blast_radius_count,
        tests_found: $tests_found,
        reviewers: $reviewers,
        review_summary: $review_summary
    })
    RETURN s.session_id AS id
    """
    graph.query(query, {
        'session_id': session_id,
        'function_name': function_name,
        'timestamp': timestamp,
        'risk_rank': risk_rank if risk_rank is not None else -1,
        'blast_radius_count': blast_radius_count,
        'tests_found': tests_found,
        'reviewers': reviewer_names,
        'review_summary': review_summary[:300] if review_summary else ""
    })

    # Link session to Function node (ANALYZED edge)
    link_query = """
    MATCH (s:AnalysisSession {session_id: $session_id})
    MATCH (f:Function {name: $function_name})
    CREATE (s)-[:ANALYZED {confidence: 1.0}]->(f)
    """
    try:
        graph.query(link_query, {
            'session_id': session_id,
            'function_name': function_name
        })
    except Exception:
        pass  # Function may not exist in graph (e.g. external function)

    # Link to previous session for same function (chain)
    prev_query = """
    MATCH (prev:AnalysisSession {function_name: $function_name})
    WHERE prev.session_id <> $session_id
    WITH prev ORDER BY prev.timestamp DESC LIMIT 1
    MATCH (curr:AnalysisSession {session_id: $session_id})
    CREATE (curr)-[:PREVIOUS_SESSION]->(prev)
    """
    try:
        graph.query(prev_query, {
            'session_id': session_id,
            'function_name': function_name
        })
    except Exception:
        pass

    return session_id


def get_session_history(function_name: str, limit: int = 5) -> list:
    """
    Retrieve past analysis sessions for a function.

    Returns:
        List of session dicts ordered by most recent first
    """
    graph = get_graph()

    query = """
    MATCH (s:AnalysisSession {function_name: $name})
    RETURN
        s.session_id AS session_id,
        s.timestamp AS timestamp,
        s.risk_rank AS risk_rank,
        s.blast_radius_count AS blast_radius_count,
        s.tests_found AS tests_found,
        s.reviewers AS reviewers,
        s.review_summary AS review_summary
    ORDER BY s.timestamp DESC
    LIMIT $limit
    """

    result = graph.query(query, {'name': function_name, 'limit': limit})

    sessions = []
    for row in result.result_set:
        sessions.append({
            'session_id': row[0],
            'timestamp': row[1],
            'risk_rank': row[2] if row[2] != -1 else None,
            'blast_radius_count': row[3],
            'tests_found': row[4],
            'reviewers': row[5],
            'review_summary': row[6]
        })

    return sessions


def compare_with_previous(function_name: str, current: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare current analysis with the most recent previous session.

    Returns a dict with change indicators:
      - risk_change: 'increased' | 'decreased' | 'unchanged' | 'new'
      - blast_radius_delta: int (positive = grew)
      - days_since_last: int
      - summary: human-readable string for agent to include in review
    """
    history = get_session_history(function_name, limit=2)

    if not history:
        return {
            'risk_change': 'new',
            'blast_radius_delta': 0,
            'days_since_last': None,
            'summary': f"🆕 First time analyzing `{function_name}` — no prior session."
        }

    # Most recent is first (it's the one we just created)
    # Second is the previous one
    if len(history) < 2:
        return {
            'risk_change': 'new',
            'blast_radius_delta': 0,
            'days_since_last': None,
            'summary': f"🆕 First analysis of `{function_name}` stored. Future runs will track changes."
        }

    prev = history[1]  # Previous session
    curr_blast = current.get('blast_radius_count', 0)
    prev_blast = prev.get('blast_radius_count', 0)
    curr_risk = current.get('risk_rank')
    prev_risk = prev.get('risk_rank')

    # Calculate time delta
    import time as t
    now = int(t.time())
    prev_ts = prev.get('timestamp', now)
    days_ago = max(0, (now - prev_ts) // 86400)

    # Blast radius delta
    blast_delta = curr_blast - prev_blast

    # Risk direction
    if prev_risk is None or curr_risk is None:
        risk_change = 'unchanged'
        risk_str = "Risk rank unchanged"
    elif curr_risk < prev_risk:
        risk_change = 'increased'  # Lower rank number = higher risk
        risk_str = f"📈 Risk rank moved #{prev_risk} → #{curr_risk} (higher risk)"
    elif curr_risk > prev_risk:
        risk_change = 'decreased'
        risk_str = f"📉 Risk rank moved #{prev_risk} → #{curr_risk} (lower risk)"
    else:
        risk_change = 'unchanged'
        risk_str = f"Risk rank stable at #{curr_risk}"

    # Blast radius direction
    if blast_delta > 0:
        blast_str = f"⚠️ Blast radius grew by {blast_delta} functions since last analysis"
    elif blast_delta < 0:
        blast_str = f"✅ Blast radius shrank by {abs(blast_delta)} functions"
    else:
        blast_str = f"Blast radius unchanged at {curr_blast} functions"

    time_str = f"{days_ago} days ago" if days_ago > 0 else "earlier today"

    summary = (
        f"📊 **Session Memory** (vs analysis {time_str}, session `{prev['session_id']}`):\n"
        f"  - {risk_str}\n"
        f"  - {blast_str}\n"
        f"  - Tests: {prev.get('tests_found', 0)} → {current.get('tests_found', 0)}"
    )

    return {
        'risk_change': risk_change,
        'blast_radius_delta': blast_delta,
        'days_since_last': days_ago,
        'previous_session_id': prev['session_id'],
        'summary': summary
    }


def get_all_analyzed_functions(limit: int = 20) -> list:
    """
    Get all functions that have been analyzed, with their latest session.
    Used by the UI memory panel.
    """
    graph = get_graph()

    query = """
    MATCH (s:AnalysisSession)
    WITH s.function_name AS fn,
         max(s.timestamp) AS latest_ts
    MATCH (s2:AnalysisSession {function_name: fn, timestamp: latest_ts})
    RETURN
        fn AS function_name,
        s2.session_id AS last_session_id,
        s2.timestamp AS last_analyzed,
        s2.risk_rank AS risk_rank,
        s2.blast_radius_count AS blast_radius_count
    ORDER BY s2.timestamp DESC
    LIMIT $limit
    """

    try:
        result = graph.query(query, {'limit': limit})
        functions = []
        for row in result.result_set:
            functions.append({
                'function_name': row[0],
                'last_session_id': row[1],
                'last_analyzed': row[2],
                'risk_rank': row[3] if row[3] != -1 else None,
                'blast_radius_count': row[4]
            })
        return functions
    except Exception:
        return []


def get_session_count() -> int:
    """Total number of analysis sessions stored."""
    graph = get_graph()
    try:
        result = graph.query("MATCH (s:AnalysisSession) RETURN count(s) AS count")
        return result.result_set[0][0] if result.result_set else 0
    except Exception:
        return 0

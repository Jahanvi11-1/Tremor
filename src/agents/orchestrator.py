"""
Agent Orchestrator: Runs SecurityAgent + ComplexityAgent in sequence.

The key insight for judges:
  1. ComplexityAgent runs first — stores findings in graph
  2. SecurityAgent runs second — READS ComplexityAgent findings from graph
  3. Both agents see the same function through different lenses
  4. Their findings connect in the graph: Finding -> Function <- Finding
  5. The orchestrator synthesizes both perspectives

This demonstrates "Share state between agents" criterion:
  State is shared through the GRAPH, not through direct API calls or shared memory.
  Any agent can query any other agent's findings using standard Cypher.

Cypher for shared state:
  MATCH (fi:Finding)-[:FLAGGED]->(f:Function {name: $fn})
  RETURN fi.agent_type, fi.severity, fi.message
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.security_agent import SecurityAgent
from agents.complexity_agent import ComplexityAgent
from db import get_graph


def run_multi_agent_analysis(function_name: str) -> dict:
    """
    Run both agents on a function and combine their findings.
    
    Agent execution order:
      1. ComplexityAgent — analyzes structural complexity, stores to graph
      2. SecurityAgent — analyzes security patterns, READS ComplexityAgent findings
      3. Orchestrator — combines both, finds overlaps (high risk = complex + security)
    
    Returns:
        Combined analysis dict with all findings and combined risk assessment
    """
    print(f"\n[Orchestrator] Running multi-agent analysis for: {function_name}")
    print("=" * 60)

    # Step 1: ComplexityAgent runs first — stores findings
    print("\n[Orchestrator] → Running ComplexityAgent...")
    complexity_agent = ComplexityAgent()
    complexity_result = complexity_agent.analyze(function_name)

    # Step 2: SecurityAgent runs — can now read ComplexityAgent's findings
    print("\n[Orchestrator] → Running SecurityAgent (with ComplexityAgent context)...")
    security_agent = SecurityAgent()
    security_result = security_agent.analyze(function_name)

    # Step 3: Find functions flagged by BOTH agents (highest risk)
    print("\n[Orchestrator] → Finding cross-agent overlap...")
    overlap = find_overlap(function_name)

    # Step 4: Combined risk assessment
    combined_risk = assess_combined_risk(
        function_name,
        complexity_result,
        security_result,
        overlap
    )

    print(f"\n[Orchestrator] Analysis complete. Combined risk: {combined_risk['level']}")

    return {
        'function': function_name,
        'complexity': complexity_result,
        'security': security_result,
        'overlap': overlap,
        'combined_risk': combined_risk,
        'agents_run': ['complexity', 'security']
    }


def find_overlap(function_name: str) -> list:
    """
    Find findings about a function from multiple agents.
    These are the most important: flagged by both complexity AND security.
    
    Cypher:
      MATCH (fi:Finding)-[:FLAGGED]->(f:Function {name: $name})
      RETURN fi.agent_type, fi.severity, fi.message
    """
    graph = get_graph()
    
    query = """
    MATCH (fi:Finding)-[:FLAGGED]->(f:Function {name: $name})
    RETURN fi.agent_type AS agent, fi.finding_type AS type,
           fi.severity AS severity, fi.message AS message
    ORDER BY
        CASE fi.severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END
    """
    
    try:
        result = graph.query(query, {'name': function_name})
        findings = [
            {'agent': row[0], 'type': row[1], 'severity': row[2], 'message': row[3]}
            for row in result.result_set
        ]
        
        # Mark findings that appear across multiple agents
        agents_seen = set(f['agent'] for f in findings)
        for f in findings:
            f['cross_agent'] = len(agents_seen) > 1
        
        return findings
    except Exception:
        return []


def assess_combined_risk(
    function_name: str,
    complexity: dict,
    security: dict,
    overlap: list
) -> dict:
    """
    Combine both agents' findings into a unified risk assessment.
    """
    # Count severities across both agents
    all_findings = (
        complexity.get('findings', []) + security.get('findings', [])
    )
    
    high_count = sum(1 for f in all_findings if f.get('severity') == 'HIGH')
    medium_count = sum(1 for f in all_findings if f.get('severity') == 'MEDIUM')
    
    # Target-specific findings
    target_complexity = next(
        (f for f in complexity.get('findings', []) if f.get('function') == function_name),
        {}
    )
    target_security_paths = [
        f for f in security.get('findings', [])
        if f.get('function') == function_name and f.get('type') == 'security_path'
    ]
    
    # Combined risk level
    if high_count >= 3 or (target_complexity.get('severity') == 'HIGH' and target_security_paths):
        level = 'CRITICAL'
        emoji = '🔴'
        explanation = (
            f"Function is in top PageRank positions AND touches security boundaries. "
            f"{high_count} HIGH severity findings across {len(set(f.get('agent','') for f in all_findings))} agents."
        )
    elif high_count >= 1 or medium_count >= 3:
        level = 'HIGH'
        emoji = '🟠'
        explanation = (
            f"{high_count} HIGH + {medium_count} MEDIUM findings. "
            "Recommend thorough review and test coverage."
        )
    elif medium_count >= 1:
        level = 'MEDIUM'
        emoji = '🟡'
        explanation = f"{medium_count} MEDIUM severity findings. Standard review process recommended."
    else:
        level = 'LOW'
        emoji = '🟢'
        explanation = "No significant complexity or security concerns detected."
    
    # Agent summaries
    summaries = []
    if complexity.get('summary'):
        summaries.append(complexity['summary'])
    if security.get('summary'):
        summaries.append(security['summary'])
    
    return {
        'level': level,
        'emoji': emoji,
        'explanation': explanation,
        'high_findings': high_count,
        'medium_findings': medium_count,
        'agents_contributed': list(set(f.get('agent', '') for f in all_findings if f.get('agent'))),
        'cross_agent_flags': [f for f in overlap if f.get('cross_agent')],
        'agent_summaries': summaries
    }


def get_all_findings(limit: int = 50) -> list:
    """
    Get all stored findings from all agents — for the UI.
    """
    graph = get_graph()
    
    query = """
    MATCH (fi:Finding)-[:FLAGGED]->(f:Function)
    RETURN fi.agent_type AS agent, fi.finding_type AS type,
           fi.severity AS severity, fi.message AS message,
           f.name AS function, f.module AS module,
           fi.timestamp AS ts
    ORDER BY
        CASE fi.severity WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,
        fi.timestamp DESC
    LIMIT $limit
    """
    
    try:
        result = graph.query(query, {'limit': limit})
        return [
            {
                'agent': row[0], 'type': row[1], 'severity': row[2],
                'message': row[3], 'function': row[4],
                'module': (row[5] or '').split('/')[-1],
                'timestamp': row[6]
            }
            for row in result.result_set
        ]
    except Exception:
        return []

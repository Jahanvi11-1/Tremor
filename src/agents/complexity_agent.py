"""
Complexity Agent: Identifies structurally complex functions in the call graph.

Focuses on:
  - Functions with high blast radius (many downstream dependencies)
  - Functions with many incoming calls (high in-degree = hub function)
  - Functions in the top PageRank scores (central to the call graph)
  - Functions that appear in many shortest paths (betweenness)

Stores findings as:
  (Finding {type:'complexity', score:int})-[:FLAGGED]->(Function)

Other agents (e.g. SecurityAgent) can read these to cross-reference:
  "This function is complex AND security-sensitive = critical risk"
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.base_agent import BaseAgent


class ComplexityAgent(BaseAgent):
    """
    Analyzes structural complexity of functions in the call graph.
    Uses PageRank + blast radius + in-degree to score complexity.
    """

    agent_type = "complexity"

    def analyze(self, target_function: str = None) -> dict:
        """
        Run complexity analysis.
        Returns findings about complex functions.
        """
        print(f"[ComplexityAgent] Starting analysis" + (f" for {target_function}" if target_function else ""))

        findings = []

        # 1. Get PageRank scores
        ranked = self._get_risk_ranking()
        print(f"[ComplexityAgent] Got {len(ranked)} ranked functions")

        # 2. Store findings for high-complexity functions
        for i, fn in enumerate(ranked[:15]):
            rank = i + 1
            score = fn.get('score', 0)
            blast = self._get_blast_radius(fn['function'])
            callers = self._get_caller_count(fn['function'])
            
            # Complexity score: combination of rank + blast + callers
            complexity = (15 - rank) + min(blast // 3, 10) + min(callers, 5)
            severity = 'HIGH' if complexity >= 15 else 'MEDIUM' if complexity >= 8 else 'LOW'
            
            message = (
                f"'{fn['function']}' is structurally complex: "
                f"PageRank rank #{rank}, {blast} functions in blast radius, "
                f"{callers} direct callers."
            )
            
            finding_id = self.store_finding(
                function_name=fn['function'],
                finding_type='high_complexity',
                severity=severity,
                message=message,
                evidence=f"pagerank_rank={rank},blast={blast},callers={callers},score={score}"
            )
            
            findings.append({
                'function': fn['function'],
                'module': fn.get('module', ''),
                'pagerank_rank': rank,
                'blast_radius': blast,
                'callers': callers,
                'severity': severity,
                'finding_id': finding_id
            })

        # 3. If target function provided, do targeted analysis
        target_finding = None
        if target_function:
            target_finding = self._analyze_target(target_function, ranked)
            if target_finding:
                findings.insert(0, target_finding)

        # 4. Read SecurityAgent's findings for cross-reference
        other_findings = []
        if target_function:
            other_findings = self.get_other_agents_findings(target_function)
            if other_findings:
                print(f"[ComplexityAgent] Read {len(other_findings)} findings from other agents")

        summary = self._synthesize_findings(target_function, findings, other_findings)

        print(f"[ComplexityAgent] Stored {len(findings)} findings")

        return {
            'agent': 'complexity',
            'target': target_function,
            'findings': findings,
            'other_agent_context': other_findings,
            'summary': summary,
            'high_complexity_count': len([f for f in findings if f.get('severity') == 'HIGH'])
        }

    def _get_risk_ranking(self) -> list:
        """Get PageRank ranking of functions."""
        try:
            query = """
            CALL algo.pageRank('Function', 'CALLS')
            YIELD node, score
            RETURN node.name AS function, node.module AS module, score
            ORDER BY score DESC
            LIMIT 20
            """
            result = self.graph.query(query)
            return [
                {'function': row[0], 'module': (row[1] or '').split('/')[-1], 'score': row[2]}
                for row in result.result_set
            ]
        except Exception:
            # Fallback: in-degree
            try:
                query = """
                MATCH (caller:Function)-[:CALLS]->(f:Function)
                RETURN f.name AS function, f.module AS module, count(caller) AS score
                ORDER BY score DESC LIMIT 20
                """
                result = self.graph.query(query)
                return [
                    {'function': row[0], 'module': (row[1] or '').split('/')[-1], 'score': row[2]}
                    for row in result.result_set
                ]
            except Exception:
                return []

    def _get_blast_radius(self, function_name: str) -> int:
        """Get blast radius count."""
        query = """
        MATCH (f:Function {name: $name})-[:CALLS*1..3]->(affected:Function)
        RETURN count(DISTINCT affected) AS count
        """
        try:
            result = self.graph.query(query, {'name': function_name})
            return result.result_set[0][0] if result.result_set else 0
        except Exception:
            return 0

    def _get_caller_count(self, function_name: str) -> int:
        """Count direct callers of a function."""
        query = """
        MATCH (caller:Function)-[:CALLS]->(f:Function {name: $name})
        RETURN count(caller) AS count
        """
        try:
            result = self.graph.query(query, {'name': function_name})
            return result.result_set[0][0] if result.result_set else 0
        except Exception:
            return 0

    def _analyze_target(self, target: str, ranked: list) -> dict:
        """Analyze complexity specifically for the target function."""
        blast = self._get_blast_radius(target)
        callers = self._get_caller_count(target)
        
        # Find rank in PageRank results
        rank = next((i + 1 for i, f in enumerate(ranked) if f['function'] == target), None)
        
        severity = 'HIGH' if (blast >= 10 or callers >= 5) else 'MEDIUM' if (blast >= 3 or callers >= 2) else 'LOW'
        
        message = (
            f"'{target}' complexity assessment: "
            f"{blast} functions in blast radius, {callers} direct callers"
            + (f", PageRank rank #{rank}" if rank else "")
        )
        
        finding_id = self.store_finding(
            function_name=target,
            finding_type='target_complexity',
            severity=severity,
            message=message,
            evidence=f"blast={blast},callers={callers},rank={rank}"
        )
        
        return {
            'function': target,
            'blast_radius': blast,
            'callers': callers,
            'pagerank_rank': rank,
            'severity': severity,
            'finding_id': finding_id,
            'message': message
        }

    def _synthesize_findings(self, target: str, findings: list, other_findings: list) -> str:
        """Generate complexity summary."""
        high = [f for f in findings if f.get('severity') == 'HIGH']
        
        parts = [f"⚙️ **Complexity Analysis** ({self.agent_type} agent):\n"]
        
        if target:
            target_f = next((f for f in findings if f.get('function') == target), None)
            if target_f:
                parts.append(
                    f"- Target `{target}`: blast={target_f.get('blast_radius', 0)}, "
                    f"callers={target_f.get('callers', 0)}, "
                    f"severity=**{target_f.get('severity', 'UNKNOWN')}**"
                )
        
        if high:
            parts.append(f"- **{len(high)} HIGH complexity** functions in graph")
            for f in high[:2]:
                parts.append(f"  - `{f['function']}` (blast={f.get('blast_radius', 0)}, rank #{f.get('pagerank_rank', '?')})")
        
        if other_findings:
            parts.append(f"\n_Cross-agent context (from {other_findings[0]['agent']} agent):_")
            parts.append(f"- {other_findings[0]['message'][:100]}")
        
        return "\n".join(parts)

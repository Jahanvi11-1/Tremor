"""
Security Agent: Finds security-relevant patterns in the call graph.

Focuses on:
  - Authentication/authorization functions (high blast radius = high risk)
  - Functions that touch external systems (SQL, HTTP, file I/O)
  - Functions that are both widely called AND have security responsibilities
  
Stores findings as:
  (Finding {type:'security', severity:'HIGH/MEDIUM/LOW'})-[:FLAGGED]->(Function)

Other agents can read these findings from the graph.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.base_agent import BaseAgent


# Security-sensitive keywords to look for in function names
SECURITY_KEYWORDS = [
    'auth', 'login', 'logout', 'password', 'token', 'secret', 'key',
    'permission', 'role', 'access', 'verify', 'validate', 'check',
    'encrypt', 'decrypt', 'hash', 'sign', 'cert', 'ssl', 'tls',
    'admin', 'root', 'sudo', 'privilege', 'credential', 'session',
    'cookie', 'csrf', 'xss', 'inject', 'sanitize', 'escape'
]

SQL_KEYWORDS = [
    'query', 'execute', 'fetch', 'insert', 'update', 'delete', 'select',
    'sql', 'db', 'database', 'cursor', 'connection', 'transaction'
]

HTTP_KEYWORDS = [
    'request', 'response', 'endpoint', 'route', 'handler', 'api',
    'http', 'url', 'get', 'post', 'put', 'patch', 'header', 'webhook'
]


class SecurityAgent(BaseAgent):
    """
    Scans the codebase graph for security-relevant functions.
    Stores findings for other agents to read.
    """

    agent_type = "security"

    def analyze(self, target_function: str = None) -> dict:
        """
        Run security analysis.
        
        If target_function is provided, focus on that function and its blast radius.
        Otherwise, scan the entire graph for security-sensitive functions.
        
        Returns:
            dict with findings list and summary
        """
        print(f"[SecurityAgent] Starting analysis" + (f" for {target_function}" if target_function else ""))
        
        findings = []

        # 1. Find security-sensitive functions in the graph
        sec_functions = self._find_security_functions()
        print(f"[SecurityAgent] Found {len(sec_functions)} security-sensitive functions")

        # 2. Check blast radius of security functions (high blast radius = high risk)
        for fn in sec_functions[:10]:  # Top 10 to keep it fast
            blast = self._get_blast_radius(fn['name'])
            severity = 'HIGH' if blast >= 10 else 'MEDIUM' if blast >= 3 else 'LOW'
            
            message = (
                f"Security-sensitive function '{fn['name']}' affects {blast} functions "
                f"(blast radius). Pattern: {fn['pattern']}."
            )
            
            finding_id = self.store_finding(
                function_name=fn['name'],
                finding_type='security_sensitive',
                severity=severity,
                message=message,
                evidence=f"blast_radius={blast}, pattern={fn['pattern']}, module={fn['module']}"
            )
            
            findings.append({
                'function': fn['name'],
                'module': fn['module'],
                'blast_radius': blast,
                'severity': severity,
                'pattern': fn['pattern'],
                'finding_id': finding_id
            })

        # 3. If specific target, also analyze path from target to security functions
        target_findings = []
        if target_function:
            target_findings = self._analyze_target_security(target_function, sec_functions)
            findings.extend(target_findings)

        # 4. Read ComplexityAgent's findings to cross-reference
        other_findings = []
        if target_function:
            other_findings = self.get_other_agents_findings(target_function)
            if other_findings:
                print(f"[SecurityAgent] Read {len(other_findings)} findings from other agents")

        # 5. Generate summary with Gemini if we have findings
        summary = self._synthesize_findings(target_function, findings, other_findings)

        print(f"[SecurityAgent] Stored {len(findings)} findings")
        
        return {
            'agent': 'security',
            'target': target_function,
            'findings': findings,
            'other_agent_context': other_findings,
            'summary': summary,
            'total_security_functions': len(sec_functions)
        }

    def _find_security_functions(self) -> list:
        """Find functions with security-sensitive names in the graph."""
        # Build name matching conditions
        conditions = []
        for kw in SECURITY_KEYWORDS + SQL_KEYWORDS + HTTP_KEYWORDS:
            conditions.append(f"toLower(f.name) CONTAINS '{kw}'")
        
        where_clause = " OR ".join(conditions)
        
        query = f"""
        MATCH (f:Function)
        WHERE {where_clause}
        RETURN f.name AS name, f.module AS module, f.language AS language
        LIMIT 30
        """
        
        try:
            result = self.graph.query(query)
            functions = []
            for row in result.result_set:
                name = row[0]
                # Determine which pattern matched
                name_lower = name.lower()
                pattern = 'general'
                for kw in SECURITY_KEYWORDS:
                    if kw in name_lower:
                        pattern = f'security:{kw}'
                        break
                for kw in SQL_KEYWORDS:
                    if kw in name_lower:
                        pattern = f'sql:{kw}'
                        break
                for kw in HTTP_KEYWORDS:
                    if kw in name_lower:
                        pattern = f'http:{kw}'
                        break
                
                functions.append({
                    'name': name,
                    'module': (row[1] or '').split('/')[-1],
                    'language': row[2] or 'python',
                    'pattern': pattern
                })
            return functions
        except Exception:
            return []

    def _get_blast_radius(self, function_name: str) -> int:
        """Get blast radius count for a function."""
        query = """
        MATCH (f:Function {name: $name})-[:CALLS*1..3]->(affected:Function)
        RETURN count(DISTINCT affected) AS count
        """
        try:
            result = self.graph.query(query, {'name': function_name})
            return result.result_set[0][0] if result.result_set else 0
        except Exception:
            return 0

    def _analyze_target_security(self, target: str, sec_functions: list) -> list:
        """Check if target function has a path to security-sensitive functions."""
        findings = []
        sec_names = [f['name'] for f in sec_functions[:5]]
        
        for sec_fn in sec_names:
            # Check if target calls into security function
            path_query = """
            MATCH (a:Function {name: $from_name}), (b:Function {name: $to_name})
            RETURN shortestPath((a)-[:CALLS*]->(b)) AS p
            """
            try:
                result = self.graph.query(path_query, {
                    'from_name': target,
                    'to_name': sec_fn
                })
                if result.result_set and result.result_set[0][0]:
                    path_obj = result.result_set[0][0]
                    hops = len(path_obj.nodes()) - 1 if hasattr(path_obj, 'nodes') else 1
                    
                    message = (
                        f"'{target}' reaches security-sensitive function '{sec_fn}' "
                        f"in {hops} hop(s). Changes to '{target}' may affect security boundaries."
                    )
                    finding_id = self.store_finding(
                        function_name=target,
                        finding_type='security_path',
                        severity='HIGH' if hops <= 2 else 'MEDIUM',
                        message=message,
                        evidence=f"path to {sec_fn} in {hops} hops"
                    )
                    findings.append({
                        'function': target,
                        'severity': 'HIGH' if hops <= 2 else 'MEDIUM',
                        'type': 'security_path',
                        'message': message
                    })
            except Exception:
                continue
        
        return findings

    def _synthesize_findings(self, target: str, findings: list, other_findings: list) -> str:
        """Generate a concise security summary."""
        if not findings:
            return "No security-sensitive patterns detected in blast radius."
        
        high = [f for f in findings if f.get('severity') == 'HIGH']
        medium = [f for f in findings if f.get('severity') == 'MEDIUM']
        
        parts = [f"🔒 **Security Analysis** ({self.agent_type} agent):\n"]
        
        if high:
            parts.append(f"- **{len(high)} HIGH severity** findings")
            for f in high[:2]:
                parts.append(f"  - `{f['function']}`: {f.get('message', '')[:100]}")
        
        if medium:
            parts.append(f"- **{len(medium)} MEDIUM severity** findings")
        
        if other_findings:
            parts.append(f"\n_Cross-agent context (from {other_findings[0]['agent']} agent):_")
            parts.append(f"- {other_findings[0]['message'][:100]}")
        
        return "\n".join(parts)

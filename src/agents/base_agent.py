"""
Base agent class for Tremor multi-agent system.

All specialized agents share the same graph for state.
Each agent stores its findings as Finding nodes:
  (Finding {type, severity, message})-[:FLAGGED]->(Function)

This allows agents to READ each other's findings, creating
shared context without any separate coordination protocol.
The graph IS the message bus.
"""

import os
import sys
import time
import uuid
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db import get_graph

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


class BaseAgent:
    """Base class for all Tremor agents."""

    agent_type = "base"

    def __init__(self):
        self.graph = get_graph()

    def store_finding(
        self,
        function_name: str,
        finding_type: str,
        severity: str,
        message: str,
        evidence: str = ""
    ) -> str:
        """
        Store a finding in the graph.
        
        Returns finding_id
        """
        finding_id = str(uuid.uuid4())[:8]
        timestamp = int(time.time())

        query = """
        CREATE (fi:Finding {
            finding_id: $finding_id,
            agent_type: $agent_type,
            finding_type: $finding_type,
            severity: $severity,
            message: $message,
            evidence: $evidence,
            timestamp: $timestamp
        })
        RETURN fi.finding_id AS id
        """
        self.graph.query(query, {
            'finding_id': finding_id,
            'agent_type': self.agent_type,
            'finding_type': finding_type,
            'severity': severity,
            'message': message,
            'evidence': evidence[:500],
            'timestamp': timestamp
        })

        # Link to function
        link_query = """
        MATCH (fi:Finding {finding_id: $finding_id})
        MATCH (f:Function {name: $function_name})
        CREATE (fi)-[:FLAGGED]->(f)
        """
        try:
            self.graph.query(link_query, {
                'finding_id': finding_id,
                'function_name': function_name
            })
        except Exception:
            pass

        return finding_id

    def get_other_agents_findings(self, function_name: str) -> list:
        """
        Read findings from OTHER agents about this function.
        This is how agents share state — through the graph.
        """
        query = """
        MATCH (fi:Finding)-[:FLAGGED]->(f:Function {name: $name})
        WHERE fi.agent_type <> $my_type
        RETURN fi.agent_type AS agent, fi.finding_type AS type,
               fi.severity AS severity, fi.message AS message
        ORDER BY fi.timestamp DESC
        LIMIT 10
        """
        try:
            result = self.graph.query(query, {
                'name': function_name,
                'my_type': self.agent_type
            })
            return [
                {'agent': row[0], 'type': row[1], 'severity': row[2], 'message': row[3]}
                for row in result.result_set
            ]
        except Exception:
            return []

    def call_gemini(self, prompt: str, max_tokens: int = 1024) -> str:
        """Shared Gemini call logic."""
        if not GEMINI_API_KEY:
            return "[No GEMINI_API_KEY set]"
        
        model_id = GEMINI_MODEL if GEMINI_MODEL.startswith("models/") else f"models/{GEMINI_MODEL}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}
        }

        for attempt in range(3):
            try:
                resp = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=45)
                if resp.status_code == 200:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                if resp.status_code == 503:
                    time.sleep(5 * (attempt + 1))
                    continue
            except Exception:
                time.sleep(3)
        
        return "[Gemini unavailable]"

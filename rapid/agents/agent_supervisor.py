from __future__ import annotations
"""
Agent Supervisor — Tier 1 Meta Agent.
Rates every agent after every task. Runs fully async — never delays user response.
Detects gaps. Flags when a new agent is needed.
"""

import asyncio
import logging
import uuid
from typing import List, Optional

import config
from models.nl_result import NLResult

logger = logging.getLogger(__name__)


class AgentSupervisor:

    def __init__(self):
        self._gap_reports: List[dict] = []

    async def rate_agent(self, agent_id: str, task_id: str, result: NLResult) -> float:
        """
        Rate agent performance on three dimensions:
          - Answer relevance: did it actually answer the question?
          - Confidence accuracy: was the bid confidence justified by result quality?
          - Token efficiency: placeholder (tokens not tracked per result yet)
        Returns composite score 0.0–1.0. Writes to audit log.
        """
        from agents.audit_logger import get_audit
        audit = get_audit()

        if result is None or not result.summary:
            score = 0.0
            dimensions = {"relevance": 0.0, "confidence_accuracy": 0.0, "token_efficiency": 0.5}
        else:
            # Relevance heuristic: non-empty, non-error summary
            relevance = 0.8 if len(result.summary) > 50 else 0.3
            # Confidence accuracy: score matches result quality
            conf_accuracy = result.confidence if result.confidence > 0 else 0.2
            # Token efficiency: placeholder
            token_efficiency = 0.7
            score = (relevance * 0.4 + conf_accuracy * 0.4 + token_efficiency * 0.2)
            dimensions = {
                "relevance": round(relevance, 3),
                "confidence_accuracy": round(conf_accuracy, 3),
                "token_efficiency": round(token_efficiency, 3),
            }

        audit.write_agent_score(agent_id, task_id, round(score, 3), dimensions)
        logger.debug(f"Supervisor rated {agent_id}: {score:.3f}")
        return score

    async def detect_gaps(self, query_log: List[dict]) -> List[dict]:
        """
        Scan query log for patterns where no agent bid ≥ MIN_BID_CONF.
        Returns list of capability gap reports.
        """
        gap_queries = [
            q for q in query_log
            if q.get("action_taken") == "gap_flagged"
        ]

        gap_counts: dict[str, int] = {}
        for q in gap_queries:
            key = q.get("raw_query", "")[:80]
            gap_counts[key] = gap_counts.get(key, 0) + 1

        gaps = []
        for query_pattern, count in gap_counts.items():
            if count >= config.GAP_PATTERN_THRESHOLD:
                gaps.append({
                    "gap_id": str(uuid.uuid4()),
                    "query_pattern": query_pattern,
                    "occurrence_count": count,
                    "suggested_action": "Consider adding a new department agent for this query type.",
                })

        return gaps

    async def flag_gap(self, gap_report: dict):
        """Send gap report to Agent Representative."""
        self._gap_reports.append(gap_report)
        logger.warning(f"Gap flagged: {gap_report}")
        # In production: notify AgentRepresentative via event queue

    def get_pending_gaps(self) -> List[dict]:
        gaps = list(self._gap_reports)
        self._gap_reports.clear()
        return gaps


class AgentRepresentative:
    """
    Tier 1 Meta Agent — sole channel between system and human admins.
    Manages the formal process of requesting and onboarding new agents.
    """

    def __init__(self):
        self._pending_requests: List[dict] = []
        self._approved_agents: List[dict] = []

    def receive_gap_report(self, gap_report: dict):
        """Validate and queue gap report. Waits for 3+ occurrences before escalating."""
        self._pending_requests.append(gap_report)
        logger.info(f"Gap report received: {gap_report.get('gap_id')}")

    def create_agent_request(self, gap_report: dict) -> dict:
        """Generate a formal new-agent request document."""
        return {
            "request_id": str(uuid.uuid4()),
            "gap_id": gap_report.get("gap_id"),
            "query_pattern": gap_report.get("query_pattern"),
            "occurrences": gap_report.get("occurrence_count"),
            "suggested_dept_scope": "unknown",
            "status": "pending_human_approval",
        }

    def track_approval(self, request_id: str) -> str:
        """Returns: pending / approved / rejected."""
        # In production: check approval queue / database
        return "pending"

    def onboard_agent(self, agent_spec: dict):
        """Register a new agent into the system once approved by human admin."""
        self._approved_agents.append(agent_spec)
        logger.info(f"New agent onboarded: {agent_spec.get('dept_tag')}")
        return agent_spec

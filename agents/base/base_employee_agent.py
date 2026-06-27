from __future__ import annotations
"""
base_employee_agent.py — Abstract base for all specialist employee agents.

Employee agents are the "workforce" inside each department:
  - Narrower keyword scope than the dept head
  - Access to only their sub-domain tables and doc folders
  - Execute via typed Tools (not raw pipelines directly)
  - Own specific skills from the dept config.yaml

The dept head agent's IntraDeptOrchestrator dispatches to these agents.
They never interact with the Orchestrator or MeshBus directly.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List

from models.bid_object import BidObject
from models.nl_result import NLResult
from agents.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class BaseEmployeeAgent(ABC):

    # ── Subclasses define these ───────────────────────────────────────────────
    dept_tag:        str        = ""
    role_title:      str        = ""   # e.g. "Financial Analyst"
    specialization:  str        = ""   # one-liner: "P&L, variance, trend analysis"
    skills:          List[str]  = []   # skill IDs from config.yaml
    tools_available: List[str]  = []   # tool names this agent may call

    # Narrower access than dept head
    permitted_tables: List[str] = []
    doc_folders:      List[str] = []
    bid_keywords:     List[str] = []   # very specific to this specialization

    # ── Bidding (used internally by IntraDeptOrchestrator) ───────────────────

    async def bid(self, query: str) -> BidObject:
        """Keyword-based bid — more specific than dept head."""
        q = query.lower()
        matches = sum(1 for kw in self.bid_keywords if kw in q)

        if matches >= 2:
            confidence = min(0.95, 0.72 + matches * 0.07)
        elif matches == 1:
            confidence = 0.65
        else:
            confidence = 0.15

        return BidObject(
            agent_id=f"{self.dept_tag}::{self.role_title}",
            can_handle=confidence >= 0.30,
            confidence=round(confidence, 3),
            estimated_tokens=350,
            needs_web_fallback=False,
            caveats="",
        )

    # ── Execution (via tools) ─────────────────────────────────────────────────

    async def execute(self, query: str, user_permissions: dict) -> NLResult:
        """
        Run the query using the tools listed in tools_available.
        All tools return NL strings — no raw data ever surfaces here.
        """
        registry = ToolRegistry.default()
        tool_outputs: List[str] = []

        tasks = []
        tool_names = []

        for tool_name in self.tools_available:
            tool = registry.get(tool_name)
            if tool is None:
                logger.warning(f"{self.role_title}: tool '{tool_name}' not registered")
                continue
            tasks.append(self._call_tool(tool, query, user_permissions))
            tool_names.append(tool_name)

        if not tasks:
            return NLResult(
                summary=f"No tools available for {self.role_title}.",
                source="employee_agent",
                confidence=0.1,
                dept_tag=self.dept_tag,
            )

        raw = await asyncio.gather(*tasks, return_exceptions=True)

        for name, outcome in zip(tool_names, raw):
            if isinstance(outcome, Exception):
                logger.error(f"{self.role_title}: tool '{name}' raised: {outcome!r}")
            elif outcome:
                tool_outputs.append(outcome)

        if not tool_outputs:
            return NLResult(
                summary=f"No relevant information found by {self.role_title} for this query.",
                source="employee_agent",
                confidence=0.1,
                dept_tag=self.dept_tag,
            )

        summary = await self._synthesise(tool_outputs, query)

        # Check if a skill should reformat this output
        from infrastructure.skills_engine import get_skills_engine
        engine = get_skills_engine()
        skill_id = engine.detect(query, self.dept_tag)
        if skill_id:
            try:
                skill_result = await engine.execute(
                    skill_id, self.dept_tag,
                    [NLResult(summary=summary, source="employee_agent", confidence=0.7, dept_tag=self.dept_tag)],
                    user_permissions,
                )
                summary = skill_result.content
                logger.info(f"{self.role_title}: skill '{skill_id}' applied to output")
            except Exception as e:
                logger.warning(f"{self.role_title}: skill '{skill_id}' failed: {e!r} — using raw summary")

        confidence = min(0.9, 0.55 + len(tool_outputs) * 0.15)

        return NLResult(
            summary=summary,
            source="employee_agent",
            confidence=round(confidence, 3),
            dept_tag=self.dept_tag,
            governance_log=[{
                "agent": self.role_title,
                "tools_used": [n for n, o in zip(tool_names, raw) if not isinstance(o, Exception) and o],
            }],
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _call_tool(self, tool, query: str, user_permissions: dict) -> str:
        """Route the query to the correct tool with the right kwargs."""
        from agents.tools.db_query_tool     import DBQueryTool
        from agents.tools.document_tool     import DocumentTool
        from agents.tools.calculation_tool  import CalculationTool
        from agents.tools.peer_consult_tool import PeerConsultTool

        if isinstance(tool, DBQueryTool):
            return await tool.run(query=query, dept_tag=self.dept_tag,
                                  user_permissions=user_permissions)
        if isinstance(tool, DocumentTool):
            return await tool.run(query=query, dept_tag=self.dept_tag,
                                  user_permissions=user_permissions)
        if isinstance(tool, CalculationTool):
            # Try to extract calculation intent from the query using LLM
            from infrastructure.llm_client import get_llm
            llm = get_llm()
            system = (
                "Extract calculation parameters from the query. "
                "Return JSON: {\"formula\": \"variance|roi|yoy_change|burn_rate|cagr\", \"params\": {...}} "
                "or {\"formula\": null} if no calculation is needed. "
                "Return ONLY the JSON, nothing else."
            )
            try:
                raw = await llm.complete(query, system=system)
                import json, re as _re
                match = _re.search(r'\{.*\}', raw, _re.DOTALL)
                if match:
                    extracted = json.loads(match.group())
                    formula = extracted.get("formula")
                    params = extracted.get("params", {})
                    if formula:
                        return await tool.run(formula=formula, params=params)
            except Exception as e:
                logger.warning(f"{self.role_title}: CalculationTool extraction failed: {e!r}")
            return ""
        if isinstance(tool, PeerConsultTool):
            # Only call peer consult if this agent has explicit consult targets configured
            # Skip silently for free-form queries without explicit dept_tag
            logger.debug(
                f"{self.role_title}: PeerConsultTool requires explicit dept_tag — skipping for free-form query"
            )
            return ""
        return ""

    async def _synthesise(self, tool_outputs: List[str], query: str) -> str:
        """LLM merges tool outputs into one coherent NL answer."""
        from infrastructure.llm_client import get_llm
        llm = get_llm()

        context = "\n\n".join(f"[Source {i+1}]: {out}" for i, out in enumerate(tool_outputs))
        system = (
            f"You are a {self.role_title} in the {self.dept_tag.upper()} department. "
            f"Your specialization: {self.specialization}. "
            "Using ONLY the sources below, answer the question clearly and concisely. "
            "Do not add information not present in the sources. "
            "If sources conflict, note both versions."
        )
        prompt = f"Question: {query}\n\nSources:\n{context}"

        try:
            return await llm.complete(prompt, system=system)
        except Exception as exc:
            logger.error(f"{self.role_title}: synthesis failed: {exc!r}")
            return "\n\n".join(tool_outputs)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(role={self.role_title!r}, dept={self.dept_tag!r})"

from __future__ import annotations
"""
agents/base/dynamic_employee_agent.py

A BaseEmployeeAgent whose identity and capabilities are configured
from a dict (typically loaded from CustomAgentStore) rather than
hardcoded class attributes.

Usage:
    from agents.base.dynamic_employee_agent import DynamicEmployeeAgent

    agent = DynamicEmployeeAgent({
        "agent_id":        "uuid-...",
        "dept_tag":        "finance",
        "role_title":      "Tax Specialist",
        "specialization":  "Corporate tax, VAT, deferred tax, withholding",
        "bid_keywords":    ["tax", "vat", "irs", "deferred", "withholding"],
        "permitted_tables": ["tax_compliance", "financials"],
        "doc_folders":     ["finance/tax_docs/"],
        "tools_available": ["db_query", "document_search"],
        "system_prompt":   "You are a specialist in corporate taxation...",
    })
"""

import logging
from typing import Any, Dict, List

from agents.base.base_employee_agent import BaseEmployeeAgent

logger = logging.getLogger("rapid.dynamic_agent")

# Map tool name strings → registered tool names used by ToolRegistry
_TOOL_MAP = {
    "db_query":        "db_query",
    "document_search": "document_search",
    "calculation":     "calculation",
    "peer_consult":    "peer_consult",
}


class DynamicEmployeeAgent(BaseEmployeeAgent):
    """
    A specialist agent whose configuration comes from a stored dict
    instead of class-level attributes. Fully compatible with
    IntraDeptOrchestrator — it bids and executes exactly like any
    hardcoded specialist.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        # Required fields
        self.agent_id:       str       = config["agent_id"]
        self.dept_tag:       str       = config["dept_tag"]
        self.role_title:     str       = config["role_title"]
        self.specialization: str       = config.get("specialization", "")

        # Capability fields
        self.bid_keywords:     List[str] = config.get("bid_keywords", [])
        self.permitted_tables: List[str] = config.get("permitted_tables", [])
        self.doc_folders:      List[str] = config.get("doc_folders", [])

        # Map stored tool names → registry keys
        raw_tools = config.get("tools_available", ["db_query", "document_search"])
        self.tools_available: List[str] = [
            _TOOL_MAP[t] for t in raw_tools if t in _TOOL_MAP
        ]

        # Optional custom system prompt injected into _synthesise
        self._custom_system_prompt: str = config.get("system_prompt", "")

        self.skills: List[str] = []

        logger.debug(
            f"[DynamicAgent] Loaded '{self.role_title}' "
            f"for dept={self.dept_tag} (id={self.agent_id})"
        )

    # ── Override _synthesise to inject custom system prompt ───────────────────

    async def _synthesise(self, tool_outputs: List[str], query: str) -> str:
        """Use the stored system_prompt if provided; fall back to base behaviour."""
        from infrastructure.llm_client import get_llm
        llm = get_llm()

        context = "\n\n".join(
            f"[Source {i+1}]: {out}" for i, out in enumerate(tool_outputs)
        )

        if self._custom_system_prompt:
            system = (
                f"{self._custom_system_prompt}\n\n"
                "Using ONLY the sources below, answer the question clearly and concisely. "
                "Do not add information not present in the sources."
            )
        else:
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
            logger.error(f"[DynamicAgent] {self.role_title}: synthesis failed: {exc!r}")
            return "\n\n".join(tool_outputs)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise back to the store format."""
        return {
            "agent_id":        self.agent_id,
            "dept_tag":        self.dept_tag,
            "role_title":      self.role_title,
            "specialization":  self.specialization,
            "bid_keywords":    self.bid_keywords,
            "permitted_tables": self.permitted_tables,
            "doc_folders":     self.doc_folders,
            "tools_available": self.tools_available,
            "system_prompt":   self._custom_system_prompt,
        }

    def __repr__(self) -> str:
        return (
            f"DynamicEmployeeAgent("
            f"role={self.role_title!r}, "
            f"dept={self.dept_tag!r}, "
            f"id={self.agent_id!r})"
        )

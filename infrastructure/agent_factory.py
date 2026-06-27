"""
infrastructure/agent_factory.py — Dynamic Agent Factory for RAPID.

Maps dept_id → the right intelligence agent instance.
Supports project-scoped agent selection without hardcoded imports.

Usage:
    factory = get_agent_factory()
    agent   = factory.get_intelligence_agent("sales")   # → SalesIntelligenceAgent
    dept    = factory.get_dept_agent("sales")           # → BaseDeptAgent (from registry)
    labels  = factory.list_available_depts()
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Type

logger = logging.getLogger(__name__)


# ── Intelligence agent map ────────────────────────────────────────────────────
# Maps dept_id → fully-qualified import path + class name.
# Lazy-loaded so startup is fast and individual import errors don't cascade.

_INTELLIGENCE_REGISTRY: Dict[str, tuple[str, str]] = {
    "finance":          ("agents.intelligence.finance_agent",           "FinanceAgent"),
    "sales":            ("agents.intelligence.sales_agent",             "SalesAgent"),
    "hr":               ("agents.intelligence.hr_agent",                "HRAgent"),
    "legal":            ("agents.intelligence.legal_agent",             "LegalAgent"),
    "marketing":        ("agents.intelligence.marketing_agent",         "MarketingAgent"),
    "ops":              ("agents.intelligence.operations_agent",        "OperationsAgent"),
    "it":               ("agents.intelligence.it_agent",                "ITAgent"),
    "procurement":      ("agents.intelligence.procurement_agent",       "ProcurementAgent"),
    "rd":               ("agents.intelligence.rd_agent",                "RDAgent"),
    "customer_success": ("agents.intelligence.customer_success_agent",  "CustomerSuccessAgent"),
}


class DynamicAgentFactory:
    """
    Factory that resolves dept_id → the correct agent class and returns
    a ready-to-use instance.

    Two pools:
      - Intelligence agents  (agents/intelligence/) — domain-aware LLM agents
      - Dept agents          (agents/departments/)  — execution agents (via AgentRegistry)
    """

    def __init__(self) -> None:
        # Cache: dept_id → instantiated intelligence agent
        self._intelligence_cache: Dict[str, object] = {}
        # AgentRegistry singleton — lazily loaded to avoid circular imports
        self._registry = None

    # ── Intelligence agents ───────────────────────────────────────────────────

    def get_intelligence_agent(self, dept_id: str) -> Optional[object]:
        """
        Return the intelligence agent for a department.
        Instances are cached after first creation.
        Returns None if the dept_id is unknown or import fails.
        """
        dept_id = dept_id.lower()

        if dept_id in self._intelligence_cache:
            return self._intelligence_cache[dept_id]

        entry = _INTELLIGENCE_REGISTRY.get(dept_id)
        if not entry:
            logger.warning(f"[AgentFactory] Unknown dept_id '{dept_id}' — no intelligence agent")
            return None

        module_path, class_name = entry
        try:
            import importlib
            module = importlib.import_module(module_path)
            cls: Type = getattr(module, class_name)

            # Intelligence agents need a CapabilityEngine
            from agents.capabilities.capability_engine import CapabilityEngine
            engine = CapabilityEngine()
            engine.setup()

            instance = cls(engine)
            self._intelligence_cache[dept_id] = instance
            logger.info(f"[AgentFactory] Created intelligence agent for '{dept_id}': {class_name}")
            return instance

        except Exception as e:
            logger.error(f"[AgentFactory] Failed to create intelligence agent for '{dept_id}': {e}")
            return None

    def get_intelligence_agent_class(self, dept_id: str) -> Optional[Type]:
        """Return the intelligence agent *class* without instantiating."""
        entry = _INTELLIGENCE_REGISTRY.get(dept_id.lower())
        if not entry:
            return None
        try:
            import importlib
            module = importlib.import_module(entry[0])
            return getattr(module, entry[1])
        except Exception as e:
            logger.error(f"[AgentFactory] Cannot load class for '{dept_id}': {e}")
            return None

    # ── Dept agents (execution layer) ─────────────────────────────────────────

    def get_dept_agent(self, dept_id: str) -> Optional[object]:
        """
        Return the execution-layer BaseDeptAgent from the AgentRegistry.
        Falls back to None if the registry isn't initialised or dept is unknown.
        """
        registry = self._get_registry()
        if not registry:
            return None
        return registry.get_dept_agent(dept_id)

    # ── Utility ───────────────────────────────────────────────────────────────

    def list_available_depts(self) -> list[str]:
        """Return all dept_ids that have registered intelligence agents."""
        return list(_INTELLIGENCE_REGISTRY.keys())

    def dept_has_agent(self, dept_id: str) -> bool:
        return dept_id.lower() in _INTELLIGENCE_REGISTRY

    def preload_all(self) -> dict[str, bool]:
        """
        Eagerly instantiate all intelligence agents.
        Returns {dept_id: success} map.
        Useful at startup to catch import errors early.
        """
        results = {}
        for dept_id in _INTELLIGENCE_REGISTRY:
            agent = self.get_intelligence_agent(dept_id)
            results[dept_id] = agent is not None
            if not results[dept_id]:
                logger.warning(f"[AgentFactory] Preload failed for '{dept_id}'")
        loaded = sum(results.values())
        logger.info(f"[AgentFactory] Preloaded {loaded}/{len(results)} intelligence agents")
        return results

    # ── Private ───────────────────────────────────────────────────────────────

    def _get_registry(self):
        if self._registry is None:
            try:
                from shared import agent_registry
                self._registry = agent_registry
            except Exception as e:
                logger.debug(f"[AgentFactory] AgentRegistry not available yet: {e}")
        return self._registry


# ── Singleton ─────────────────────────────────────────────────────────────────

_factory: Optional[DynamicAgentFactory] = None


def get_agent_factory() -> DynamicAgentFactory:
    global _factory
    if _factory is None:
        _factory = DynamicAgentFactory()
    return _factory

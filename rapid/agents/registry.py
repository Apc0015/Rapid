from __future__ import annotations
"""
registry.py — Single source of truth for all agent instances.

AgentRegistry holds every dept agent (×10) and every C-Suite agent (×4)
and provides lookup methods used by:
  - MasterPlanner  (as_planner_dict)
  - MeshBus        (get_dept_agent / get_csuite_agent)
  - EscalationRouter (get_exec_for_dept)
  - Orchestrator   (get_exec_for_dept / get_csuite_agent)

Build sequence (in shared.py):
    registry  = AgentRegistry.build()       # create all agents
    bus       = MeshBus(registry)           # needs registry
    router    = EscalationRouter(registry)  # needs registry
    orch      = Orchestrator(planner, bus, router, mem, registry)
    # Inject bus into all c-suite agents so they can dispatch to depts
    registry.inject_bus(bus)
"""

import logging
from typing import Dict, List, Optional

from agents.base_dept_agent import BaseDeptAgent
from agents.csuite.base_csuite_agent import BaseCsuiteAgent

logger = logging.getLogger(__name__)

# Known dept tags — kept in sync with departments/ directory
_ALL_DEPT_TAGS: List[str] = [
    "finance",
    "hr",
    "legal",
    "sales",
    "marketing",
    "ops",
    "it",
    "procurement",
    "rd",
    "customer_success",
]


class AgentRegistry:
    """
    Central registry for all agent instances.

    Access patterns:
        registry.get_dept_agent("finance")      → FinanceAgent
        registry.get_csuite_agent("cfo")        → CFOAgent
        registry.get_exec_for_dept("finance")   → CFOAgent
        registry.as_planner_dict()              → {"finance": FinanceAgent, ...}
    """

    def __init__(self) -> None:
        self._dept_agents:   Dict[str, BaseDeptAgent]    = {}
        self._csuite_agents: Dict[str, BaseCsuiteAgent]  = {}
        self._dept_to_exec:  Dict[str, str]              = {}  # dept_tag → exec_tag

    # ── Registration ──────────────────────────────────────────────────────────

    def register_dept(self, agent: BaseDeptAgent) -> None:
        self._dept_agents[agent.dept_tag] = agent
        logger.debug(f"Registry: registered dept agent '{agent.dept_tag}'")

    def register_csuite(self, agent: BaseCsuiteAgent) -> None:
        self._csuite_agents[agent.exec_tag] = agent
        # Record dept → exec mapping
        for dept in agent.division_depts:
            self._dept_to_exec[dept] = agent.exec_tag
        logger.debug(
            f"Registry: registered csuite agent '{agent.exec_tag}' "
            f"(owns: {agent.division_depts})"
        )

    # ── Lookups ───────────────────────────────────────────────────────────────

    def get_dept_agent(self, dept_tag: str) -> Optional[BaseDeptAgent]:
        return self._dept_agents.get(dept_tag)

    def get_csuite_agent(self, exec_tag: str) -> Optional[BaseCsuiteAgent]:
        return self._csuite_agents.get(exec_tag)

    def get_exec_for_dept(self, dept_tag: str) -> Optional[BaseCsuiteAgent]:
        """Return the C-Suite agent that owns this department."""
        exec_tag = self._dept_to_exec.get(dept_tag)
        return self._csuite_agents.get(exec_tag) if exec_tag else None

    def get_all_dept_agents(self) -> Dict[str, BaseDeptAgent]:
        return dict(self._dept_agents)

    def get_all_csuite_agents(self) -> Dict[str, BaseCsuiteAgent]:
        return dict(self._csuite_agents)

    def as_planner_dict(self) -> Dict[str, BaseDeptAgent]:
        """Return {dept_tag: agent} compatible with MasterPlanner(agent_registry=...)."""
        return self.get_all_dept_agents()

    # ── Bus injection ─────────────────────────────────────────────────────────

    def inject_bus(self, bus) -> None:
        """
        Inject the MeshBus into all C-Suite agents.
        Must be called after both the registry and bus are constructed.
        """
        for agent in self._csuite_agents.values():
            agent.set_bus(bus)
        logger.info(f"Registry: bus injected into {len(self._csuite_agents)} c-suite agents")

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def build(cls) -> "AgentRegistry":
        """
        Instantiate and register all 10 dept agents + 4 C-Suite agents.
        Called once at startup in shared.py.
        """
        registry = cls()

        # ── Dept agents (×10) ─────────────────────────────────────────────
        from agents.departments import (
            HRAgent, FinanceAgent, LegalAgent,
            SalesAgent, MarketingAgent, OperationsAgent, ITAgent,
            ProcurementAgent, RDAgent, CustomerSuccessAgent,
        )

        dept_agents = [
            FinanceAgent(),
            HRAgent(),
            LegalAgent(),
            SalesAgent(),
            MarketingAgent(),
            OperationsAgent(),
            ITAgent(),
            ProcurementAgent(),
            RDAgent(),
            CustomerSuccessAgent(),
        ]
        for agent in dept_agents:
            registry.register_dept(agent)

        # ── C-Suite agents (×4) ───────────────────────────────────────────
        from agents.csuite import CFOAgent, CTOAgent, COOAgent, CEOAgent

        # CEO is registered FIRST so that CFO/CTO/COO overwrite its broad
        # dept→exec mappings with their specific division ownership.
        csuite_agents = [CEOAgent(), CFOAgent(), CTOAgent(), COOAgent()]
        for agent in csuite_agents:
            registry.register_csuite(agent)

        logger.info(
            f"AgentRegistry built: "
            f"{len(registry._dept_agents)} dept agents, "
            f"{len(registry._csuite_agents)} c-suite agents"
        )
        return registry

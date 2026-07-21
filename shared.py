"""
shared.py — small shared singletons used across routers.

Intentionally minimal after the Phase 0 cleanup. The old bidding stack that
lived here — AgentRegistry (10 dept + 4 c-suite agents), MasterPlanner, MeshBus,
EscalationRouter, AgentMemory and the Orchestrator — was removed. Governed
retrieval now runs through one deterministic path: pipelines.rag_pipeline for
the /ask endpoint, and infrastructure.intelligence_gateway (a single governed
LLM synthesis over permission-scoped evidence) for the product surfaces.
See DECISIONS.md for why the bidding mesh and C-suite hierarchy were cut.

What remains here:
  • spokesperson    — the Spokesperson voice (greetings, trivial/general LLM
                      answers, intent classification), used by auth/users/admin
                      and the gateway's single-call synthesizer.
  • AGENT_REGISTRY  — a plain {dept_tag: {...}} map of the department catalog,
                      read by the monitoring router for per-department audit
                      stats. No longer a live agent registry.
"""
from agents.system.spokesperson import (
    Spokesperson,
    INTENT_TRIVIAL,
    INTENT_GENERAL,
    INTENT_AMBIGUOUS,
)
from infrastructure.people_ops_store import DEPARTMENTS as _DEPARTMENTS

spokesperson = Spokesperson()

# Plain department catalog (dept_tag -> label metadata). Replaces the old
# AgentRegistry.as_planner_dict(); the monitoring router reads per-department
# audit stats by iterating these keys.
AGENT_REGISTRY = {
    dept_tag: {"dept": dept_tag, "label": (meta.get("label", dept_tag) if isinstance(meta, dict) else dept_tag)}
    for dept_tag, meta in _DEPARTMENTS.items()
}

__all__ = [
    "spokesperson",
    "AGENT_REGISTRY",
    "INTENT_TRIVIAL",
    "INTENT_GENERAL",
    "INTENT_AMBIGUOUS",
]

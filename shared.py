"""
shared.py — singleton agent instances shared across the entire application.

Imported by main.py and every router that needs an agent reference.
Nothing here should import from main.py or routers/ (no circular deps).

Build sequence:
  1. AgentRegistry.build()    — instantiate all 10 dept + 4 c-suite agents
  2. MasterPlanner            — uses registry.as_planner_dict() for bidding
  3. MeshBus                  — uses registry for routing
  4. EscalationRouter         — uses registry to find exec agents
  5. AgentMemory              — ephemeral per-query state
  6. registry.inject_bus()    — give csuite agents access to the bus
  7. Orchestrator             — wraps all of the above
"""

from agents.system.spokesperson import Spokesperson, INTENT_TRIVIAL, INTENT_GENERAL, INTENT_AMBIGUOUS
from agents.system.master_planner import MasterPlanner
from agents.system.fusion_agent import FusionAgent
from agents.system.web_agent import WebAgent
from agents.system.agent_supervisor import AgentSupervisor, get_agent_supervisor, get_agent_representative
from agents.system.governance_filter import get_governance

# ── Registry (all 10 dept + 4 c-suite agents) ────────────────────────────────
from agents.registry import AgentRegistry
registry = AgentRegistry.build()

# ── Mesh infrastructure ───────────────────────────────────────────────────────
from agents.mesh.mesh_bus import MeshBus
from agents.mesh.escalation_router import EscalationRouter
from agents.mesh.agent_memory import AgentMemory
from agents.mesh.orchestrator import Orchestrator

bus    = MeshBus(registry)
router = EscalationRouter(registry)
mem    = AgentMemory()

# Inject live bus into PeerConsultTool so cross-dept consultation works
from agents.tools.peer_consult_tool import set_bus
set_bus(bus)

# Inject bus into all c-suite agents (they use it to dispatch to division depts)
registry.inject_bus(bus)

# ── Core pipeline components ──────────────────────────────────────────────────
spokesperson = Spokesperson()
planner      = MasterPlanner(registry.as_planner_dict())
fusion       = FusionAgent()
web_agent    = WebAgent()
supervisor   = get_agent_supervisor()

# ── Orchestrator ──────────────────────────────────────────────────────────────
orchestrator = Orchestrator(planner, bus, router, mem, registry)

# ── Backward-compatible AGENT_REGISTRY dict for any code that still uses it ──
AGENT_REGISTRY = registry.as_planner_dict()

# Re-export intent constants so callers can do `from shared import INTENT_TRIVIAL`
__all__ = [
    "registry",
    "orchestrator",
    "AGENT_REGISTRY",
    "spokesperson",
    "planner",
    "fusion",
    "web_agent",
    "supervisor",
    "INTENT_TRIVIAL",
    "INTENT_GENERAL",
    "INTENT_AMBIGUOUS",
]

"""RAPID agent system package.

After the Phase 0 cleanup this package holds only the retained building blocks:
the Spokesperson voice, the single governance filter, and the audit logger.
The bidding / mesh stack — MasterPlanner, FusionAgent, WebAgent, AgentSupervisor,
BaseDeptAgent, and the department / c-suite agents — was removed. Governed
retrieval now runs through one deterministic path. See DECISIONS.md.
"""
from .system.spokesperson import Spokesperson
from .system.governance_filter import GovernanceFilter, get_governance
from .system.audit_logger import AuditLogger, get_audit

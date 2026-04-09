from __future__ import annotations
"""
PeerConsultTool — consult a peer department agent mid-query.

Only allowed for dept pairs listed in config.yaml → agent.can_consult.
Governance firewall: the peer dept's full governance stack runs before
returning an NL summary — no raw data crosses the boundary.
"""

import logging
from agents.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

# Lazy reference to the bus — set at startup via set_bus()
_bus = None


def set_bus(bus) -> None:
    """Inject the MeshBus singleton. Called from shared.py after bus is built."""
    global _bus
    _bus = bus


class PeerConsultTool(BaseTool):
    name = "consult_department"
    description = (
        "Consult a peer department agent for their perspective on a query. "
        "Use only for depts listed in this agent's can_consult config. "
        "Returns their NL answer — never raw data."
    )

    async def run(
        self,
        dept_tag: str,
        query: str,
        user_permissions: dict,
    ) -> str:
        """
        Route the query to a peer dept agent via MeshBus.
        Returns the NL summary from that dept.
        """
        if _bus is None:
            logger.error("PeerConsultTool: MeshBus not injected — call set_bus() at startup")
            return ""

        try:
            result = await _bus.send(dept_tag, query, user_permissions)
            return result.summary or ""
        except Exception as exc:
            logger.error(f"PeerConsultTool: failed to consult dept='{dept_tag}': {exc!r}")
            return ""

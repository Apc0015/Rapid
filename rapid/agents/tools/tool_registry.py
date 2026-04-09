from __future__ import annotations
"""
ToolRegistry — central registry of all callable agent tools.

Usage:
    registry = ToolRegistry.default()   # singleton with all 4 tools
    tool = registry.get("calculate")
    result = await tool.run(formula="variance", params={...})
"""

import logging
from typing import Dict, Optional, TYPE_CHECKING

from agents.tools.base_tool import BaseTool

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_default_registry: Optional["ToolRegistry"] = None


class ToolRegistry:

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.debug(f"ToolRegistry: registered tool '{tool.name}'")

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    @classmethod
    def default(cls) -> "ToolRegistry":
        """
        Return (and build on first call) the application-wide singleton registry
        containing all 4 standard tools.
        """
        global _default_registry
        if _default_registry is None:
            _default_registry = cls()
            from agents.tools.db_query_tool    import DBQueryTool
            from agents.tools.calculation_tool import CalculationTool
            from agents.tools.document_tool    import DocumentTool
            from agents.tools.peer_consult_tool import PeerConsultTool

            _default_registry.register(DBQueryTool())
            _default_registry.register(CalculationTool())
            _default_registry.register(DocumentTool())
            _default_registry.register(PeerConsultTool())
            logger.info(f"ToolRegistry: default registry built with {len(_default_registry._tools)} tools")
        return _default_registry

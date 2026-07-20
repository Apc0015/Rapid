"""Compatibility facade for portal intelligence during gateway migration."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import BackgroundTasks

from infrastructure.intelligence_gateway import IntelligenceRequest, get_intelligence_gateway


class PortalIntelligenceService:
    """Keep the existing portal API stable while using the shared gateway."""

    @staticmethod
    async def _run_original_engine(*_args: Any, **_kwargs: Any) -> Any:
        # The gateway owns the default engine. Tests and legacy callers can
        # still inject this hook during the migration.
        return await get_intelligence_gateway()._run_legacy_engine(*_args, **_kwargs)

    async def ask(
        self,
        *,
        question: str,
        current_user: dict[str, Any],
        background_tasks: BackgroundTasks,
        department: Optional[str] = None,
        workspace_view: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
    ) -> dict[str, Any]:
        result = await get_intelligence_gateway().ask(
            IntelligenceRequest(
                question=question,
                department=department,
                workspace_view=workspace_view,
                history=history or [],
            ),
            current_user,
            background_tasks,
            legacy_executor=self._run_original_engine,
        )
        return result.model_dump()


def get_portal_intelligence() -> PortalIntelligenceService:
    return PortalIntelligenceService()

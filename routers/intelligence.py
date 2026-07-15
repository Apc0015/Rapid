"""Product-facing intelligence API backed by RAPID's original agent engine."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from infrastructure.portal_intelligence import get_portal_intelligence
from routers.deps import get_current_user

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class PortalQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    department: Optional[str] = Field(default=None, max_length=64)
    workspace_view: Optional[Literal[
        "overview", "meetings", "actions", "people", "crm", "projects", "tickets",
        "departments", "reports", "search", "notifications", "settings",
    ]] = None
    history: list[dict[str, str]] = Field(default_factory=list, max_length=6)


@router.post("/ask")
async def ask(
    body: PortalQuestion,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    try:
        return await get_portal_intelligence().ask(
            question=body.question,
            department=body.department,
            workspace_view=body.workspace_view,
            history=body.history,
            current_user=current_user,
            background_tasks=background_tasks,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

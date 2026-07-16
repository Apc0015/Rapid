"""Product-facing intelligence API backed by RAPID's original agent engine."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from infrastructure.portal_intelligence import get_portal_intelligence
from infrastructure.chat_history import ChatHistory
from infrastructure.intelligence_gateway import IntelligenceRequest, get_intelligence_gateway
from routers.deps import get_current_user

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class PortalQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    department: Optional[str] = Field(default=None, max_length=64)
    project_id: Optional[str] = Field(default=None, max_length=128)
    workspace_view: Optional[Literal[
        "overview", "meetings", "actions", "people", "crm", "projects", "tickets",
        "departments", "reports", "search", "notifications", "settings",
    ]] = None
    mode: Literal["query", "analysis", "planning", "reporting"] = "query"
    history: list[dict[str, str]] = Field(default_factory=list, max_length=6)
    session_id: Optional[str] = Field(default=None, max_length=128)


_history = ChatHistory()


def _tenant(current_user: dict) -> str:
    return str(current_user.get("tenant_id") or "default")


@router.post("/ask")
async def ask(
    body: PortalQuestion,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    try:
        session = None
        history = body.history
        tenant_id = _tenant(current_user)
        if body.session_id:
            # Conversation context is owned by the server. This prevents a
            # browser from injecting another user's or tenant's chat history.
            session = await _history.get_session(body.session_id, current_user["sub"], tenant_id)
            if not session:
                raise HTTPException(status_code=404, detail="Conversation not found")
            persisted_messages = await _history.get_messages(body.session_id, current_user["sub"], tenant_id)
            history = [
                {"role": message["role"], "content": message["content"]}
                for message in (persisted_messages or [])[-6:]
            ]
        if body.project_id:
            response = (await get_intelligence_gateway().ask(
                IntelligenceRequest(
                    question=body.question,
                    department=body.department,
                    project_id=body.project_id,
                    workspace_view=body.workspace_view,
                    mode=body.mode,
                    history=history,
                ),
                current_user,
                background_tasks,
            )).model_dump()
        else:
            response = await get_portal_intelligence().ask(
                question=body.question,
                department=body.department,
                workspace_view=body.workspace_view,
                history=history,
                current_user=current_user,
                background_tasks=background_tasks,
            )
        if session and body.session_id:
            await _history.append_message(body.session_id, "user", body.question)
            await _history.append_message(
                body.session_id,
                "assistant",
                str(response["answer"]),
                {
                    "response": response,
                    "workspace_view": body.workspace_view,
                    "department": body.department,
                },
            )
            if session["title"] == "New Chat":
                await _history.auto_title(body.session_id, current_user["sub"], tenant_id, body.question)
        return response
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

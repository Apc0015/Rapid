"""
Chat Sessions router — /sessions endpoints.

Auth: JWT Bearer token via Authorization header.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from infrastructure.chat_history import ChatHistory
from .deps import get_current_user

router = APIRouter(prefix="/sessions", tags=["sessions"])

_history = ChatHistory()


# ── Request bodies ────────────────────────────────────────────────────────────

class CreateSessionBody(BaseModel):
    title: str = "New Chat"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_sessions(current_user: dict = Depends(get_current_user)):
    """List all sessions for the authenticated user, newest first."""
    user_id = current_user["sub"]
    sessions = await _history.list_sessions(user_id)
    return {"sessions": sessions}


@router.post("")
async def create_session(body: CreateSessionBody,
                         current_user: dict = Depends(get_current_user)):
    """Create a new chat session. Returns {session_id, title, created_at}."""
    user_id = current_user["sub"]
    session = await _history.create_session(user_id, body.title)
    return session


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, current_user: dict = Depends(get_current_user)):
    """Return all messages for a session (ownership-checked)."""
    user_id = current_user["sub"]
    messages = await _history.get_messages(session_id, user_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found or not yours")
    return {"session_id": session_id, "messages": messages}


@router.delete("/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a session and all its messages (ownership-checked)."""
    user_id = current_user["sub"]
    deleted = await _history.delete_session(session_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found or not yours")
    return {"status": "deleted", "session_id": session_id}

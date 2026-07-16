"""
Chat Sessions router — /chat-sessions endpoints.

Auth: JWT Bearer token via Authorization header.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from infrastructure.chat_history import ChatHistory
from .deps import get_current_user

router = APIRouter(prefix="/chat-sessions", tags=["sessions"])

_history = ChatHistory()


def _tenant(current_user: dict) -> str:
    return str(current_user.get("tenant_id") or "default")


# ── Request bodies ────────────────────────────────────────────────────────────

class CreateSessionBody(BaseModel):
    title: str = "New Chat"


class UpdateTitleBody(BaseModel):
    title: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_sessions(current_user: dict = Depends(get_current_user)):
    """List all sessions for the authenticated user, newest first."""
    user_id = current_user["sub"]
    sessions = await _history.list_sessions(user_id, _tenant(current_user))
    return {"sessions": sessions}


@router.post("")
async def create_session(body: CreateSessionBody,
                         current_user: dict = Depends(get_current_user)):
    """Create a new chat session. Returns {session_id, title, created_at}."""
    user_id = current_user["sub"]
    title = body.title.strip() or "New Chat"
    session = await _history.create_session(user_id, _tenant(current_user), title)
    return session


@router.get("/{session_id}")
async def get_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Return session metadata (title, timestamps) for one session (ownership-checked)."""
    user_id = current_user["sub"]
    session = await _history.get_session(session_id, user_id, _tenant(current_user))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or not yours")
    return session


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, current_user: dict = Depends(get_current_user)):
    """Return all messages for a session (ownership-checked)."""
    user_id = current_user["sub"]
    messages = await _history.get_messages(session_id, user_id, _tenant(current_user))
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found or not yours")
    return {"session_id": session_id, "messages": messages}


@router.post("/{session_id}/title")
async def update_session_title(
    session_id: str,
    body: UpdateTitleBody,
    current_user: dict = Depends(get_current_user),
):
    """Manually update the title of a session (ownership-checked)."""
    user_id = current_user["sub"]
    session = await _history.get_session(session_id, user_id, _tenant(current_user))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or not yours")
    import aiosqlite
    from config import DB_PATH
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=? AND user_id=? AND tenant_id=?",
            (title, now, session_id, user_id, _tenant(current_user)),
        )
        await conn.commit()
    return {"status": "ok", "session_id": session_id, "title": title}


@router.delete("/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a session and all its messages (ownership-checked)."""
    user_id = current_user["sub"]
    deleted = await _history.delete_session(session_id, user_id, _tenant(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found or not yours")
    return {"status": "deleted", "session_id": session_id}

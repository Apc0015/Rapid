"""
Chat History — persists chat sessions and messages in SQLite (rapid.db).
Tables are created on first use (lazy init).
"""

import uuid
import json
import aiosqlite
from datetime import datetime, timezone
from typing import Optional

from config import DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatHistory:
    """Async SQLite-backed chat session store."""

    _initialized = False

    async def _ensure_tables(self, conn: aiosqlite.Connection) -> None:
        if ChatHistory._initialized:
            return
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                title       TEXT NOT NULL DEFAULT 'New Chat',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);

            CREATE TABLE IF NOT EXISTS chat_messages (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
        """)
        await conn.commit()
        ChatHistory._initialized = True

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(self, user_id: str, title: str = "New Chat") -> dict:
        session_id = str(uuid.uuid4())
        now = _now()
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            await conn.execute(
                "INSERT INTO chat_sessions(id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                (session_id, user_id, title, now, now),
            )
            await conn.commit()
        return {"id": session_id, "user_id": user_id, "title": title,
                "created_at": now, "updated_at": now}

    async def list_sessions(self, user_id: str, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM chat_sessions WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_session(self, session_id: str, user_id: str) -> Optional[dict]:
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM chat_sessions WHERE id=? AND user_id=?",
                (session_id, user_id),
            ) as cur:
                row = await cur.fetchone()
        return dict(row) if row else None

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            cur = await conn.execute(
                "DELETE FROM chat_sessions WHERE id=? AND user_id=?",
                (session_id, user_id),
            )
            await conn.commit()
        return cur.rowcount > 0

    async def auto_title(self, session_id: str, first_query: str) -> None:
        """Set the session title from the first user message (truncated)."""
        title = first_query[:60].strip()
        if len(first_query) > 60:
            title += "…"
        now = _now()
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=?",
                (title, now, session_id),
            )
            await conn.commit()

    async def touch_session(self, session_id: str) -> None:
        """Update updated_at timestamp so the session floats to the top."""
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE chat_sessions SET updated_at=? WHERE id=?",
                (_now(), session_id),
            )
            await conn.commit()

    # ── Messages ──────────────────────────────────────────────────────────────

    async def append_message(self, session_id: str, role: str, content: str) -> None:
        msg_id = str(uuid.uuid4())
        now = _now()
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            await conn.execute(
                "INSERT INTO chat_messages(id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                (msg_id, session_id, role, content, now),
            )
            # Also bump session updated_at
            await conn.execute(
                "UPDATE chat_sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
            await conn.commit()

    async def get_messages(self, session_id: str, user_id: str) -> list[dict]:
        """Returns messages only if user owns the session."""
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            conn.row_factory = aiosqlite.Row
            # Verify ownership
            async with conn.execute(
                "SELECT 1 FROM chat_sessions WHERE id=? AND user_id=?",
                (session_id, user_id),
            ) as cur:
                if not await cur.fetchone():
                    return []
            async with conn.execute(
                "SELECT id, role, content, created_at FROM chat_messages WHERE session_id=? ORDER BY created_at",
                (session_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def message_count(self, session_id: str) -> int:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id=?",
                (session_id,),
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else 0

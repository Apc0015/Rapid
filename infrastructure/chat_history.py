from __future__ import annotations
"""
Chat History — persists chat sessions and messages in SQLite (rapid.db).
Tables are created on first use (lazy init).
"""

import uuid
import json
import asyncio
import aiosqlite
from datetime import datetime, timezone
from typing import Optional

from config import DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatHistory:
    """Async SQLite-backed chat session store."""

    _initialized = False
    _initialization_lock: asyncio.Lock | None = None

    async def _ensure_tables(self, conn: aiosqlite.Connection) -> None:
        if ChatHistory._initialized:
            return
        if ChatHistory._initialization_lock is None:
            ChatHistory._initialization_lock = asyncio.Lock()
        async with ChatHistory._initialization_lock:
            if ChatHistory._initialized:
                return
            await self._initialize_tables(conn)
            ChatHistory._initialized = True

    async def _initialize_tables(self, conn: aiosqlite.Connection) -> None:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                tenant_id   TEXT NOT NULL DEFAULT 'default',
                title       TEXT NOT NULL DEFAULT 'New Chat',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content     TEXT NOT NULL,
                metadata    TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
        """)
        # Existing local demo databases predate tenant and answer metadata.
        # Migrate them in place so a product upgrade preserves user history.
        async with conn.execute("PRAGMA table_info(chat_sessions)") as cursor:
            session_columns = {row[1] for row in await cursor.fetchall()}
        if "tenant_id" not in session_columns:
            await conn.execute("ALTER TABLE chat_sessions ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
        async with conn.execute("PRAGMA table_info(chat_messages)") as cursor:
            message_columns = {row[1] for row in await cursor.fetchall()}
        if "metadata" not in message_columns:
            await conn.execute("ALTER TABLE chat_messages ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_owner ON chat_sessions(tenant_id, user_id, updated_at DESC)"
        )
        await conn.commit()

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(self, user_id: str, tenant_id: str, title: str = "New Chat") -> dict:
        session_id = str(uuid.uuid4())
        now = _now()
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            await conn.execute(
                "INSERT INTO chat_sessions(id, user_id, tenant_id, title, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (session_id, user_id, tenant_id, title, now, now),
            )
            await conn.commit()
        return {"id": session_id, "user_id": user_id, "tenant_id": tenant_id, "title": title,
                "created_at": now, "updated_at": now}

    async def list_sessions(self, user_id: str, tenant_id: str, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM chat_sessions WHERE user_id=? AND tenant_id=? ORDER BY updated_at DESC LIMIT ?",
                (user_id, tenant_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_session(self, session_id: str, user_id: str, tenant_id: str) -> Optional[dict]:
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM chat_sessions WHERE id=? AND user_id=? AND tenant_id=?",
                (session_id, user_id, tenant_id),
            ) as cur:
                row = await cur.fetchone()
        return dict(row) if row else None

    async def delete_session(self, session_id: str, user_id: str, tenant_id: str) -> bool:
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            cur = await conn.execute(
                "DELETE FROM chat_sessions WHERE id=? AND user_id=? AND tenant_id=?",
                (session_id, user_id, tenant_id),
            )
            await conn.commit()
        return cur.rowcount > 0

    async def auto_title(self, session_id: str, user_id: str, tenant_id: str, first_query: str) -> None:
        """Set the session title from the first user message (truncated)."""
        title = first_query[:60].strip()
        if len(first_query) > 60:
            title += "…"
        now = _now()
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE chat_sessions SET title=?, updated_at=? WHERE id=? AND user_id=? AND tenant_id=?",
                (title, now, session_id, user_id, tenant_id),
            )
            await conn.commit()

    async def touch_session(self, session_id: str, user_id: str, tenant_id: str) -> None:
        """Update updated_at timestamp so the session floats to the top."""
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE chat_sessions SET updated_at=? WHERE id=? AND user_id=? AND tenant_id=?",
                (_now(), session_id, user_id, tenant_id),
            )
            await conn.commit()

    # ── Messages ──────────────────────────────────────────────────────────────

    async def append_message(
        self, session_id: str, role: str, content: str, metadata: Optional[dict] = None
    ) -> None:
        msg_id = str(uuid.uuid4())
        now = _now()
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            await conn.execute(
                "INSERT INTO chat_messages(id, session_id, role, content, metadata, created_at) VALUES (?,?,?,?,?,?)",
                (msg_id, session_id, role, content, json.dumps(metadata or {}), now),
            )
            # Also bump session updated_at
            await conn.execute(
                "UPDATE chat_sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
            await conn.commit()

    async def get_messages(self, session_id: str, user_id: str, tenant_id: str) -> Optional[list[dict]]:
        """Returns messages only if user owns the session."""
        async with aiosqlite.connect(DB_PATH) as conn:
            await self._ensure_tables(conn)
            conn.row_factory = aiosqlite.Row
            # Verify ownership
            async with conn.execute(
                "SELECT 1 FROM chat_sessions WHERE id=? AND user_id=? AND tenant_id=?",
                (session_id, user_id, tenant_id),
            ) as cur:
                if not await cur.fetchone():
                    return None
            async with conn.execute(
                "SELECT id, role, content, metadata, created_at FROM chat_messages WHERE session_id=? ORDER BY created_at",
                (session_id,),
            ) as cur:
                rows = await cur.fetchall()
        messages = []
        for row in rows:
            message = dict(row)
            try:
                message["metadata"] = json.loads(message.get("metadata") or "{}")
            except json.JSONDecodeError:
                message["metadata"] = {}
            messages.append(message)
        return messages

    async def message_count(self, session_id: str) -> int:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id=?",
                (session_id,),
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else 0

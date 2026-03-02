import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USER_DB_PATH = os.path.join(DB_DIR, "users.db")


class ConversationService:
    """Conversation and message persistence."""

    def __init__(self):
        self._init_db()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(USER_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(USER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                created_at TEXT NOT NULL,
                last_message_at TEXT NOT NULL,
                archived INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sources TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            )
        """)
        conn.commit()
        conn.close()

    def create_conversation(self, user_id: str, title: Optional[str] = None) -> Dict:
        conv_id = f"conv_{datetime.now(timezone.utc).timestamp():.0f}"
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        try:
            conn.execute(
                "INSERT INTO conversations (conversation_id, user_id, title, created_at, last_message_at, archived) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (conv_id, user_id, title or "New Conversation", now, now),
            )
            conn.commit()
            return {"conversation_id": conv_id, "title": title or "New Conversation", "created_at": now}
        finally:
            conn.close()

    def list_conversations(self, user_id: str) -> List[Dict]:
        conn = self._get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE user_id = ? AND archived = 0 ORDER BY last_message_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def archive_conversation(self, conversation_id: str, user_id: str) -> Dict:
        conn = self._get_db()
        try:
            cur = conn.execute(
                "UPDATE conversations SET archived = 1 WHERE conversation_id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Conversation not found")
            conn.commit()
            return {"conversation_id": conversation_id, "archived": True}
        finally:
            conn.close()

    def add_message(self, conversation_id: str, role: str, content: str, sources: Optional[str] = None) -> Dict:
        message_id = f"msg_{datetime.now(timezone.utc).timestamp():.0f}"
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        try:
            conn.execute(
                "INSERT INTO messages (message_id, conversation_id, role, content, created_at, sources) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, conversation_id, role, content, now, sources),
            )
            conn.execute(
                "UPDATE conversations SET last_message_at = ? WHERE conversation_id = ?",
                (now, conversation_id),
            )
            conn.commit()
            return {"message_id": message_id, "created_at": now}
        finally:
            conn.close()

    def list_messages(self, conversation_id: str, user_id: str) -> List[Dict]:
        conn = self._get_db()
        try:
            # Ensure user owns conversation
            row = conn.execute(
                "SELECT 1 FROM conversations WHERE conversation_id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found")
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

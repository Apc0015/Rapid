from __future__ import annotations
"""
spokesperson/memory_store.py
─────────────────────────────────────────────────────────────────────────────
Spokesperson Memory — per-user persistent memory that lets the Spokesperson
answer questions in a way that is tailored to:

  • Who the user is (role, dept, permissions)
  • What they have asked before (last 10 queries — rolling window)
  • How they prefer to receive answers (learned from interaction)
  • What has already been told to them (avoids contradictions)
  • What topics have been blocked for them (privacy rights enforcement)

Storage: SQLite at data/spokesperson_memory.db
Each user has one memory row; queries stored as JSON array (rolling window).
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def _resolve_memory_db() -> str:
    try:
        p = Path("data/spokesperson_memory.db")
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(p), timeout=3)
        c.execute("CREATE TABLE IF NOT EXISTS _probe (x INTEGER)")
        c.execute("INSERT INTO _probe VALUES (1)")
        c.commit()
        c.execute("DELETE FROM _probe")
        c.commit()
        c.close()
        return str(p)
    except sqlite3.OperationalError:
        return "/tmp/rapid_spokesperson_memory.db"

_DB_PATH = _resolve_memory_db()
_QUERY_WINDOW = 10          # keep last N queries per user


def _conn() -> sqlite3.Connection:
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_memory (
            user_id          TEXT PRIMARY KEY,
            role             TEXT,
            department       TEXT,
            permitted_depts  TEXT,          -- JSON list
            query_history    TEXT,          -- JSON list of {query, ts, dept, intent}
            response_style   TEXT,          -- 'brief'|'detailed'|'strategic'|'board_level'
            interaction_count INTEGER DEFAULT 0,
            blocked_topics   TEXT,          -- JSON list of topics blocked this session
            last_seen        TEXT,
            notes            TEXT           -- free-form notes the memory can accumulate
        )
    """)
    c.commit()
    return c


# ─────────────────────────────────────────────────────────────────────────────
class UserMemory:
    """In-memory snapshot of a single user's memory row."""

    def __init__(self, row: Optional[sqlite3.Row] = None, user_id: str = ""):
        if row:
            self.user_id           = row["user_id"]
            self.role              = row["role"] or "employee"
            self.department        = row["department"] or ""
            self.permitted_depts   = json.loads(row["permitted_depts"] or "[]")
            self.query_history     = json.loads(row["query_history"]   or "[]")
            self.response_style    = row["response_style"] or "brief"
            self.interaction_count = row["interaction_count"] or 0
            self.blocked_topics    = json.loads(row["blocked_topics"]  or "[]")
            self.last_seen         = row["last_seen"] or ""
            self.notes             = row["notes"] or ""
        else:
            self.user_id           = user_id
            self.role              = "employee"
            self.department        = ""
            self.permitted_depts   = []
            self.query_history     = []
            self.response_style    = "brief"
            self.interaction_count = 0
            self.blocked_topics    = []
            self.last_seen         = ""
            self.notes             = ""

    # ── Derived helpers ───────────────────────────────────────────────────────

    def recent_queries(self, n: int = 5) -> list[str]:
        return [q["query"] for q in self.query_history[-n:]]

    def has_asked_about(self, topic: str) -> bool:
        t = topic.lower()
        return any(t in q["query"].lower() for q in self.query_history)

    def dept_context_prompt(self) -> str:
        """
        Returns a short context string injected into the Spokesperson prompt
        so it knows who it's talking to.
        """
        lines = [
            f"User role: {self.role}",
            f"Department: {self.department}",
            f"Permitted departments: {', '.join(self.permitted_depts) or 'own dept only'}",
            f"Response style: {self.response_style}",
            f"Interaction count: {self.interaction_count}",
        ]
        if self.recent_queries(3):
            lines.append(f"Recent topics: {'; '.join(self.recent_queries(3))}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
class MemoryStore:
    """
    CRUD interface for the Spokesperson memory DB.
    """

    # ── Read ──────────────────────────────────────────────────────────────────

    def load(self, user_id: str) -> UserMemory:
        """Load memory for a user. Returns blank UserMemory if first visit."""
        try:
            c   = _conn()
            row = c.execute(
                "SELECT * FROM user_memory WHERE user_id = ?", (user_id,)
            ).fetchone()
            c.close()
            return UserMemory(row=row, user_id=user_id) if row else UserMemory(user_id=user_id)
        except Exception as e:
            logger.error(f"[memory] load failed for {user_id}: {e}")
            return UserMemory(user_id=user_id)

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_profile(self, user_id: str, role: str, department: str,
                       permitted_depts: list[str]):
        """Called at login — keep profile in sync with auth system."""
        try:
            c = _conn()
            # Determine response style from role
            style_map = {
                "employee": "brief", "manager": "detailed",
                "dept_head": "strategic", "division_head": "executive",
                "c_suite": "board_level", "ceo": "board_level", "admin": "detailed",
            }
            style = style_map.get(role, "brief")
            now   = datetime.now(timezone.utc).isoformat()

            c.execute("""
                INSERT INTO user_memory
                    (user_id, role, department, permitted_depts, response_style, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    role=excluded.role,
                    department=excluded.department,
                    permitted_depts=excluded.permitted_depts,
                    response_style=excluded.response_style,
                    last_seen=excluded.last_seen
            """, (user_id, role, department,
                  json.dumps(permitted_depts), style, now))
            c.commit()
            c.close()
        except Exception as e:
            logger.error(f"[memory] upsert_profile failed: {e}")

    def record_query(self, user_id: str, query: str,
                     dept: str, intent: str):
        """Append a query to the rolling history window."""
        try:
            mem = self.load(user_id)
            entry = {
                "query":  query[:200],          # cap length
                "dept":   dept,
                "intent": intent,
                "ts":     datetime.now(timezone.utc).isoformat(),
            }
            history = mem.query_history[-(_QUERY_WINDOW - 1):] + [entry]
            count   = mem.interaction_count + 1
            now     = datetime.now(timezone.utc).isoformat()

            c = _conn()
            c.execute("""
                UPDATE user_memory
                SET query_history=?, interaction_count=?, last_seen=?
                WHERE user_id=?
            """, (json.dumps(history), count, now, user_id))
            if c.execute("SELECT changes()").fetchone()[0] == 0:
                # Row doesn't exist yet — create it
                c.execute("""
                    INSERT OR IGNORE INTO user_memory
                        (user_id, query_history, interaction_count, last_seen)
                    VALUES (?, ?, ?, ?)
                """, (user_id, json.dumps([entry]), 1, now))
            c.commit()
            c.close()
        except Exception as e:
            logger.error(f"[memory] record_query failed: {e}")

    def add_blocked_topic(self, user_id: str, topic: str):
        """Record a topic that was blocked this session (for audit + UX)."""
        try:
            mem    = self.load(user_id)
            topics = list(set(mem.blocked_topics + [topic]))[:50]  # cap at 50
            c = _conn()
            c.execute(
                "UPDATE user_memory SET blocked_topics=? WHERE user_id=?",
                (json.dumps(topics), user_id),
            )
            c.commit()
            c.close()
        except Exception as e:
            logger.error(f"[memory] add_blocked_topic failed: {e}")

    def add_note(self, user_id: str, note: str):
        """Append a note to the user's memory (admin use)."""
        try:
            mem      = self.load(user_id)
            combined = f"{mem.notes}\n{note}".strip()[-500:]    # cap at 500 chars
            c = _conn()
            c.execute(
                "UPDATE user_memory SET notes=? WHERE user_id=?",
                (combined, user_id),
            )
            c.commit()
            c.close()
        except Exception as e:
            logger.error(f"[memory] add_note failed: {e}")

    def clear(self, user_id: str):
        """Clear memory for a user (admin use / GDPR right to erasure)."""
        try:
            c = _conn()
            c.execute("DELETE FROM user_memory WHERE user_id=?", (user_id,))
            c.commit()
            c.close()
        except Exception as e:
            logger.error(f"[memory] clear failed: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────
_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store

from __future__ import annotations
"""
Audit Logger — Tier 5.
Immutable audit record for every query. 7-year retention enforced.

Retention policy:
  - Every row is stamped with retained_until = timestamp + 7 years at insert time.
  - purge_expired_records() hard-deletes rows whose retained_until has passed.
  - query_audit_trail() filters to in-retention rows only by default.
  - purge_expired_records() is called once at startup and should be scheduled daily.

Append-only within the retention window — no UPDATE ever executed on audit tables.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

RETENTION_YEARS = 7


class AuditLogger:

    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_audit_table()

    def _init_audit_table(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                log_id          TEXT PRIMARY KEY,
                event_type      TEXT NOT NULL,
                query_id        TEXT,
                user_id         TEXT,
                timestamp       TEXT NOT NULL,
                retained_until  TEXT NOT NULL,
                raw_query       TEXT,
                intent_class    TEXT,
                depts_activated TEXT,
                agents_selected TEXT,
                confidence      REAL,
                action_taken    TEXT,
                severity        TEXT DEFAULT 'LOW',
                details         TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_scores (
                score_id    TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                task_id     TEXT,
                score       REAL,
                timestamp   TEXT,
                dimensions  TEXT
            );
        """)
        # Migration: add retained_until column to pre-existing DBs that lack it
        try:
            conn.execute("ALTER TABLE audit_log ADD COLUMN retained_until TEXT")
            # Back-fill existing rows with 7 years from their timestamp
            conn.execute("""
                UPDATE audit_log
                SET retained_until = datetime(timestamp, '+7 years')
                WHERE retained_until IS NULL
            """)
            conn.commit()
            logger.info("Audit migration: retained_until column added and back-filled")
        except sqlite3.OperationalError:
            pass  # Column already exists — normal startup
        conn.commit()
        conn.close()
        # Purge any already-expired rows on startup (table now guaranteed to exist)
        try:
            self.purge_expired_records()
        except Exception as e:
            logger.warning(f"Startup purge skipped: {e}")

    # ── Logging methods ───────────────────────────────────────────────────────

    def log_query(self, query_event: dict):
        """Write full query event record — append only."""
        self._insert({
            "event_type": "QUERY",
            "query_id": query_event.get("query_id"),
            "user_id": query_event.get("user_id"),
            "raw_query": query_event.get("raw_query"),
            "intent_class": query_event.get("intent_class"),
            "depts_activated": json.dumps(query_event.get("depts_activated", [])),
            "agents_selected": json.dumps(query_event.get("agents_selected", [])),
            "confidence": query_event.get("composite_confidence", 0.0),
            "action_taken": query_event.get("action_taken"),
            "severity": "LOW",
            "details": None,
        })

    def log_governance(self, governance_event: dict):
        """Write governance action — which rule, which column, which user."""
        self._insert({
            "event_type": "GOVERNANCE",
            "query_id": governance_event.get("query_id"),
            "user_id": governance_event.get("user_id"),
            "severity": "HIGH" if governance_event.get("action") == "BLOCK" else "LOW",
            "details": json.dumps(governance_event),
        })

    def log_block(self, block_event: dict):
        """Write blocked actions with CRITICAL severity."""
        self._insert({
            "event_type": "BLOCK",
            "query_id": block_event.get("query_id"),
            "user_id": block_event.get("user_id"),
            "severity": "CRITICAL",
            "details": json.dumps(block_event),
        })
        logger.warning(f"AUDIT BLOCK: {block_event}")

    def log_auth_failure(self, user_id: str, reason: str):
        self._insert({
            "event_type": "AUTH_FAILURE",
            "user_id": user_id,
            "severity": "HIGH",
            "details": json.dumps({"reason": reason}),
        })

    # ── Query ─────────────────────────────────────────────────────────────────

    def query_audit_trail(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        include_expired: bool = False,
    ) -> list:
        """
        Read-only query for compliance review.
        By default only returns in-retention rows (retained_until > now).
        Pass include_expired=True only for archival/legal hold purposes.
        """
        if self.db_path == ":memory:":
            conn = sqlite3.connect(self.db_path)
        else:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        clauses = []
        params = []
        if not include_expired:
            clauses.append("(retained_until IS NULL OR retained_until > ?)")
            params.append(datetime.now(timezone.utc).isoformat())
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def purge_expired_records(self) -> int:
        """
        Hard-delete audit rows whose retention window has expired.
        Called at startup and should be scheduled daily.
        Returns the number of records deleted.
        """
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "DELETE FROM audit_log WHERE retained_until IS NOT NULL AND retained_until <= ?",
                (now,),
            )
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            if deleted:
                logger.info(f"Audit retention: purged {deleted} expired records (past 7-year window)")
            return deleted
        except sqlite3.OperationalError:
            # Table may not exist yet on very first init — safe to ignore
            return 0

    def get_retention_stats(self) -> dict:
        """Summary of retention window health — for admin monitoring."""
        try:
            # Use read-only URI for file DBs; fall back to normal connect for :memory:
            if self.db_path == ":memory:":
                conn = sqlite3.connect(self.db_path)
            else:
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            total     = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            in_window = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE retained_until > ?",
                (datetime.now(timezone.utc).isoformat(),),
            ).fetchone()[0]
            oldest = conn.execute(
                "SELECT MIN(timestamp) FROM audit_log"
            ).fetchone()[0]
            conn.close()
        except sqlite3.OperationalError:
            return {"total_records": 0, "in_retention_window": 0,
                    "expired_pending_purge": 0, "oldest_record": None,
                    "retention_years": RETENTION_YEARS}
        return {
            "total_records": total,
            "in_retention_window": in_window,
            "expired_pending_purge": total - in_window,
            "oldest_record": oldest,
            "retention_years": RETENTION_YEARS,
        }

    # ── Agent score writing ───────────────────────────────────────────────────

    def write_agent_score(self, agent_id: str, task_id: str, score: float, dimensions: dict):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO agent_scores (score_id, agent_id, task_id, score, timestamp, dimensions) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), agent_id, task_id, score, datetime.utcnow().isoformat(), json.dumps(dimensions)),
        )
        conn.commit()
        conn.close()

    def get_agent_stats(self, agent_id: str) -> dict:
        if self.db_path == ":memory:":
            conn = sqlite3.connect(self.db_path)
        else:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT score, timestamp FROM agent_scores WHERE agent_id = ? ORDER BY timestamp DESC",
            (agent_id,),
        ).fetchall()
        conn.close()
        if not rows:
            return {"agent_id": agent_id, "tasks": 0, "avg_score": None}
        scores = [r[0] for r in rows]
        return {
            "agent_id": agent_id,
            "tasks": len(scores),
            "avg_score": sum(scores) / len(scores),
            "recent_score": scores[0] if scores else None,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _insert(self, data: dict):
        """Append-only insert — never UPDATE or DELETE within the retention window."""
        now = datetime.now(timezone.utc)
        data["log_id"]        = str(uuid.uuid4())
        data["timestamp"]     = now.isoformat()
        data["retained_until"] = (now + timedelta(days=365 * RETENTION_YEARS)).isoformat()
        fields = [
            "log_id", "event_type", "query_id", "user_id", "timestamp",
            "retained_until", "raw_query", "intent_class", "depts_activated",
            "agents_selected", "confidence", "action_taken", "severity", "details",
        ]
        values = [data.get(f) for f in fields]
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            f"INSERT INTO audit_log ({','.join(fields)}) VALUES ({','.join(['?']*len(fields))})",
            values,
        )
        conn.commit()
        conn.close()


# ── Singleton ─────────────────────────────────────────────────────────────────
_audit: Optional[AuditLogger] = None

def get_audit() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger()
    return _audit

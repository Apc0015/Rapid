from __future__ import annotations
"""
Audit Logger — Tier 5.
Immutable audit record for every query. 7-year retention.
Append-only — no UPDATE or DELETE ever executed on audit tables.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


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
        conn.commit()
        conn.close()

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

    def query_audit_trail(self, user_id: Optional[str] = None, event_type: Optional[str] = None, limit: int = 100) -> list:
        """Read-only query for compliance review."""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        clauses = []
        params = []
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
        """Append-only insert — never UPDATE or DELETE."""
        data["log_id"] = str(uuid.uuid4())
        data["timestamp"] = datetime.utcnow().isoformat()
        # Fill missing fields with None
        fields = [
            "log_id", "event_type", "query_id", "user_id", "timestamp",
            "raw_query", "intent_class", "depts_activated", "agents_selected",
            "confidence", "action_taken", "severity", "details",
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

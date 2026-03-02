"""
Trace Service — records per-query execution traces to SQLite for observability.

Every query that passes through the orchestrator gets a trace row with:
  - confidence scores, retry count, repair history
  - latency, LLM call count (cost proxy)
  - intent classification

The /metrics endpoint reads from this table to surface aggregate stats.
"""

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "traces.db",
)


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class QueryTrace:
    """One trace record per orchestrator invocation."""
    query: str
    username: Optional[str] = None
    query_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: Optional[str] = None          # query_type from orchestrator
    is_decomposed: bool = False           # True if QueryDecomposer split the query
    sub_query_count: int = 1
    retry_count: int = 0                  # graph-level repair cycles
    repair_history: List[str] = field(default_factory=list)
    confidence_overall: Optional[float] = None
    confidence_verdict: Optional[str] = None  # "high" | "medium" | "low"
    is_partial_deliver: bool = False      # True if graceful degradation triggered
    llm_calls: int = 0                    # rough cost proxy
    latency_ms: int = 0
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


# ── Service ────────────────────────────────────────────────────────────────────

class TraceService:
    """
    Writes QueryTrace records to SQLite and exposes aggregate metrics.

    Thread-safe: each write opens its own connection (SQLite WAL mode).
    """

    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS query_traces (
                        query_id          TEXT PRIMARY KEY,
                        query             TEXT,
                        username          TEXT,
                        intent            TEXT,
                        is_decomposed     INTEGER DEFAULT 0,
                        sub_query_count   INTEGER DEFAULT 1,
                        retry_count       INTEGER DEFAULT 0,
                        repair_history    TEXT,       -- JSON list
                        confidence_overall REAL,
                        confidence_verdict TEXT,
                        is_partial_deliver INTEGER DEFAULT 0,
                        llm_calls         INTEGER DEFAULT 0,
                        latency_ms        INTEGER DEFAULT 0,
                        timestamp         TEXT
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_traces_username ON query_traces(username)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_traces_ts ON query_traces(timestamp)"
                )
        except Exception as exc:
            logger.warning("TraceService: failed to init DB: %s", exc)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ── Write ──────────────────────────────────────────────────────────────────

    def log(self, trace: QueryTrace) -> None:
        """Persist a QueryTrace. Silently swallows errors to never block queries."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO query_traces
                      (query_id, query, username, intent, is_decomposed, sub_query_count,
                       retry_count, repair_history, confidence_overall, confidence_verdict,
                       is_partial_deliver, llm_calls, latency_ms, timestamp)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        trace.query_id,
                        trace.query[:500],  # cap to avoid huge rows
                        trace.username,
                        trace.intent,
                        int(trace.is_decomposed),
                        trace.sub_query_count,
                        trace.retry_count,
                        json.dumps(trace.repair_history),
                        trace.confidence_overall,
                        trace.confidence_verdict,
                        int(trace.is_partial_deliver),
                        trace.llm_calls,
                        trace.latency_ms,
                        trace.timestamp,
                    ),
                )
        except Exception as exc:
            logger.debug("TraceService.log failed (non-fatal): %s", exc)

    # ── Read / Metrics ─────────────────────────────────────────────────────────

    def get_metrics(
        self,
        username: Optional[str] = None,
        last_n: int = 100,
    ) -> Dict[str, Any]:
        """
        Return aggregate quality metrics over the last *last_n* traces.

        Scope to a specific user if *username* is provided, otherwise global.

        Returns::

            {
              "total_queries": int,
              "avg_confidence": float | None,
              "high_confidence_pct": float,
              "retry_rate": float,           # % queries that needed graph-level repair
              "partial_deliver_rate": float, # % queries that hit graceful degradation
              "avg_latency_ms": float,
              "intent_breakdown": {intent: count},
              "decomposed_pct": float,
            }
        """
        try:
            with self._connect() as conn:
                where = "WHERE username = ?" if username else ""
                params: tuple = (username,) if username else ()

                rows = conn.execute(
                    f"""
                    SELECT intent, is_decomposed, retry_count, confidence_overall,
                           confidence_verdict, is_partial_deliver, latency_ms
                    FROM query_traces
                    {where}
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    params + (last_n,),
                ).fetchall()

            if not rows:
                return {"total_queries": 0, "message": "No traces recorded yet."}

            total = len(rows)
            confidences = [r["confidence_overall"] for r in rows if r["confidence_overall"] is not None]
            avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
            high_conf = sum(1 for r in rows if r["confidence_verdict"] == "high")
            retried = sum(1 for r in rows if r["retry_count"] > 0)
            partial = sum(1 for r in rows if r["is_partial_deliver"])
            decomposed = sum(1 for r in rows if r["is_decomposed"])
            latencies = [r["latency_ms"] for r in rows if r["latency_ms"] > 0]
            avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0

            intent_breakdown: Dict[str, int] = {}
            for r in rows:
                intent = r["intent"] or "unknown"
                intent_breakdown[intent] = intent_breakdown.get(intent, 0) + 1

            return {
                "total_queries": total,
                "avg_confidence": avg_confidence,
                "high_confidence_pct": round(high_conf / total * 100, 1),
                "retry_rate": round(retried / total * 100, 1),
                "partial_deliver_rate": round(partial / total * 100, 1),
                "decomposed_pct": round(decomposed / total * 100, 1),
                "avg_latency_ms": avg_latency,
                "intent_breakdown": intent_breakdown,
                "scope": username or "global",
                "last_n": total,
            }

        except Exception as exc:
            logger.warning("TraceService.get_metrics failed: %s", exc)
            return {"error": str(exc)}

    def get_recent_traces(
        self,
        username: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return the most recent trace rows as plain dicts."""
        try:
            with self._connect() as conn:
                where = "WHERE username = ?" if username else ""
                params: tuple = (username,) if username else ()
                rows = conn.execute(
                    f"""
                    SELECT * FROM query_traces
                    {where}
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    params + (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("TraceService.get_recent_traces failed: %s", exc)
            return []

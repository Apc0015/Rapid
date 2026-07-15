"""Durable tenant-scoped jobs with idempotency, retries, and dead-letter handling."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional


class JobQueueError(ValueError):
    """Safe queue error exposed through the API."""


JobHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
_handlers: dict[str, JobHandler] = {}


def register_job_handler(job_type: str, handler: JobHandler) -> None:
    if not job_type or not callable(handler):
        raise JobQueueError("A job type and async handler are required")
    _handlers[job_type] = handler


class JobQueue:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or os.getenv("RAPID_JOB_DB_PATH", "data/db/jobs.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS durable_jobs (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    available_at TEXT NOT NULL,
                    locked_at TEXT,
                    locked_by TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(tenant_id, job_type, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_durable_jobs_claim
                    ON durable_jobs(status, available_at, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_durable_jobs_tenant
                    ON durable_jobs(tenant_id, status, created_at DESC);
                CREATE TABLE IF NOT EXISTS job_worker_heartbeats (
                    worker_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_job_worker_heartbeats_seen
                    ON job_worker_heartbeats(last_seen_at DESC);
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
        data["result"] = json.loads(data.pop("result_json") or "{}")
        return data

    def enqueue(
        self,
        tenant_id: str,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        priority: int = 100,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> dict[str, Any]:
        if not tenant_id.strip() or not job_type.strip():
            raise JobQueueError("Tenant and job type are required")
        if max_attempts < 1 or max_attempts > 25:
            raise JobQueueError("max_attempts must be between 1 and 25")
        encoded = json.dumps(payload, default=str)
        if len(encoded.encode("utf-8")) > 1_000_000:
            raise JobQueueError("Job payload must be smaller than 1MB")
        key = (idempotency_key or f"auto:{uuid.uuid4().hex}").strip()
        if len(key) > 255:
            raise JobQueueError("Idempotency key must be at most 255 characters")
        now = self._now()
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        conn = self._connect()
        try:
            try:
                conn.execute(
                    """INSERT INTO durable_jobs
                       (id, tenant_id, job_type, idempotency_key, payload_json, status, priority, attempts,
                        max_attempts, available_at, created_at, updated_at)
                       VALUES (?,?,?,?,?,'queued',?,0,?,?,?,?)""",
                    (job_id, tenant_id.strip(), job_type.strip(), key, encoded, int(priority), max_attempts,
                     (available_at or now).isoformat(), now.isoformat(), now.isoformat()),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT * FROM durable_jobs WHERE tenant_id=? AND job_type=? AND idempotency_key=?",
                    (tenant_id.strip(), job_type.strip(), key),
                ).fetchone()
                if not row:
                    raise
                return {**self._serialize(row), "duplicate": True}
            row = conn.execute("SELECT * FROM durable_jobs WHERE id=?", (job_id,)).fetchone()
            return {**self._serialize(row), "duplicate": False}
        finally:
            conn.close()

    def get(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM durable_jobs WHERE id=? AND tenant_id=?", (job_id, tenant_id)).fetchone()
            if not row:
                raise JobQueueError("Job not found")
            return self._serialize(row)
        finally:
            conn.close()

    def list(self, tenant_id: str, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            query, args = "SELECT * FROM durable_jobs WHERE tenant_id=?", [tenant_id]
            if status:
                query += " AND status=?"
                args.append(status)
            query += " ORDER BY created_at DESC LIMIT ?"
            args.append(max(1, min(limit, 500)))
            return [self._serialize(row) for row in conn.execute(query, args).fetchall()]
        finally:
            conn.close()

    def stats(self, tenant_id: str | None = None) -> dict[str, int]:
        conn = self._connect()
        try:
            query, args = "SELECT status, COUNT(*) AS count FROM durable_jobs", []
            if tenant_id:
                query += " WHERE tenant_id=?"
                args.append(tenant_id)
            query += " GROUP BY status"
            counts = {row["status"]: row["count"] for row in conn.execute(query, args).fetchall()}
            return {"queued": counts.get("queued", 0), "running": counts.get("running", 0), "retry": counts.get("retry", 0), "completed": counts.get("completed", 0), "dead_letter": counts.get("dead_letter", 0)}
        finally:
            conn.close()

    def heartbeat(self, worker_id: str) -> dict[str, str]:
        """Record a worker lease so deployments can verify background processing."""
        if not worker_id.strip():
            raise JobQueueError("Worker id is required")
        now = self._now().isoformat()
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO job_worker_heartbeats (worker_id, started_at, last_seen_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(worker_id) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
                (worker_id.strip(), now, now),
            )
            conn.commit()
            return {"worker_id": worker_id.strip(), "last_seen_at": now}
        finally:
            conn.close()

    def worker_status(self, max_age_seconds: int = 45) -> dict[str, Any]:
        """Return workers with a current lease without exposing stale instances."""
        max_age = max(5, min(int(max_age_seconds), 3600))
        cutoff = (self._now() - timedelta(seconds=max_age)).isoformat()
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT worker_id, started_at, last_seen_at FROM job_worker_heartbeats
                   WHERE last_seen_at >= ? ORDER BY last_seen_at DESC""",
                (cutoff,),
            ).fetchall()
            workers = [dict(row) for row in rows]
            return {
                "status": "ready" if workers else "unavailable",
                "active_count": len(workers),
                "max_age_seconds": max_age,
                "workers": workers,
            }
        finally:
            conn.close()

    def recover_stale(self, stale_after_seconds: int = 900) -> int:
        cutoff = (self._now() - timedelta(seconds=max(60, stale_after_seconds))).isoformat()
        conn = self._connect()
        try:
            result = conn.execute(
                """UPDATE durable_jobs SET status='retry', locked_at=NULL, locked_by='', available_at=?,
                   last_error='Worker lease expired', updated_at=? WHERE status='running' AND locked_at<?""",
                (self._now().isoformat(), self._now().isoformat(), cutoff),
            )
            conn.commit()
            return result.rowcount
        finally:
            conn.close()

    def claim(self, worker_id: str, accepted_types: list[str] | None = None) -> Optional[dict[str, Any]]:
        if not worker_id.strip():
            raise JobQueueError("Worker id is required")
        now = self._now().isoformat()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            query = "SELECT * FROM durable_jobs WHERE status IN ('queued','retry') AND available_at<=?"
            args: list[Any] = [now]
            if accepted_types:
                placeholders = ",".join("?" for _ in accepted_types)
                query += f" AND job_type IN ({placeholders})"
                args.extend(accepted_types)
            query += " ORDER BY priority ASC, created_at ASC LIMIT 1"
            row = conn.execute(query, args).fetchone()
            if not row:
                conn.commit()
                return None
            result = conn.execute(
                """UPDATE durable_jobs SET status='running', attempts=attempts+1, locked_at=?, locked_by=?, updated_at=?
                   WHERE id=? AND status IN ('queued','retry')""",
                (now, worker_id.strip(), now, row["id"]),
            )
            if result.rowcount != 1:
                conn.rollback()
                return None
            conn.commit()
            claimed = conn.execute("SELECT * FROM durable_jobs WHERE id=?", (row["id"],)).fetchone()
            return self._serialize(claimed)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def complete(self, job_id: str, worker_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        now = self._now().isoformat()
        conn = self._connect()
        try:
            updated = conn.execute(
                """UPDATE durable_jobs SET status='completed', result_json=?, locked_at=NULL, locked_by='',
                   completed_at=?, updated_at=? WHERE id=? AND status='running' AND locked_by=?""",
                (json.dumps(result or {}, default=str), now, now, job_id, worker_id),
            )
            if updated.rowcount != 1:
                raise JobQueueError("Job is not owned by this worker")
            conn.commit()
            row = conn.execute("SELECT * FROM durable_jobs WHERE id=?", (job_id,)).fetchone()
            return self._serialize(row)
        finally:
            conn.close()

    def fail(self, job_id: str, worker_id: str, error: str, *, base_delay_seconds: int = 5) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM durable_jobs WHERE id=? AND status='running' AND locked_by=?", (job_id, worker_id)).fetchone()
            if not row:
                raise JobQueueError("Job is not owned by this worker")
            terminal = row["attempts"] >= row["max_attempts"]
            status = "dead_letter" if terminal else "retry"
            delay = min(3600, max(1, base_delay_seconds) * (2 ** max(0, row["attempts"] - 1)))
            now = self._now()
            conn.execute(
                """UPDATE durable_jobs SET status=?, available_at=?, locked_at=NULL, locked_by='', last_error=?,
                   completed_at=?, updated_at=? WHERE id=?""",
                (status, (now + timedelta(seconds=delay)).isoformat(), str(error)[:2000], now.isoformat() if terminal else None, now.isoformat(), job_id),
            )
            conn.commit()
            saved = conn.execute("SELECT * FROM durable_jobs WHERE id=?", (job_id,)).fetchone()
            return self._serialize(saved)
        finally:
            conn.close()

    def retry_dead_letter(self, tenant_id: str, job_id: str) -> dict[str, Any]:
        now = self._now().isoformat()
        conn = self._connect()
        try:
            result = conn.execute(
                """UPDATE durable_jobs SET status='queued', attempts=0, available_at=?, completed_at=NULL,
                   last_error='', updated_at=? WHERE id=? AND tenant_id=? AND status='dead_letter'""",
                (now, now, job_id, tenant_id),
            )
            if result.rowcount != 1:
                raise JobQueueError("Dead-letter job not found")
            conn.commit()
            row = conn.execute("SELECT * FROM durable_jobs WHERE id=?", (job_id,)).fetchone()
            return self._serialize(row)
        finally:
            conn.close()


async def process_one(queue: JobQueue, worker_id: str) -> Optional[dict[str, Any]]:
    job = queue.claim(worker_id, list(_handlers) or None)
    if not job:
        return None
    handler = _handlers.get(job["job_type"])
    if not handler:
        return queue.fail(job["id"], worker_id, f"No handler registered for {job['job_type']}")
    try:
        result = await handler(job)
        return queue.complete(job["id"], worker_id, result)
    except Exception as error:
        return queue.fail(job["id"], worker_id, str(error))


async def run_worker(queue: JobQueue | None = None, *, worker_id: str | None = None, poll_seconds: float = 1.0) -> None:
    queue = queue or get_job_queue()
    worker_id = worker_id or f"worker-{os.getpid()}"
    queue.recover_stale()

    async def maintain_heartbeat() -> None:
        while True:
            queue.heartbeat(worker_id)
            await asyncio.sleep(10)

    heartbeat_task = asyncio.create_task(maintain_heartbeat())
    try:
        while True:
            processed = await process_one(queue, worker_id)
            if not processed:
                await asyncio.sleep(max(0.1, poll_seconds))
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task


def get_job_queue() -> JobQueue:
    return JobQueue()

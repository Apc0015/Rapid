from __future__ import annotations
"""
agent_memory.py — Per-query working memory for the mesh layer.

Ephemeral, in-process only.  Nothing persists after the response is sent.
All query contexts are cleaned up by the Orchestrator once a response is
returned, or by cleanup_stale() if something goes wrong.

Thread-safety: asyncio.Lock protects the internal dict so multiple
concurrent queries don't race.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from models.nl_result import NLResult

logger = logging.getLogger(__name__)


@dataclass
class QueryContext:
    """Working memory for a single in-flight query."""

    query_id: str
    original_query: str
    user_permissions: dict

    # Accumulated results keyed by dept_tag (or exec_tag for c-suite)
    sub_results: Dict[str, NLResult] = field(default_factory=dict)

    # Wall-clock time when this context was created
    started_at: float = field(default_factory=time.monotonic)

    # Dept tags that triggered escalation during this query
    escalations: List[str] = field(default_factory=list)


class AgentMemory:
    """
    In-process store for per-query working memory.

    Lifecycle:
        context = memory.create(query_id, query, perms)
        memory.add_result(query_id, "finance", nl_result)
        memory.mark_escalation(query_id, "finance")
        memory.cleanup(query_id)          # always call when done

    Periodic housekeeping:
        await memory.cleanup_stale(max_age=120)
    """

    def __init__(self) -> None:
        self._store: Dict[str, QueryContext] = {}
        self._lock = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def create(
        self, query_id: str, original_query: str, user_permissions: dict
    ) -> QueryContext:
        """Create and store a new QueryContext. Returns the context."""
        ctx = QueryContext(
            query_id=query_id,
            original_query=original_query,
            user_permissions=user_permissions,
        )
        async with self._lock:
            self._store[query_id] = ctx
        return ctx

    async def get(self, query_id: str) -> Optional[QueryContext]:
        """Return the QueryContext for this query_id, or None."""
        async with self._lock:
            return self._store.get(query_id)

    async def add_result(self, query_id: str, agent_tag: str, result: NLResult) -> None:
        """Record a completed agent result into the query context."""
        async with self._lock:
            ctx = self._store.get(query_id)
            if ctx is not None:
                ctx.sub_results[agent_tag] = result

    async def mark_escalation(self, query_id: str, dept_tag: str) -> None:
        """Record that this dept triggered escalation for audit purposes."""
        async with self._lock:
            ctx = self._store.get(query_id)
            if ctx is not None and dept_tag not in ctx.escalations:
                ctx.escalations.append(dept_tag)

    async def cleanup(self, query_id: str) -> None:
        """Remove the query context. Call this when the response is sent."""
        async with self._lock:
            self._store.pop(query_id, None)

    # ── Housekeeping ──────────────────────────────────────────────────────────

    async def cleanup_stale(self, max_age: float = 120.0) -> int:
        """
        Remove contexts older than max_age seconds.
        Returns number of stale contexts removed.
        Called periodically (e.g. every 60s) by the Orchestrator.
        """
        now = time.monotonic()
        stale_ids = []
        async with self._lock:
            for qid, ctx in self._store.items():
                if now - ctx.started_at > max_age:
                    stale_ids.append(qid)
            for qid in stale_ids:
                del self._store[qid]

        if stale_ids:
            logger.warning(f"AgentMemory: removed {len(stale_ids)} stale query context(s)")
        return len(stale_ids)

    def __len__(self) -> int:
        return len(self._store)

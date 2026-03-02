"""
Semantic Cache Service — reduces LLM calls for repeated / near-duplicate queries.

Strategy
--------
1. On every answered query, store (query_embedding, answer, confidence) in SQLite.
2. On incoming query, compute its embedding and compare cosine similarity against
   every cached entry (filtered by TTL first).
3. If similarity > threshold (default 0.92), return the cached answer directly —
   skipping the full retrieval + generation pipeline.

TTL defaults
------------
- general : 3600 s  (1 hour)
- web     :  300 s  (5 minutes, web data goes stale quickly)

The SQLite file lives at  data/cache.db  (next to traces.db).

Thread-safety
-------------
Each operation opens its own connection with WAL mode; the cache never blocks
the query pipeline (all errors are swallowed and logged at DEBUG level).
"""

import json
import logging
import math
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "cache.db",
)

_DEFAULT_THRESHOLD = 0.92
_GENERAL_TTL = 3600   # 1 hour
_WEB_TTL = 300        # 5 minutes


# ── Helpers ────────────────────────────────────────────────────────────────────

def _cosine(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Service ────────────────────────────────────────────────────────────────────

class SemanticCache:
    """
    SQLite-backed semantic cache with cosine-similarity lookup.

    Usage::

        cache = SemanticCache()

        # On query arrival:
        hit = cache.get(query_embedding, query_type="general")
        if hit:
            return hit["answer"]

        # After successful answer generation:
        cache.set(query_embedding, answer, confidence=0.87, query_type="general")
    """

    def __init__(
        self,
        db_path: str = _DB_PATH,
        threshold: float = _DEFAULT_THRESHOLD,
    ):
        self.db_path = db_path
        self.threshold = threshold
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS query_cache (
                        cache_id    TEXT PRIMARY KEY,
                        embedding   TEXT NOT NULL,   -- JSON float array
                        answer      TEXT NOT NULL,
                        confidence  REAL,
                        query_type  TEXT DEFAULT 'general',
                        hit_count   INTEGER DEFAULT 0,
                        created_at  REAL NOT NULL,   -- unix timestamp
                        expires_at  REAL NOT NULL    -- unix timestamp
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cache_expires ON query_cache(expires_at)"
                )
        except Exception as exc:
            logger.debug("SemanticCache: failed to init DB: %s", exc)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ── Write ──────────────────────────────────────────────────────────────────

    def set(
        self,
        embedding: List[float],
        answer: str,
        confidence: Optional[float] = None,
        query_type: str = "general",
    ) -> None:
        """Store a new cache entry."""
        if not embedding or not answer:
            return
        try:
            import uuid
            now = time.time()
            ttl = _WEB_TTL if query_type == "web" else _GENERAL_TTL
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO query_cache
                      (cache_id, embedding, answer, confidence, query_type, hit_count, created_at, expires_at)
                    VALUES (?,?,?,?,?,0,?,?)
                    """,
                    (
                        str(uuid.uuid4()),
                        json.dumps(embedding),
                        answer[:4000],  # cap to avoid huge rows
                        confidence,
                        query_type,
                        now,
                        now + ttl,
                    ),
                )
            logger.debug("SemanticCache.set: stored entry (type=%s)", query_type)
        except Exception as exc:
            logger.debug("SemanticCache.set failed (non-fatal): %s", exc)

    # ── Read ───────────────────────────────────────────────────────────────────

    def get(
        self,
        embedding: List[float],
        query_type: str = "general",
    ) -> Optional[Dict[str, Any]]:
        """
        Look up a cached answer by cosine similarity.

        Returns the best matching entry dict (keys: answer, confidence,
        similarity, hit_count) or None if no match above threshold.
        """
        if not embedding:
            return None
        try:
            now = time.time()
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM query_cache WHERE expires_at > ?",
                    (now,),
                ).fetchall()

            if not rows:
                return None

            best: Optional[Dict[str, Any]] = None
            best_sim = -1.0

            for row in rows:
                try:
                    cached_emb = json.loads(row["embedding"])
                    sim = _cosine(embedding, cached_emb)
                    if sim > best_sim:
                        best_sim = sim
                        best = dict(row)
                except Exception:
                    continue

            if best_sim >= self.threshold and best is not None:
                # Increment hit counter (fire-and-forget)
                self._increment_hit(best["cache_id"])
                best.pop("embedding", None)  # don't return raw embedding
                best["similarity"] = round(best_sim, 4)
                logger.debug(
                    "SemanticCache.get: hit (sim=%.4f, type=%s)",
                    best_sim, best.get("query_type"),
                )
                return best

        except Exception as exc:
            logger.debug("SemanticCache.get failed (non-fatal): %s", exc)
        return None

    def _increment_hit(self, cache_id: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE query_cache SET hit_count = hit_count + 1 WHERE cache_id = ?",
                    (cache_id,),
                )
        except Exception:
            pass

    # ── Maintenance ────────────────────────────────────────────────────────────

    def evict_expired(self) -> int:
        """Delete all expired entries. Returns number of rows deleted."""
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM query_cache WHERE expires_at <= ?", (time.time(),)
                )
                deleted = cur.rowcount
            if deleted:
                logger.debug("SemanticCache: evicted %d expired entries", deleted)
            return deleted
        except Exception as exc:
            logger.debug("SemanticCache.evict_expired failed: %s", exc)
            return 0

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        try:
            now = time.time()
            with self._connect() as conn:
                total = conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
                active = conn.execute(
                    "SELECT COUNT(*) FROM query_cache WHERE expires_at > ?", (now,)
                ).fetchone()[0]
                hits = conn.execute(
                    "SELECT COALESCE(SUM(hit_count), 0) FROM query_cache"
                ).fetchone()[0]
            return {"total_entries": total, "active_entries": active, "total_hits": hits}
        except Exception as exc:
            logger.debug("SemanticCache.stats failed: %s", exc)
            return {}

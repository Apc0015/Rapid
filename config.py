"""
RAPID — Central configuration.
All locked parameters come from the implementation reference document.
"""

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE = 512          # tokens
CHUNK_OVERLAP = 64        # tokens

# ── Retrieval ─────────────────────────────────────────────────────────────────
RRF_ALPHA = 0.6           # weight for vector search in RRF
BM25_ALPHA = 0.4          # weight for BM25 keyword search in RRF
TOP_K = 10                # chunks returned per hybrid search

# ── Confidence thresholds ─────────────────────────────────────────────────────
HIGH_CONF = 0.65          # answer returned directly to user
LOW_CONF = 0.40           # below this → fallback (web search or escalation)

# ── DB ────────────────────────────────────────────────────────────────────────
def _resolve_db_path() -> str:
    """
    Return a writable SQLite path for the main rapid.db.
    Falls back to /tmp on filesystems that don't support SQLite journal files
    (e.g. certain network/overlay mounts used in sandboxed environments).
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path
    primary = _Path("data/db/rapid.db")
    try:
        primary.parent.mkdir(parents=True, exist_ok=True)
        _c = _sqlite3.connect(str(primary), timeout=3)
        _c.execute("CREATE TABLE IF NOT EXISTS _probe (x INTEGER)")
        _c.execute("INSERT INTO _probe VALUES (1)")
        _c.commit()
        _c.execute("DELETE FROM _probe")
        _c.commit()
        _c.close()
        return str(primary)
    except _sqlite3.OperationalError:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            f"[config] Cannot write to {primary} — using /tmp/rapid_main.db"
        )
        return "/tmp/rapid_main.db"

DB_PATH = _resolve_db_path()
DB_TIMEOUT_SECONDS = 30

# ── FAISS (per-department vector store) ──────────────────────────────────────
FAISS_BASE_DIR = "data/faiss"

# ── Schema cache ──────────────────────────────────────────────────────────────
SCHEMA_DIR = "data/schema"

# ── Embeddings ────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# ── LLM — OpenRouter (primary) ────────────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "anthropic/claude-3.5-haiku"   # fast + cheap for most calls
OPENROUTER_STRONG_MODEL = "anthropic/claude-3.5-sonnet"  # for decomposition + fusion

# ── LLM — Ollama (local fallback) ────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "llama3.2"

# ── Gap detection ─────────────────────────────────────────────────────────────
GAP_PATTERN_THRESHOLD = 3  # gap must appear 3+ times before escalation

# ── Audit ─────────────────────────────────────────────────────────────────────
AUDIT_RETENTION_YEARS = 7

# ── Phase 3: Vector store (Qdrant) ────────────────────────────────────────────
# Set USE_QDRANT=true to route all vector operations to Qdrant instead of FAISS.
# QDRANT_URL defaults to local Docker instance.
QDRANT_URL = "http://localhost:6333"

# ── Phase 3: Relational DB (PostgreSQL) ───────────────────────────────────────
# Set DATABASE_URL=postgresql://user:pass@host:5432/dbname to switch from SQLite.
# When unset, SQLite is used (existing behaviour).
DATABASE_URL = ""

# ── Phase 3: Redis (shared intent cache + optional task queue) ─────────────────
# Set REDIS_URL=redis://localhost:6379/0 to enable cross-worker intent caching.
# When unset, each worker uses its own in-process LRU cache.
REDIS_URL = ""

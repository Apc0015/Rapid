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
MIN_BID_CONF = 0.50       # minimum confidence for a bid to be considered

# ── Confidence scoring weights ────────────────────────────────────────────────
CONF_CONTEXT_WEIGHT = 0.30
CONF_FAITHFULNESS_WEIGHT = 0.50
CONF_COMPLETENESS_WEIGHT = 0.20

# ── DB ────────────────────────────────────────────────────────────────────────
DB_PATH = "data/db/rapid.db"
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
OLLAMA_MODEL = "llama3.1:8b"

# ── Gap detection ─────────────────────────────────────────────────────────────
GAP_PATTERN_THRESHOLD = 3  # gap must appear 3+ times before escalation

# ── Audit ─────────────────────────────────────────────────────────────────────
AUDIT_RETENTION_YEARS = 7

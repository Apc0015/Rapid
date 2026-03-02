import os
import sqlite3
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USER_DB_PATH = os.path.join(DB_DIR, "users.db")

# ---------------------------------------------------------------------------
# Pre-built RAG templates
# ---------------------------------------------------------------------------

RAG_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "fast_search": {
        "name": "Fast Search",
        "chunk_size": 256,
        "overlap_size": 32,
        "top_k": 3,
        "embedding_model": "text-embedding-ada-002",
        "search_mode": "semantic",
        "description": "Quick FAQ lookups and real-time chat",
        "trade_off": "Less context per chunk, faster responses",
    },
    "balanced": {
        "name": "Balanced",
        "chunk_size": 512,
        "overlap_size": 64,
        "top_k": 5,
        "embedding_model": "text-embedding-ada-002",
        "search_mode": "hybrid",
        "description": "General-purpose queries with optimal speed/quality",
        "trade_off": "Good balance between latency, cost, and answer quality",
    },
    "deep_analysis": {
        "name": "Deep Analysis",
        "chunk_size": 1024,
        "overlap_size": 128,
        "top_k": 8,
        "embedding_model": "text-embedding-ada-002",
        "search_mode": "hybrid",
        "description": "Research and detailed document analysis",
        "trade_off": "Slower but more comprehensive context",
    },
    "cost_optimized": {
        "name": "Cost Optimized",
        "chunk_size": 384,
        "overlap_size": 48,
        "top_k": 3,
        "embedding_model": "text-embedding-ada-002",
        "search_mode": "semantic",
        "description": "Cost-sensitive deployments with minimal API calls",
        "trade_off": "Lower cost, slightly reduced retrieval coverage",
    },
    "high_accuracy": {
        "name": "High Accuracy",
        "chunk_size": 768,
        "overlap_size": 96,
        "top_k": 10,
        "embedding_model": "text-embedding-ada-002",
        "search_mode": "hybrid",
        "description": "Mission-critical accuracy requirements",
        "trade_off": "Higher cost and latency, maximum retrieval quality",
    },
}

# Default template used when a user has no saved configuration
DEFAULT_TEMPLATE = "balanced"

# Validation bounds
CHUNK_SIZE_MIN, CHUNK_SIZE_MAX = 128, 2048
OVERLAP_MIN, OVERLAP_MAX = 0, 256
TOP_K_MIN, TOP_K_MAX = 1, 20


class RAGConfigurationService:
    """Manages per-user RAG configurations stored in SQLite."""

    def __init__(self):
        self._init_db()

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _init_db(self):
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(USER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_configurations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                config_name TEXT NOT NULL,
                config_type TEXT NOT NULL DEFAULT 'template',
                chunk_size INTEGER NOT NULL,
                overlap_size INTEGER NOT NULL,
                top_k INTEGER NOT NULL,
                embedding_model TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                template_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(USER_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row)

    @staticmethod
    def _validate_params(chunk_size: int, overlap_size: int, top_k: int):
        if not (CHUNK_SIZE_MIN <= chunk_size <= CHUNK_SIZE_MAX):
            raise ValueError(f"chunk_size must be between {CHUNK_SIZE_MIN} and {CHUNK_SIZE_MAX}")
        if not (OVERLAP_MIN <= overlap_size <= OVERLAP_MAX):
            raise ValueError(f"overlap_size must be between {OVERLAP_MIN} and {OVERLAP_MAX}")
        if not (TOP_K_MIN <= top_k <= TOP_K_MAX):
            raise ValueError(f"top_k must be between {TOP_K_MIN} and {TOP_K_MAX}")
        if overlap_size >= chunk_size:
            raise ValueError("overlap_size must be less than chunk_size")

    # ------------------------------------------------------------------
    # Template queries
    # ------------------------------------------------------------------

    def get_all_templates(self) -> List[Dict[str, Any]]:
        return [{"key": k, **v} for k, v in RAG_TEMPLATES.items()]

    def get_template_by_name(self, name: str) -> Dict[str, Any]:
        name = name.lower().replace(" ", "_")
        tmpl = RAG_TEMPLATES.get(name)
        if tmpl is None:
            raise ValueError(f"Unknown template: {name}")
        return {"key": name, **tmpl}

    # ------------------------------------------------------------------
    # User configuration CRUD
    # ------------------------------------------------------------------

    def get_user_active_config(self, username: str) -> Dict[str, Any]:
        """Return the user's active config, or the default balanced template."""
        conn = self._get_db()
        try:
            row = conn.execute(
                "SELECT * FROM rag_configurations WHERE username = ? AND is_active = 1",
                (username,),
            ).fetchone()
            if row:
                return self._row_to_dict(row)
            # No active config → return balanced defaults (not persisted yet)
            tmpl = RAG_TEMPLATES[DEFAULT_TEMPLATE]
            return {
                "id": None,
                "username": username,
                "config_name": tmpl["name"],
                "config_type": "template",
                "chunk_size": tmpl["chunk_size"],
                "overlap_size": tmpl["overlap_size"],
                "top_k": tmpl["top_k"],
                "embedding_model": tmpl["embedding_model"],
                "is_active": 1,
                "template_name": DEFAULT_TEMPLATE,
                "created_at": None,
                "updated_at": None,
            }
        finally:
            conn.close()

    def apply_template(self, username: str, template_name: str) -> Dict[str, Any]:
        """Deactivate existing configs and save the template as the active one."""
        tmpl = self.get_template_by_name(template_name)  # raises if unknown
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_db()
        try:
            # Deactivate all current configs for this user
            conn.execute(
                "UPDATE rag_configurations SET is_active = 0 WHERE username = ?",
                (username,),
            )
            # Insert new active config
            cursor = conn.execute(
                """INSERT INTO rag_configurations
                   (username, config_name, config_type, chunk_size, overlap_size,
                    top_k, embedding_model, is_active, template_name, created_at, updated_at)
                   VALUES (?, ?, 'template', ?, ?, ?, ?, 1, ?, ?, ?)""",
                (
                    username,
                    tmpl["name"],
                    tmpl["chunk_size"],
                    tmpl["overlap_size"],
                    tmpl["top_k"],
                    tmpl["embedding_model"],
                    tmpl["key"],
                    now,
                    now,
                ),
            )
            conn.commit()
            config_id = cursor.lastrowid

            logger.info("User %s applied template '%s' (config_id=%s)", username, template_name, config_id)
            return self.get_user_active_config(username)
        finally:
            conn.close()

    def create_custom_config(self, username: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a custom RAG config and set it as active."""
        chunk_size = config_data["chunk_size"]
        overlap_size = config_data["overlap_size"]
        top_k = config_data["top_k"]
        embedding_model = config_data.get("embedding_model", "text-embedding-ada-002")
        config_name = config_data.get("config_name", "Custom")

        self._validate_params(chunk_size, overlap_size, top_k)
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_db()
        try:
            # Deactivate all current configs
            conn.execute(
                "UPDATE rag_configurations SET is_active = 0 WHERE username = ?",
                (username,),
            )
            cursor = conn.execute(
                """INSERT INTO rag_configurations
                   (username, config_name, config_type, chunk_size, overlap_size,
                    top_k, embedding_model, is_active, template_name, created_at, updated_at)
                   VALUES (?, ?, 'custom', ?, ?, ?, ?, 1, NULL, ?, ?)""",
                (username, config_name, chunk_size, overlap_size, top_k, embedding_model, now, now),
            )
            conn.commit()
            config_id = cursor.lastrowid
            logger.info("User %s created custom config '%s' (id=%s)", username, config_name, config_id)

            row = conn.execute("SELECT * FROM rag_configurations WHERE id = ?", (config_id,)).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_user_custom_configs(self, username: str) -> List[Dict[str, Any]]:
        conn = self._get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM rag_configurations WHERE username = ? AND config_type = 'custom' ORDER BY updated_at DESC",
                (username,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def delete_custom_config(self, username: str, config_id: int) -> bool:
        conn = self._get_db()
        try:
            row = conn.execute(
                "SELECT * FROM rag_configurations WHERE id = ? AND username = ? AND config_type = 'custom'",
                (config_id, username),
            ).fetchone()
            if not row:
                return False

            was_active = row["is_active"]
            conn.execute("DELETE FROM rag_configurations WHERE id = ?", (config_id,))

            # If the deleted config was active, fall back to balanced
            if was_active:
                conn.execute(
                    "UPDATE rag_configurations SET is_active = 0 WHERE username = ?",
                    (username,),
                )

            conn.commit()
            logger.info("User %s deleted custom config id=%s", username, config_id)
            return True
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Engine integration
    # ------------------------------------------------------------------

    def get_active_params(self, username: Optional[str] = None) -> Tuple[int, int, int, str, str]:
        """Return (chunk_size, overlap_size, top_k, embedding_model, search_mode) for the user.

        Falls back to the balanced template when no user or no saved config.
        """
        if username:
            cfg = self.get_user_active_config(username)
        else:
            tmpl = RAG_TEMPLATES[DEFAULT_TEMPLATE]
            cfg = tmpl

        return (
            cfg["chunk_size"],
            cfg["overlap_size"],
            cfg["top_k"],
            cfg.get("embedding_model", "text-embedding-ada-002"),
            cfg.get("search_mode", "hybrid"),
        )

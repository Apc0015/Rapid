from __future__ import annotations
"""
DeptConfig — per-department RAG and DB configuration.

Stores two JSON files under data/:
  data/dept_rag_config.json   — RAG settings per department
  data/dept_db_config.json    — DB connection settings per department

Admin can read/write these via the API.
Each department agent reads its own config when executing pipelines.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEPTS = [
    "hr", "finance", "legal", "sales", "marketing",
    "ops", "it", "procurement", "rd", "customer_success",
]

# ── Default RAG config per dept ───────────────────────────────────────────────

_DEFAULT_RAG = {
    "embedding_model":      "nomic-embed-text",  # Ollama model name
    "chunk_size":           512,                  # tokens (approx)
    "chunk_overlap":        64,
    "top_k":                10,
    "similarity_threshold": 0.25,                 # min cosine similarity
    "rrf_alpha":            0.6,                  # vector weight in RRF
    "bm25_alpha":           0.4,                  # BM25 weight in RRF
    "hyde_enabled":         True,                 # HyDE query rewriting
}

# ── Default DB config per dept ─────────────────────────────────────────────────

def _default_db(dept: str) -> dict:
    return {
        "type":    "sqlite",             # sqlite | postgresql | mysql
        "path":    f"data/db/{dept}.db", # used when type=sqlite
        "host":    "",                   # used when type=postgresql/mysql
        "port":    5432,
        "name":    "",
        "user":    "",
        "password": "",
        "enabled": False,                # False = use shared rapid.db fallback
    }


# ── DeptConfig class ──────────────────────────────────────────────────────────

class DeptConfig:

    def __init__(
        self,
        rag_config_path: str = "data/dept_rag_config.json",
        db_config_path:  str = "data/dept_db_config.json",
    ):
        self._rag_path = Path(rag_config_path)
        self._db_path  = Path(db_config_path)
        self._rag: Dict[str, dict] = {}
        self._db:  Dict[str, dict] = {}
        self._load()

    # ── RAG config ────────────────────────────────────────────────────────────

    def get_rag(self, dept: str) -> dict:
        """Return RAG config for dept, filling missing keys from defaults."""
        base = dict(_DEFAULT_RAG)
        base.update(self._rag.get(dept, {}))
        return base

    def set_rag(self, dept: str, updates: dict) -> dict:
        """Merge updates into dept RAG config and persist."""
        current = self.get_rag(dept)
        current.update({k: v for k, v in updates.items() if k in _DEFAULT_RAG})
        self._rag[dept] = current
        self._save_rag()
        return current

    def all_rag(self) -> Dict[str, dict]:
        """Return RAG config for all departments."""
        return {d: self.get_rag(d) for d in _DEPTS}

    # ── DB config ─────────────────────────────────────────────────────────────

    def get_db(self, dept: str) -> dict:
        """Return DB config for dept."""
        base = _default_db(dept)
        base.update(self._db.get(dept, {}))
        return base

    def set_db(self, dept: str, updates: dict) -> dict:
        """Merge updates into dept DB config and persist."""
        current = self.get_db(dept)
        allowed = {"type", "path", "host", "port", "name", "user", "password", "enabled"}
        current.update({k: v for k, v in updates.items() if k in allowed})
        self._db[dept] = current
        self._save_db()
        return current

    def all_db(self) -> Dict[str, dict]:
        """Return DB config for all departments (passwords redacted)."""
        result = {}
        for d in _DEPTS:
            cfg = self.get_db(d)
            cfg["password"] = "***" if cfg.get("password") else ""
            result[d] = cfg
        return result

    def get_db_connection_string(self, dept: str) -> Optional[str]:
        """
        Return a connection string or path for the dept's DB.
        Returns None if the dept DB is not enabled.
        """
        cfg = self.get_db(dept)
        if not cfg.get("enabled"):
            return None
        if cfg["type"] == "sqlite":
            return cfg["path"] or f"data/db/{dept}.db"
        if cfg["type"] in ("postgresql", "mysql"):
            driver = "postgresql" if cfg["type"] == "postgresql" else "mysql+pymysql"
            user = cfg.get("user", "")
            pwd  = cfg.get("password", "")
            host = cfg.get("host", "localhost")
            port = cfg.get("port", 5432)
            name = cfg.get("name", dept)
            return f"{driver}://{user}:{pwd}@{host}:{port}/{name}"
        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self):
        if self._rag_path.exists():
            try:
                self._rag = json.loads(self._rag_path.read_text())
            except Exception as e:
                logger.warning(f"Could not load RAG config: {e}")
                self._rag = {}
        else:
            # Write defaults on first run
            self._rag = {}
            self._save_rag()

        if self._db_path.exists():
            try:
                self._db = json.loads(self._db_path.read_text())
            except Exception as e:
                logger.warning(f"Could not load DB config: {e}")
                self._db = {}
        else:
            self._db = {}
            self._save_db()

    def _save_rag(self):
        _atomic_write(self._rag_path, self._rag)

    def _save_db(self):
        _atomic_write(self._db_path, self._db)


def _atomic_write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Singleton ─────────────────────────────────────────────────────────────────

_dept_config: Optional[DeptConfig] = None


def get_dept_config() -> DeptConfig:
    global _dept_config
    if _dept_config is None:
        _dept_config = DeptConfig()
    return _dept_config

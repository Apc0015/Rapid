from __future__ import annotations
"""
infrastructure/custom_agent_store.py

SQLite-backed store for dynamically created specialist agent configurations.
Each record defines a custom agent that can be injected into any department's
IntraDeptOrchestrator at runtime — no code changes or restarts required.

Table: custom_agents
  agent_id        TEXT PRIMARY KEY  (uuid4)
  dept_tag        TEXT              e.g. "finance"
  role_title      TEXT              e.g. "Tax Specialist"
  specialization  TEXT              one-liner shown in prompts
  bid_keywords    TEXT              JSON list of trigger keywords
  permitted_tables TEXT             JSON list of allowed DB tables
  doc_folders     TEXT             JSON list of RAG doc paths
  tools_available TEXT             JSON list: ["db_query","document_search","calculation"]
  system_prompt   TEXT             optional extra system instructions
  created_by      TEXT             user_id of creator
  created_at      TEXT             ISO timestamp
  updated_at      TEXT             ISO timestamp
  active          INTEGER          1 = live, 0 = disabled
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger("rapid.custom_agent_store")

_VALID_TOOLS = {"db_query", "document_search", "calculation", "peer_consult"}
_VALID_DEPTS = {
    "finance", "hr", "legal", "sales", "marketing",
    "ops", "it", "procurement", "rd", "customer_success",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    db_path = config.DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=config.DB_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_agents (
                agent_id        TEXT PRIMARY KEY,
                dept_tag        TEXT NOT NULL,
                role_title      TEXT NOT NULL,
                specialization  TEXT NOT NULL DEFAULT '',
                bid_keywords    TEXT NOT NULL DEFAULT '[]',
                permitted_tables TEXT NOT NULL DEFAULT '[]',
                doc_folders     TEXT NOT NULL DEFAULT '[]',
                tools_available TEXT NOT NULL DEFAULT '["db_query","document_search"]',
                system_prompt   TEXT NOT NULL DEFAULT '',
                created_by      TEXT NOT NULL DEFAULT 'admin',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                active          INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()


# ── Public API ────────────────────────────────────────────────────────────────

def create_custom_agent(
    dept_tag: str,
    role_title: str,
    specialization: str = "",
    bid_keywords: Optional[List[str]] = None,
    permitted_tables: Optional[List[str]] = None,
    doc_folders: Optional[List[str]] = None,
    tools_available: Optional[List[str]] = None,
    system_prompt: str = "",
    created_by: str = "admin",
) -> Dict[str, Any]:
    """
    Create and persist a new custom agent config.
    Returns the full agent record as a dict.
    Raises ValueError on invalid input.
    """
    _ensure_table()

    if dept_tag not in _VALID_DEPTS:
        raise ValueError(f"Unknown dept_tag '{dept_tag}'. Valid: {sorted(_VALID_DEPTS)}")
    if not role_title.strip():
        raise ValueError("role_title must not be empty")

    # Validate tools
    tools = tools_available or ["db_query", "document_search"]
    invalid_tools = set(tools) - _VALID_TOOLS
    if invalid_tools:
        raise ValueError(f"Invalid tools: {invalid_tools}. Valid: {_VALID_TOOLS}")

    agent_id = str(uuid.uuid4())
    now = _now()

    record = {
        "agent_id":        agent_id,
        "dept_tag":        dept_tag,
        "role_title":      role_title.strip(),
        "specialization":  specialization.strip(),
        "bid_keywords":    json.dumps(bid_keywords or []),
        "permitted_tables": json.dumps(permitted_tables or []),
        "doc_folders":     json.dumps(doc_folders or []),
        "tools_available": json.dumps(tools),
        "system_prompt":   system_prompt.strip(),
        "created_by":      created_by,
        "created_at":      now,
        "updated_at":      now,
        "active":          1,
    }

    with _conn() as conn:
        conn.execute("""
            INSERT INTO custom_agents
            (agent_id, dept_tag, role_title, specialization,
             bid_keywords, permitted_tables, doc_folders, tools_available,
             system_prompt, created_by, created_at, updated_at, active)
            VALUES
            (:agent_id, :dept_tag, :role_title, :specialization,
             :bid_keywords, :permitted_tables, :doc_folders, :tools_available,
             :system_prompt, :created_by, :created_at, :updated_at, :active)
        """, record)
        conn.commit()

    logger.info(f"[CustomAgentStore] Created agent '{role_title}' for dept={dept_tag} (id={agent_id})")
    return _deserialise(record)


def get_custom_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    """Return one agent record by ID, or None if not found."""
    _ensure_table()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM custom_agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
    return _deserialise(dict(row)) if row else None


def list_custom_agents(
    dept_tag: Optional[str] = None,
    active_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    List all custom agents, optionally filtered by dept and/or active status.
    """
    _ensure_table()
    sql = "SELECT * FROM custom_agents WHERE 1=1"
    params: List[Any] = []
    if dept_tag:
        sql += " AND dept_tag = ?"
        params.append(dept_tag)
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY dept_tag, role_title"

    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_deserialise(dict(r)) for r in rows]


def update_custom_agent(
    agent_id: str,
    **fields: Any,
) -> Optional[Dict[str, Any]]:
    """
    Update specific fields of a custom agent.
    Allowed fields: role_title, specialization, bid_keywords,
    permitted_tables, doc_folders, tools_available, system_prompt, active.
    Returns updated record or None if not found.
    """
    _ensure_table()
    allowed = {
        "role_title", "specialization", "bid_keywords",
        "permitted_tables", "doc_folders", "tools_available",
        "system_prompt", "active",
    }
    updates: Dict[str, Any] = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        # Serialise list fields
        if k in {"bid_keywords", "permitted_tables", "doc_folders", "tools_available"}:
            if isinstance(v, list):
                v = json.dumps(v)
        updates[k] = v

    if not updates:
        return get_custom_agent(agent_id)

    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [agent_id]

    with _conn() as conn:
        conn.execute(
            f"UPDATE custom_agents SET {set_clause} WHERE agent_id = ?", params
        )
        conn.commit()

    logger.info(f"[CustomAgentStore] Updated agent {agent_id}: {list(updates.keys())}")
    return get_custom_agent(agent_id)


def delete_custom_agent(agent_id: str) -> bool:
    """Hard-delete a custom agent. Returns True if found and deleted."""
    _ensure_table()
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM custom_agents WHERE agent_id = ?", (agent_id,)
        )
        conn.commit()
    deleted = cur.rowcount > 0
    if deleted:
        logger.info(f"[CustomAgentStore] Deleted agent {agent_id}")
    return deleted


# ── Internal ──────────────────────────────────────────────────────────────────

def _deserialise(record: Dict[str, Any]) -> Dict[str, Any]:
    """Convert JSON-encoded list fields back to Python lists."""
    for field in ("bid_keywords", "permitted_tables", "doc_folders", "tools_available"):
        val = record.get(field, "[]")
        if isinstance(val, str):
            try:
                record[field] = json.loads(val)
            except Exception:
                record[field] = []
    record["active"] = bool(record.get("active", 1))
    return record

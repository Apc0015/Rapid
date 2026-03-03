"""
Column Registry — SQLite-backed Allow/Anonymize/Block rules per column.

Schema:
  column_rules: per-column governance states with optional dept/role overrides
  policy_documents: uploaded policy documents (stored for reference)
"""

import os
import json
import sqlite3
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
GOVERNANCE_DB_PATH = os.path.join(DATA_DIR, "governance.db")

VALID_STATES = ("allowed", "anonymize", "block")


@dataclass
class ColumnRule:
    table_name: str
    column_name: str
    default_state: str = "allowed"           # "allowed" | "anonymize" | "block"
    dept_overrides: Dict[str, str] = field(default_factory=dict)   # dept -> state
    role_overrides: Dict[str, str] = field(default_factory=dict)   # role -> state
    updated_at: str = ""

    def __post_init__(self):
        if self.default_state not in VALID_STATES:
            raise ValueError(f"Invalid state: {self.default_state}")
        if not self.updated_at:
            self.updated_at = datetime.now(timezone.utc).isoformat()


class ColumnRegistry:
    """SQLite-backed registry for column-level governance rules."""

    def __init__(self, db_path: str = GOVERNANCE_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS column_rules (
                    table_name      TEXT NOT NULL,
                    column_name     TEXT NOT NULL,
                    default_state   TEXT NOT NULL DEFAULT 'allowed',
                    dept_overrides  TEXT NOT NULL DEFAULT '{}',
                    role_overrides  TEXT NOT NULL DEFAULT '{}',
                    updated_at      TEXT NOT NULL,
                    PRIMARY KEY (table_name, column_name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS policy_documents (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename    TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL
                )
            """)
            conn.commit()

    # ─── Column Rules ─────────────────────────────────────────────────────────

    def upsert_rule(self, rule: ColumnRule) -> None:
        if rule.default_state not in VALID_STATES:
            raise ValueError(f"Invalid state: {rule.default_state}")
        rule.updated_at = datetime.now(timezone.utc).isoformat()
        with self._get_db() as conn:
            conn.execute(
                """
                INSERT INTO column_rules
                    (table_name, column_name, default_state, dept_overrides, role_overrides, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(table_name, column_name)
                DO UPDATE SET
                    default_state  = excluded.default_state,
                    dept_overrides = excluded.dept_overrides,
                    role_overrides = excluded.role_overrides,
                    updated_at     = excluded.updated_at
                """,
                (
                    rule.table_name,
                    rule.column_name,
                    rule.default_state,
                    json.dumps(rule.dept_overrides),
                    json.dumps(rule.role_overrides),
                    rule.updated_at,
                ),
            )
            conn.commit()

    def get_rule(self, table_name: str, column_name: str) -> Optional[ColumnRule]:
        with self._get_db() as conn:
            row = conn.execute(
                "SELECT * FROM column_rules WHERE table_name = ? AND column_name = ?",
                (table_name, column_name),
            ).fetchone()
        if not row:
            return None
        return ColumnRule(
            table_name=row["table_name"],
            column_name=row["column_name"],
            default_state=row["default_state"],
            dept_overrides=json.loads(row["dept_overrides"] or "{}"),
            role_overrides=json.loads(row["role_overrides"] or "{}"),
            updated_at=row["updated_at"],
        )

    def list_rules(self, table_name: Optional[str] = None) -> List[ColumnRule]:
        with self._get_db() as conn:
            if table_name:
                rows = conn.execute(
                    "SELECT * FROM column_rules WHERE table_name = ? ORDER BY column_name",
                    (table_name,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM column_rules ORDER BY table_name, column_name"
                ).fetchall()
        return [
            ColumnRule(
                table_name=r["table_name"],
                column_name=r["column_name"],
                default_state=r["default_state"],
                dept_overrides=json.loads(r["dept_overrides"] or "{}"),
                role_overrides=json.loads(r["role_overrides"] or "{}"),
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def delete_rule(self, table_name: str, column_name: str) -> None:
        with self._get_db() as conn:
            conn.execute(
                "DELETE FROM column_rules WHERE table_name = ? AND column_name = ?",
                (table_name, column_name),
            )
            conn.commit()

    def list_tables(self) -> List[str]:
        with self._get_db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT table_name FROM column_rules ORDER BY table_name"
            ).fetchall()
        return [r["table_name"] for r in rows]

    # ─── Policy Documents ─────────────────────────────────────────────────────

    def save_policy_document(self, filename: str, content: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO policy_documents (filename, content, uploaded_at) VALUES (?, ?, ?)",
                (filename, content, now),
            )
            conn.commit()
            return cursor.lastrowid

    def list_policy_documents(self) -> List[Dict]:
        with self._get_db() as conn:
            rows = conn.execute(
                "SELECT id, filename, uploaded_at FROM policy_documents ORDER BY uploaded_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

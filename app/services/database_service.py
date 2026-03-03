"""
Database Service — read-only connections to PostgreSQL, MySQL, SQLite.

IMPORTANT: `get_db_schema_context()` intentionally does NOT exist here.
Schema information is consumed only by D2 (Schema Analyzer) and never
passed to the LLM directly.
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional

import pandas as pd

try:
    from sqlalchemy import create_engine, text, inspect
    from sqlalchemy.engine import Engine
    _SQLALCHEMY_AVAILABLE = True
    _SQLALCHEMY_ERROR: Optional[BaseException] = None
except Exception as exc:
    create_engine = None  # type: ignore
    text = None           # type: ignore
    inspect = None        # type: ignore
    Engine = Any          # type: ignore
    _SQLALCHEMY_AVAILABLE = False
    _SQLALCHEMY_ERROR = exc

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


class DatabaseService:
    """Read-only database connection manager."""

    def __init__(self):
        self.connections: Dict[str, Engine] = {}
        # Maps username -> list of conn_ids
        self.user_connections: Dict[str, List[str]] = {}

    def _require_sqlalchemy(self) -> None:
        if not _SQLALCHEMY_AVAILABLE:
            raise RuntimeError(
                f"SQLAlchemy unavailable: {_SQLALCHEMY_ERROR}"
            )

    # ─── Connection management ─────────────────────────────────────────────────

    def register_user_connection(self, username: str, conn_id: str) -> None:
        if username not in self.user_connections:
            self.user_connections[username] = []
        if conn_id not in self.user_connections[username]:
            self.user_connections[username].append(conn_id)

    def remove_user_connection(self, username: str, conn_id: str) -> None:
        if username in self.user_connections:
            self.user_connections[username] = [
                c for c in self.user_connections[username] if c != conn_id
            ]

    def get_user_connections(self, username: str) -> List[str]:
        return [
            c for c in self.user_connections.get(username, [])
            if c in self.connections
        ]

    def connect_to_postgres(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        ssl_mode: str = "prefer",
    ) -> str:
        self._require_sqlalchemy()
        conn_str = (
            f"postgresql://{username}:{password}@{host}:{port}/{database}"
            f"?sslmode={ssl_mode}"
        )
        engine = create_engine(conn_str)
        conn_id = f"postgres_{host}_{database}"
        self.connections[conn_id] = engine
        return conn_id

    def connect_to_mysql(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
    ) -> str:
        self._require_sqlalchemy()
        conn_str = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
        engine = create_engine(conn_str)
        conn_id = f"mysql_{host}_{database}"
        self.connections[conn_id] = engine
        return conn_id

    def connect_to_sqlite(self, db_path: str, label: str = "") -> str:
        self._require_sqlalchemy()
        engine = create_engine(f"sqlite:///{db_path}")
        conn_id = f"sqlite_{label or os.path.basename(db_path)}"
        self.connections[conn_id] = engine
        return conn_id

    def close_connection(self, conn_id: str):
        if conn_id in self.connections:
            self.connections[conn_id].dispose()
            del self.connections[conn_id]

    # ─── Schema introspection (metadata only, never data) ─────────────────────

    def list_tables(self, conn_id: str) -> List[str]:
        self._require_sqlalchemy()
        if conn_id not in self.connections:
            raise ValueError(f"Connection {conn_id!r} not found")
        try:
            inspector = inspect(self.connections[conn_id])
            return inspector.get_table_names()
        except Exception as e:
            logger.warning("list_tables failed for %s: %s", conn_id, e)
            return []

    def get_table_schema(self, conn_id: str, table_name: str) -> Dict[str, Any]:
        """Return column metadata only — no row data."""
        self._require_sqlalchemy()
        if conn_id not in self.connections:
            raise ValueError(f"Connection {conn_id!r} not found")
        _validate_identifier(table_name)
        engine = self.connections[conn_id]
        try:
            inspector = inspect(engine)
            columns = [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                }
                for col in inspector.get_columns(table_name)
            ]
        except Exception as e:
            logger.warning("get_table_schema fallback for %s.%s: %s", conn_id, table_name, e)
            columns = []
            with engine.connect() as conn:
                if "postgres" in conn_id:
                    result = conn.execute(
                        text(
                            "SELECT column_name, data_type, is_nullable "
                            "FROM information_schema.columns "
                            "WHERE table_name = :tbl ORDER BY ordinal_position"
                        ),
                        {"tbl": table_name},
                    )
                    for row in result.fetchall():
                        columns.append({
                            "name": row[0],
                            "type": row[1],
                            "nullable": row[2] == "YES",
                        })
        return {"table_name": table_name, "columns": columns, "connection_id": conn_id}

    # ─── Query execution (used only by D4 — Result Verifier) ──────────────────

    def execute_query(self, conn_id: str, query: str) -> pd.DataFrame:
        """Execute a pre-validated SELECT query. Returns raw DataFrame for D4/D5 only."""
        self._require_sqlalchemy()
        if conn_id not in self.connections:
            raise ValueError(f"Connection {conn_id!r} not found")
        engine = self.connections[conn_id]
        with engine.connect() as connection:
            result = connection.execute(text(query))
            if result.returns_rows:
                return pd.DataFrame(result.fetchall(), columns=list(result.keys()))
            return pd.DataFrame()

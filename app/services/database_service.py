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
    create_engine = None  # type: ignore[assignment]
    text = None  # type: ignore[assignment]
    inspect = None  # type: ignore[assignment]
    Engine = Any  # type: ignore[misc, assignment]
    _SQLALCHEMY_AVAILABLE = False
    _SQLALCHEMY_ERROR = exc

logger = logging.getLogger(__name__)

# Pattern to validate table/column identifiers (alphanumeric + underscores only)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str) -> str:
    """Validate that a SQL identifier contains only safe characters."""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


class CloudDatabaseService:
    """Service for connecting to cloud databases"""

    def __init__(self):
        self.connections: Dict[str, Engine] = {}
        # Maps username -> list of conn_ids they have active
        self.user_connections: Dict[str, List[str]] = {}

    def register_user_connection(self, username: str, conn_id: str) -> None:
        """Associate a connection with a user."""
        if username not in self.user_connections:
            self.user_connections[username] = []
        if conn_id not in self.user_connections[username]:
            self.user_connections[username].append(conn_id)

    def remove_user_connection(self, username: str, conn_id: str) -> None:
        """Remove a connection from a user's active list."""
        if username in self.user_connections:
            self.user_connections[username] = [
                c for c in self.user_connections[username] if c != conn_id
            ]

    def get_user_connections(self, username: str) -> List[str]:
        """Return list of active conn_ids for a user."""
        return [
            c for c in self.user_connections.get(username, [])
            if c in self.connections
        ]

    def get_db_schema_context(self, conn_ids: List[str]) -> str:
        """Return a text summary of table schemas for all given connections.

        Used to give the LLM enough context to generate correct SQL.
        """
        if not conn_ids:
            return ""
        parts: List[str] = []
        for conn_id in conn_ids:
            if conn_id not in self.connections:
                continue
            try:
                tables = self.list_tables(conn_id)
                parts.append(f"Database connection: {conn_id}")
                for table in tables[:20]:  # cap at 20 tables
                    try:
                        schema = self.get_table_schema(conn_id, table)
                        cols = ", ".join(
                            f"{c['name']} ({c['type']})"
                            for c in schema.get("columns", [])
                        )
                        parts.append(f"  Table {table}: {cols}")
                    except Exception:
                        parts.append(f"  Table {table}: (schema unavailable)")
            except Exception as e:
                parts.append(f"Database connection {conn_id}: (unavailable: {e})")
        return "\n".join(parts)

    def _require_sqlalchemy(self) -> None:
        if not _SQLALCHEMY_AVAILABLE:
            raise RuntimeError(
                "SQLAlchemy failed to import in this environment. "
                "Database features are disabled. "
                f"Import error: {_SQLALCHEMY_ERROR}"
            )

    def connect_to_postgres(self, host: str, port: int, database: str,
                            username: str, password: str, ssl_mode: str = "require") -> str:
        """Connect to PostgreSQL database"""
        self._require_sqlalchemy()
        connection_string = f"postgresql://{username}:{password}@{host}:{port}/{database}?sslmode={ssl_mode}"
        engine = create_engine(connection_string)
        conn_id = f"postgres_{host}_{database}"
        self.connections[conn_id] = engine
        return conn_id

    def connect_to_mysql(self, host: str, port: int, database: str,
                         username: str, password: str) -> str:
        """Connect to MySQL database"""
        self._require_sqlalchemy()
        connection_string = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
        engine = create_engine(connection_string)
        conn_id = f"mysql_{host}_{database}"
        self.connections[conn_id] = engine
        return conn_id

    def execute_query(self, conn_id: str, query: str) -> pd.DataFrame:
        """Execute SQL query and return results as DataFrame"""
        self._require_sqlalchemy()
        if conn_id not in self.connections:
            raise ValueError(f"Connection {conn_id} not found")

        engine = self.connections[conn_id]
        with engine.connect() as connection:
            result = connection.execute(text(query))
            if result.returns_rows:
                return pd.DataFrame(result.fetchall(), columns=result.keys())
            else:
                connection.commit()
                return pd.DataFrame({"result": ["Query executed successfully"]})

    def get_table_schema(self, conn_id: str, table_name: str) -> Dict[str, Any]:
        """Get schema information for a table using parameterized queries."""
        self._require_sqlalchemy()
        if conn_id not in self.connections:
            raise ValueError(f"Connection {conn_id} not found")

        _validate_identifier(table_name)

        engine = self.connections[conn_id]

        # Use SQLAlchemy inspect for a safe, cross-database approach
        try:
            inspector = inspect(engine)
            columns_info = inspector.get_columns(table_name)
            columns = [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "default": str(col.get("default")) if col.get("default") else None,
                }
                for col in columns_info
            ]
        except Exception as e:
            logger.warning("Failed to inspect table %s: %s", table_name, e)
            # Fallback: use parameterized query for Postgres
            columns = []
            with engine.connect() as connection:
                if "postgres" in conn_id:
                    result = connection.execute(
                        text("SELECT column_name, data_type, is_nullable, column_default "
                             "FROM information_schema.columns "
                             "WHERE table_name = :tbl ORDER BY ordinal_position"),
                        {"tbl": table_name},
                    )
                    for row in result.fetchall():
                        columns.append({
                            "name": row[0],
                            "type": row[1],
                            "nullable": row[2] == "YES",
                            "default": row[3],
                        })

        return {
            "table_name": table_name,
            "columns": columns,
            "connection_id": conn_id,
        }

    def list_tables(self, conn_id: str) -> list:
        """List all tables in the database"""
        self._require_sqlalchemy()
        if conn_id not in self.connections:
            raise ValueError(f"Connection {conn_id} not found")

        engine = self.connections[conn_id]

        # Use SQLAlchemy inspect for safe, cross-database table listing
        try:
            inspector = inspect(engine)
            return inspector.get_table_names()
        except Exception as e:
            logger.warning("Failed to list tables via inspector: %s", e)
            return []

    def close_connection(self, conn_id: str):
        """Close a database connection"""
        if conn_id in self.connections:
            self.connections[conn_id].dispose()
            del self.connections[conn_id]

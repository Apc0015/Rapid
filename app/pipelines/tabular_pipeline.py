"""
Tabular Data Pipeline for Intelligent Auto-RAG.

When a user uploads a CSV, Excel, or Parquet file:
  1. Load it into a SQLite database (data/tabular_uploads.db)
  2. Register it as a connection in CloudDatabaseService
  3. The existing DatabaseProxyAgent then handles NL-to-SQL queries

This makes uploaded tabular files indistinguishable from live
database connections from the query pipeline's perspective.
"""

import os
import re
import logging
import sqlite3
from typing import Optional, List, TYPE_CHECKING

import pandas as pd
from sqlalchemy import create_engine, text

if TYPE_CHECKING:
    from app.services.document_classifier import ClassificationResult
    from app.services.database_service import CloudDatabaseService

logger = logging.getLogger(__name__)

# Path to the dedicated SQLite database for tabular uploads
_TABULAR_DB_PATH = os.path.join("data", "tabular_uploads.db")
_TABULAR_DB_URL = f"sqlite:///{_TABULAR_DB_PATH}"

# Max rows to load (safety cap to avoid OOM on huge files)
_MAX_ROWS = 500_000


def _sanitize_table_name(doc_id: str) -> str:
    """Convert a doc_id UUID into a safe SQLite table name."""
    safe = re.sub(r"[^a-zA-Z0-9]", "_", doc_id)
    return f"tbl_{safe}"


def _sanitize_sheet_name(sheet: str) -> str:
    """Convert an Excel sheet name into a safe SQLite table suffix."""
    safe = re.sub(r"[^a-zA-Z0-9]", "_", str(sheet))
    return safe[:30]  # SQLite table names have no hard limit but keep it short


class TabularPipeline:
    """
    Ingests tabular files (CSV, Excel, Parquet, flat JSON) into SQLite
    and registers them as queryable connections in CloudDatabaseService.

    Each uploaded file becomes one or more SQLite tables inside
    data/tabular_uploads.db, accessible via conn_id = "tabular_{doc_id[:8]}".
    """

    def __init__(self, database_service: "CloudDatabaseService"):
        self.database_service = database_service
        self._ensure_db_dir()

    # ─── Public API ───────────────────────────────────────────────────────────

    def ingest(
        self,
        file_path: str,
        doc_id: str,
        username: str,
        org_id: str,
        filename: str,
        classification: Optional["ClassificationResult"] = None,
    ) -> str:
        """
        Load a tabular file into SQLite and register it as a DB connection.

        Args:
            file_path: Absolute path to the saved file.
            doc_id: Document UUID.
            username: Owner's username.
            org_id: Organization ID.
            filename: Original filename (used to detect extension).
            classification: ClassificationResult from DocumentClassifier (optional).

        Returns:
            conn_id: The connection ID registered in database_service
                     (e.g. "tabular_a3f8c1d2").
        """
        ext = os.path.splitext(filename.lower())[1]
        conn_id = self._make_conn_id(doc_id)

        logger.info("TabularPipeline.ingest: %s → conn_id=%s", filename, conn_id)

        try:
            table_names = self._load_file_to_sqlite(file_path, doc_id, filename, ext)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load tabular file '{filename}' into SQLite: {e}"
            ) from e

        # Create a SQLAlchemy engine pointing at the tabular uploads DB
        engine = create_engine(_TABULAR_DB_URL, connect_args={"check_same_thread": False})

        # Register in database_service (bypassing the connect_to_postgres etc. methods
        # by directly placing the engine into connections dict)
        self.database_service.connections[conn_id] = engine
        self.database_service.register_user_connection(username, conn_id)

        logger.info(
            "TabularPipeline: registered conn_id=%s with tables=%s for user=%s",
            conn_id, table_names, username,
        )
        return conn_id

    def remove(self, doc_id: str, username: str) -> None:
        """
        Drop the SQLite table(s) for a document and deregister the connection.

        Args:
            doc_id: Document UUID.
            username: Owner's username.
        """
        conn_id = self._make_conn_id(doc_id)

        # Drop table(s) from SQLite
        try:
            con = sqlite3.connect(_TABULAR_DB_PATH)
            cur = con.cursor()
            # Find tables that start with this doc_id prefix
            base_name = _sanitize_table_name(doc_id)
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                (f"{base_name}%",),
            )
            tables = [row[0] for row in cur.fetchall()]
            for table in tables:
                cur.execute(f"DROP TABLE IF EXISTS [{table}]")
                logger.info("TabularPipeline: dropped table %s", table)
            con.commit()
            con.close()
        except Exception as e:
            logger.warning("TabularPipeline.remove: could not drop tables for %s: %s", doc_id, e)

        # Deregister from database_service
        self.database_service.close_connection(conn_id)
        self.database_service.remove_user_connection(username, conn_id)

    def get_conn_id(self, doc_id: str) -> str:
        """Return the connection ID for a given doc_id."""
        return self._make_conn_id(doc_id)

    def list_tables_for_doc(self, doc_id: str) -> List[str]:
        """List SQLite table names associated with a doc_id."""
        base_name = _sanitize_table_name(doc_id)
        try:
            con = sqlite3.connect(_TABULAR_DB_PATH)
            cur = con.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                (f"{base_name}%",),
            )
            tables = [row[0] for row in cur.fetchall()]
            con.close()
            return tables
        except Exception:
            return []

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _make_conn_id(doc_id: str) -> str:
        """Deterministic conn_id from doc_id."""
        short = re.sub(r"[^a-zA-Z0-9]", "", doc_id)[:12]
        return f"tabular_{short}"

    @staticmethod
    def _ensure_db_dir() -> None:
        """Create the data/ directory if it doesn't exist."""
        os.makedirs("data", exist_ok=True)

    def _load_file_to_sqlite(
        self, file_path: str, doc_id: str, filename: str, ext: str
    ) -> List[str]:
        """
        Load the file into SQLite and return a list of created table names.

        Supports: .csv, .xlsx, .xls, .parquet, .json (array of dicts)
        """
        engine = create_engine(_TABULAR_DB_URL, connect_args={"check_same_thread": False})
        base_table = _sanitize_table_name(doc_id)
        created_tables: List[str] = []

        if ext == ".csv":
            df = self._read_csv(file_path)
            df = self._clean_dataframe(df)
            df.to_sql(base_table, engine, if_exists="replace", index=False)
            created_tables.append(base_table)

        elif ext in (".xlsx", ".xls"):
            xf = pd.ExcelFile(file_path)
            for sheet_name in xf.sheet_names:
                df = xf.parse(sheet_name, nrows=_MAX_ROWS)
                if df.empty:
                    continue
                df = self._clean_dataframe(df)
                safe_sheet = _sanitize_sheet_name(sheet_name)
                # If only one sheet, use base name; otherwise suffix with sheet
                if len(xf.sheet_names) == 1:
                    table_name = base_table
                else:
                    table_name = f"{base_table}_{safe_sheet}"
                df.to_sql(table_name, engine, if_exists="replace", index=False)
                created_tables.append(table_name)

        elif ext == ".parquet":
            import pyarrow.parquet as pq
            table = pq.read_table(file_path)
            df = table.to_pandas()
            if len(df) > _MAX_ROWS:
                df = df.head(_MAX_ROWS)
                logger.warning("TabularPipeline: truncated %s to %d rows", filename, _MAX_ROWS)
            df = self._clean_dataframe(df)
            df.to_sql(base_table, engine, if_exists="replace", index=False)
            created_tables.append(base_table)

        elif ext == ".json":
            import json
            with open(file_path, "r", errors="ignore") as f:
                data = json.load(f)
            if isinstance(data, list):
                df = pd.DataFrame(data[:_MAX_ROWS])
            elif isinstance(data, dict):
                # Try to find an array field inside the dict
                for v in data.values():
                    if isinstance(v, list) and len(v) > 0:
                        df = pd.DataFrame(v[:_MAX_ROWS])
                        break
                else:
                    df = pd.DataFrame([data])
            df = self._clean_dataframe(df)
            df.to_sql(base_table, engine, if_exists="replace", index=False)
            created_tables.append(base_table)

        else:
            raise ValueError(f"Unsupported file type for tabular pipeline: {ext}")

        engine.dispose()
        return created_tables

    @staticmethod
    def _read_csv(file_path: str) -> pd.DataFrame:
        """Read a CSV with automatic encoding and delimiter detection."""
        # Try common encodings
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                df = pd.read_csv(
                    file_path,
                    encoding=encoding,
                    nrows=_MAX_ROWS,
                    low_memory=False,
                    sep=None,        # auto-detect delimiter
                    engine="python",
                )
                return df
            except Exception:
                continue
        raise ValueError("Could not read CSV with any common encoding")

    @staticmethod
    def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean column names and basic data types for SQLite compatibility.
        """
        # Sanitize column names
        df.columns = [
            re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).strip("_") or f"col_{i}"
            for i, c in enumerate(df.columns)
        ]
        # Deduplicate column names
        seen: dict = {}
        new_cols = []
        for col in df.columns:
            if col in seen:
                seen[col] += 1
                new_cols.append(f"{col}_{seen[col]}")
            else:
                seen[col] = 0
                new_cols.append(col)
        df.columns = new_cols

        # Convert object columns that look numeric
        for col in df.select_dtypes(include=["object"]).columns:
            try:
                df[col] = pd.to_numeric(df[col].str.replace(",", ""), errors="ignore")
            except Exception:
                pass

        return df

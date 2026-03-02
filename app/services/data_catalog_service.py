"""
Data Catalog Service for Intelligent Auto-RAG.

Maintains a lightweight, queryable index of what each uploaded document
can answer. Helps the query router decide:
  - Which documents are relevant to a user question
  - What pipeline each document uses (SQL vs RAG)
  - What topics/entities are covered in each document

The catalog is stored in SQLite (in the existing users.db) as a
`data_catalog` table alongside the `documents` table.

Usage:
    catalog = DataCatalogService()
    catalog.register(doc_id, filename, doc_type, doc_subtype, pipeline,
                     topics=["revenue", "Q3", "2024"], stats={"rows": 4200})
    matches = catalog.find_relevant(query="What was Q3 revenue?", username="alice")
"""

import os
import json
import re
import sqlite3
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join("data", "users.db")
_STOP_WORDS = {
    "what", "how", "who", "when", "where", "why", "which", "is", "are",
    "was", "were", "the", "a", "an", "and", "or", "but", "in", "on",
    "at", "to", "for", "of", "with", "by", "from", "about", "does",
    "do", "did", "can", "could", "should", "would", "will", "has",
    "have", "had", "be", "been", "being", "this", "that", "these", "those",
}


@dataclass
class CatalogEntry:
    """One document in the catalog."""
    doc_id: str
    filename: str
    username: str
    doc_type: str
    doc_subtype: str
    pipeline: str            # "sql" | "rag"
    topics: List[str]        # keyword topics extracted from doc
    stats: Dict[str, Any]    # rows/cols/words/pages/etc.
    conn_id: Optional[str]   # for SQL pipeline: DB conn_id
    doc_date: Optional[str]  # detected document date
    upload_time: str


class DataCatalogService:
    """
    Manages the data catalog — an index of all uploaded documents and their
    topic coverage, enabling smart routing at query time.
    """

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self._init_table()

    # ── Public API ────────────────────────────────────────────────────────────

    def register(
        self,
        doc_id: str,
        filename: str,
        username: str,
        doc_type: str,
        doc_subtype: str,
        pipeline: str,
        topics: Optional[List[str]] = None,
        stats: Optional[Dict[str, Any]] = None,
        conn_id: Optional[str] = None,
        doc_date: Optional[str] = None,
        text_sample: Optional[str] = None,
    ) -> None:
        """
        Register a newly uploaded document in the catalog.

        If topics is not provided but text_sample is, auto-extracts keywords.
        """
        if topics is None and text_sample:
            topics = self._extract_topics(text_sample)
        topics = topics or []

        import datetime
        upload_time = datetime.datetime.utcnow().isoformat()

        with sqlite3.connect(_DB_PATH) as con:
            con.execute(
                """
                INSERT OR REPLACE INTO data_catalog
                    (doc_id, filename, username, doc_type, doc_subtype, pipeline,
                     topics, stats, conn_id, doc_date, upload_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id, filename, username, doc_type, doc_subtype, pipeline,
                    json.dumps(topics), json.dumps(stats or {}),
                    conn_id, doc_date, upload_time,
                ),
            )
        logger.info(
            "DataCatalog: registered doc_id=%s filename=%s type=%s/%s pipeline=%s topics=%s",
            doc_id, filename, doc_type, doc_subtype, pipeline, topics[:5],
        )

    def find_relevant(
        self,
        query: str,
        username: Optional[str] = None,
        pipeline_filter: Optional[str] = None,
        top_n: int = 10,
    ) -> List[CatalogEntry]:
        """
        Find catalog entries whose topics overlap with the query keywords.

        Args:
            query: User question.
            username: If provided, filter to this user's documents.
            pipeline_filter: "sql" | "rag" | None (all)
            top_n: Max entries to return.

        Returns:
            List of CatalogEntry sorted by topic overlap score (desc).
        """
        query_kws = self._extract_keywords(query)
        all_entries = self._fetch_entries(username=username, pipeline_filter=pipeline_filter)

        if not query_kws:
            return all_entries[:top_n]

        # Score by keyword overlap
        scored = []
        for entry in all_entries:
            entry_kws = set(t.lower() for t in entry.topics)
            overlap = len(query_kws & entry_kws)
            if overlap > 0:
                scored.append((overlap, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_n]]

    def get_entry(self, doc_id: str) -> Optional[CatalogEntry]:
        """Fetch a single catalog entry by doc_id."""
        try:
            with sqlite3.connect(_DB_PATH) as con:
                row = con.execute(
                    "SELECT * FROM data_catalog WHERE doc_id = ?", (doc_id,)
                ).fetchone()
            if row:
                return self._row_to_entry(row)
        except Exception as e:
            logger.debug("DataCatalog.get_entry failed: %s", e)
        return None

    def remove(self, doc_id: str) -> None:
        """Remove a document from the catalog."""
        try:
            with sqlite3.connect(_DB_PATH) as con:
                con.execute("DELETE FROM data_catalog WHERE doc_id = ?", (doc_id,))
            logger.info("DataCatalog: removed doc_id=%s", doc_id)
        except Exception as e:
            logger.warning("DataCatalog.remove failed for %s: %s", doc_id, e)

    def list_user_catalog(self, username: str) -> List[CatalogEntry]:
        """List all catalog entries for a user."""
        return self._fetch_entries(username=username)

    def get_catalog_summary(self, username: str) -> str:
        """
        Build a human-readable summary of what the user has uploaded.
        Used to help the LLM understand available data sources.
        """
        entries = self.list_user_catalog(username)
        if not entries:
            return "No documents in catalog."

        lines = ["Available data sources:"]
        for entry in entries:
            topics_str = ", ".join(entry.topics[:5]) if entry.topics else "general"
            if entry.pipeline == "sql":
                stats = entry.stats
                shape = f"{stats.get('rows','?')} rows × {stats.get('cols','?')} cols"
                lines.append(
                    f"  • [{entry.pipeline.upper()}] {entry.filename} — {shape} | Topics: {topics_str}"
                )
            else:
                stats = entry.stats
                size = stats.get("word_count") or stats.get("pages") or "?"
                lines.append(
                    f"  • [{entry.pipeline.upper()}] {entry.filename} — {size} words | Topics: {topics_str}"
                )

        return "\n".join(lines)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _init_table(self) -> None:
        """Create data_catalog table if it doesn't exist."""
        try:
            with sqlite3.connect(_DB_PATH) as con:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS data_catalog (
                        doc_id       TEXT PRIMARY KEY,
                        filename     TEXT NOT NULL,
                        username     TEXT NOT NULL,
                        doc_type     TEXT,
                        doc_subtype  TEXT,
                        pipeline     TEXT,
                        topics       TEXT,   -- JSON array
                        stats        TEXT,   -- JSON object
                        conn_id      TEXT,
                        doc_date     TEXT,
                        upload_time  TEXT
                    )
                    """
                )
        except Exception as e:
            logger.warning("DataCatalog: could not init table: %s", e)

    def _fetch_entries(
        self,
        username: Optional[str] = None,
        pipeline_filter: Optional[str] = None,
    ) -> List[CatalogEntry]:
        """Fetch entries with optional filters."""
        try:
            with sqlite3.connect(_DB_PATH) as con:
                con.row_factory = sqlite3.Row
                sql = "SELECT * FROM data_catalog"
                conditions = []
                params = []
                if username:
                    conditions.append("username = ?")
                    params.append(username)
                if pipeline_filter:
                    conditions.append("pipeline = ?")
                    params.append(pipeline_filter)
                if conditions:
                    sql += " WHERE " + " AND ".join(conditions)
                sql += " ORDER BY upload_time DESC"
                rows = con.execute(sql, params).fetchall()
                return [self._row_to_entry(dict(row)) for row in rows]
        except Exception as e:
            logger.debug("DataCatalog._fetch_entries failed: %s", e)
            return []

    @staticmethod
    def _row_to_entry(row) -> CatalogEntry:
        """Convert a DB row (dict or tuple) to CatalogEntry."""
        if isinstance(row, dict):
            r = row
        else:
            # Fallback: assume column order from CREATE TABLE
            cols = ["doc_id","filename","username","doc_type","doc_subtype",
                    "pipeline","topics","stats","conn_id","doc_date","upload_time"]
            r = dict(zip(cols, row))
        return CatalogEntry(
            doc_id=r["doc_id"],
            filename=r["filename"],
            username=r["username"],
            doc_type=r.get("doc_type", "narrative"),
            doc_subtype=r.get("doc_subtype", "general"),
            pipeline=r.get("pipeline", "rag"),
            topics=json.loads(r.get("topics") or "[]"),
            stats=json.loads(r.get("stats") or "{}"),
            conn_id=r.get("conn_id"),
            doc_date=r.get("doc_date"),
            upload_time=r.get("upload_time", ""),
        )

    @staticmethod
    def _extract_topics(text: str, max_topics: int = 30) -> List[str]:
        """Extract top keywords from text as topics."""
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        freq: Dict[str, int] = {}
        for w in words:
            if w not in _STOP_WORDS:
                freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:max_topics]]

    @staticmethod
    def _extract_keywords(query: str) -> set:
        """Extract meaningful keywords from a query."""
        words = re.findall(r"\b[a-zA-Z]{3,}\b", query.lower())
        return {w for w in words if w not in _STOP_WORDS}

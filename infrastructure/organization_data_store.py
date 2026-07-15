"""Tenant- and department-scoped structured and unstructured data foundation.

External connectors write through this store after authentication and source
validation. The local implementation is intentionally usable without external
credentials: it supports source registration, structured-record ingestion,
document chunking, permission-filtered retrieval, and source citations.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infrastructure.data_governance import scan_and_redact
from infrastructure.people_ops_store import DEPARTMENTS

SOURCE_TYPES = {"structured", "unstructured"}
CLASSIFICATIONS = {"internal", "confidential", "restricted"}


class OrganizationDataError(ValueError):
    """Safe data-layer error that can be returned through the API."""


class OrganizationDataStore:
    def __init__(self, db_path: str | None = None):
        raw_path = db_path or os.getenv("RAPID_ORGANIZATION_DATA_DB_PATH", "data/db/organization_data.db")
        self.db_path = Path(raw_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS organization_data_sources (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    connector_type TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(tenant_id, department, name)
                );
                CREATE INDEX IF NOT EXISTS idx_org_data_sources_scope
                    ON organization_data_sources(tenant_id, department, created_at DESC);
                CREATE TABLE IF NOT EXISTS organization_structured_records (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_org_records_scope
                    ON organization_structured_records(tenant_id, department, source_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS organization_documents (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    name TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    pii_summary_json TEXT NOT NULL DEFAULT '{}',
                    extraction_method TEXT NOT NULL DEFAULT 'text',
                    created_at TEXT NOT NULL,
                    UNIQUE(source_id, content_hash)
                );
                CREATE TABLE IF NOT EXISTS organization_document_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding_status TEXT NOT NULL DEFAULT 'pending',
                    embedding_model TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(document_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_org_chunks_scope
                    ON organization_document_chunks(tenant_id, department, source_id, sequence);
                """
            )
            document_columns = {row[1] for row in conn.execute("PRAGMA table_info(organization_documents)").fetchall()}
            if "pii_summary_json" not in document_columns:
                conn.execute("ALTER TABLE organization_documents ADD COLUMN pii_summary_json TEXT NOT NULL DEFAULT '{}'")
            if "extraction_method" not in document_columns:
                conn.execute("ALTER TABLE organization_documents ADD COLUMN extraction_method TEXT NOT NULL DEFAULT 'text'")
            chunk_columns = {row[1] for row in conn.execute("PRAGMA table_info(organization_document_chunks)").fetchall()}
            if "embedding_status" not in chunk_columns:
                conn.execute("ALTER TABLE organization_document_chunks ADD COLUMN embedding_status TEXT NOT NULL DEFAULT 'pending'")
            if "embedding_model" not in chunk_columns:
                conn.execute("ALTER TABLE organization_document_chunks ADD COLUMN embedding_model TEXT NOT NULL DEFAULT ''")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _tokens(value: str) -> list[str]:
        return [token for token in re.findall(r"[a-zA-Z0-9_/-]+", value.lower()) if len(token) > 1]

    @staticmethod
    def _safe_config(config: dict[str, Any] | None) -> dict[str, Any]:
        """Configuration contains references only; raw credentials must stay in a secret manager."""
        clean = dict(config or {})
        forbidden = {"password", "token", "secret", "api_key", "access_token", "refresh_token"}
        if forbidden & {str(key).lower() for key in clean}:
            raise OrganizationDataError("Store connector credentials in a secret manager, not source configuration")
        return clean

    def register_source(self, tenant_id: str, department: str, name: str, source_type: str,
                        connector_type: str, classification: str, created_by: str,
                        config: dict[str, Any] | None = None) -> dict:
        if department not in DEPARTMENTS:
            raise OrganizationDataError("Unknown department")
        if source_type not in SOURCE_TYPES:
            raise OrganizationDataError("source_type must be structured or unstructured")
        if classification not in CLASSIFICATIONS:
            raise OrganizationDataError("Unknown data classification")
        if not name.strip() or len(name) > 160:
            raise OrganizationDataError("A source name between 1 and 160 characters is required")
        clean_config = self._safe_config(config)
        source_id = f"src_{uuid.uuid4().hex[:12]}"
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO organization_data_sources
                   (id, tenant_id, department, name, source_type, connector_type, classification, status, config_json, created_by, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id, tenant_id, department, name.strip(), source_type, connector_type.strip() or "manual",
                 classification, "ready", json.dumps(clean_config), created_by, self._now()),
            )
            conn.commit()
        except sqlite3.IntegrityError as error:
            raise OrganizationDataError("A source with this name already exists in the department") from error
        finally:
            conn.close()
        return self.get_source(tenant_id, source_id)

    def _source_row(self, conn: sqlite3.Connection, tenant_id: str, source_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM organization_data_sources WHERE id=? AND tenant_id=?", (source_id, tenant_id)).fetchone()
        if not row:
            raise OrganizationDataError("Data source not found")
        return row

    def _serialize_source(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        source = dict(row)
        source["config"] = json.loads(source.pop("config_json") or "{}")
        source["record_count"] = conn.execute("SELECT COUNT(*) FROM organization_structured_records WHERE source_id=? AND tenant_id=?", (row["id"], row["tenant_id"])).fetchone()[0]
        source["document_count"] = conn.execute("SELECT COUNT(*) FROM organization_documents WHERE source_id=? AND tenant_id=?", (row["id"], row["tenant_id"])).fetchone()[0]
        return source

    def get_source(self, tenant_id: str, source_id: str) -> dict:
        conn = self._connect()
        try:
            return self._serialize_source(conn, self._source_row(conn, tenant_id, source_id))
        finally:
            conn.close()

    def list_sources(self, tenant_id: str, department: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            query = "SELECT * FROM organization_data_sources WHERE tenant_id=?"
            args: list[Any] = [tenant_id]
            if department:
                query += " AND department=?"
                args.append(department)
            query += " ORDER BY created_at DESC"
            return [self._serialize_source(conn, row) for row in conn.execute(query, args).fetchall()]
        finally:
            conn.close()

    def add_structured_records(self, tenant_id: str, source_id: str, records: list[dict[str, Any]]) -> dict:
        if not records or len(records) > 500:
            raise OrganizationDataError("Provide between 1 and 500 structured records")
        conn = self._connect()
        try:
            source = self._source_row(conn, tenant_id, source_id)
            if source["source_type"] != "structured":
                raise OrganizationDataError("Only structured sources accept records")
            now = self._now()
            for record in records:
                encoded = json.dumps(record, default=str)
                if len(encoded) > 100_000:
                    raise OrganizationDataError("Each structured record must be smaller than 100KB")
                conn.execute(
                    "INSERT INTO organization_structured_records (id, source_id, tenant_id, department, record_json, created_at) VALUES (?,?,?,?,?,?)",
                    (f"rec_{uuid.uuid4().hex[:12]}", source_id, tenant_id, source["department"], encoded, now),
                )
            conn.commit()
        finally:
            conn.close()
        return self.get_source(tenant_id, source_id)

    def add_document(self, tenant_id: str, source_id: str, name: str, content: str, extraction_method: str = "text") -> dict:
        if not name.strip() or not content.strip():
            raise OrganizationDataError("Document name and content are required")
        if len(content.encode("utf-8")) > 2_000_000:
            raise OrganizationDataError("Document content must be smaller than 2MB")
        conn = self._connect()
        try:
            source = self._source_row(conn, tenant_id, source_id)
            if source["source_type"] != "unstructured":
                raise OrganizationDataError("Only unstructured sources accept documents")
            governance = scan_and_redact(content, redact=os.getenv("RAPID_PII_MODE", "redact").lower() != "detect")
            governed_content = governance.text
            classification = source["classification"]
            if governance.contains_pii and classification == "internal":
                classification = "confidential"
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            document_id = f"doc_{uuid.uuid4().hex[:12]}"
            now = self._now()
            try:
                conn.execute(
                    """INSERT INTO organization_documents
                       (id, source_id, tenant_id, department, name, content_hash, classification, pii_summary_json, extraction_method, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (document_id, source_id, tenant_id, source["department"], name.strip(), digest, classification,
                     json.dumps(governance.findings), extraction_method[:80], now),
                )
            except sqlite3.IntegrityError as error:
                raise OrganizationDataError("This document has already been ingested into the source") from error
            chunks = self._chunk(governed_content)
            for sequence, chunk in enumerate(chunks, start=1):
                conn.execute(
                    """INSERT INTO organization_document_chunks
                       (id, document_id, source_id, tenant_id, department, sequence, content, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (f"chk_{uuid.uuid4().hex[:12]}", document_id, source_id, tenant_id, source["department"], sequence, chunk, now),
                )
            conn.commit()
        finally:
            conn.close()
        return {
            "document_id": document_id,
            "source_id": source_id,
            "chunks_created": len(chunks),
            "classification": classification,
            "pii_detected": governance.contains_pii,
            "pii_summary": governance.findings,
            "extraction_method": extraction_method,
            "embedding_status": "pending",
        }

    @staticmethod
    def _chunk(content: str, size: int = 1200, overlap: int = 150) -> list[str]:
        text = " ".join(content.split())
        if len(text) <= size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start + size // 2:
                    end = boundary
            chunks.append(text[start:end].strip())
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
        return chunks

    def search(self, tenant_id: str, department: str, query: str, source_id: str | None = None, limit: int = 8) -> dict:
        if department not in DEPARTMENTS:
            raise OrganizationDataError("Unknown department")
        tokens = self._tokens(query)
        if not tokens:
            raise OrganizationDataError("Search query needs at least one meaningful term")
        conn = self._connect()
        try:
            params: list[Any] = [tenant_id, department]
            where = "tenant_id=? AND department=?"
            if source_id:
                source = self._source_row(conn, tenant_id, source_id)
                if source["department"] != department:
                    raise OrganizationDataError("Data source is outside this department")
                where += " AND source_id=?"
                params.append(source_id)
            rows = conn.execute(f"SELECT * FROM organization_document_chunks WHERE {where}", params).fetchall()
            ranked = []
            for row in rows:
                text = row["content"].lower()
                score = sum(text.count(token) for token in tokens)
                if score:
                    ranked.append((score, row))
            ranked.sort(key=lambda item: (-item[0], item[1]["sequence"]))
            citations = []
            for score, row in ranked[:limit]:
                document = conn.execute("SELECT name, classification FROM organization_documents WHERE id=? AND tenant_id=?", (row["document_id"], tenant_id)).fetchone()
                source = self._source_row(conn, tenant_id, row["source_id"])
                citations.append({
                    "chunk_id": row["id"], "document_id": row["document_id"], "document_name": document["name"],
                    "source_id": row["source_id"], "source_name": source["name"], "classification": document["classification"],
                    "score": score, "excerpt": row["content"][:500],
                })
            return {"query": query, "department": department, "citations": citations, "count": len(citations), "retrieval": "lexical_sandbox"}
        finally:
            conn.close()

    def list_records(self, tenant_id: str, source_id: str, limit: int = 50) -> list[dict]:
        conn = self._connect()
        try:
            self._source_row(conn, tenant_id, source_id)
            rows = conn.execute("SELECT id, record_json, created_at FROM organization_structured_records WHERE tenant_id=? AND source_id=? ORDER BY created_at DESC LIMIT ?", (tenant_id, source_id, limit)).fetchall()
            return [{"id": row["id"], "record": json.loads(row["record_json"]), "created_at": row["created_at"]} for row in rows]
        finally:
            conn.close()

    def get_document(self, tenant_id: str, document_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM organization_documents WHERE id=? AND tenant_id=?", (document_id, tenant_id)).fetchone()
            if not row:
                raise OrganizationDataError("Document not found")
            data = dict(row)
            data["pii_summary"] = json.loads(data.pop("pii_summary_json") or "{}")
            data["chunks"] = self.get_document_chunks(tenant_id, document_id)
            return data
        finally:
            conn.close()

    def get_document_chunks(self, tenant_id: str, document_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM organization_document_chunks WHERE document_id=? AND tenant_id=? ORDER BY sequence",
                (document_id, tenant_id),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_chunk(self, tenant_id: str, chunk_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT c.*, d.name AS document_name, d.classification, s.name AS source_name
                   FROM organization_document_chunks c
                   JOIN organization_documents d ON d.id=c.document_id AND d.tenant_id=c.tenant_id
                   JOIN organization_data_sources s ON s.id=c.source_id AND s.tenant_id=c.tenant_id
                   WHERE c.id=? AND c.tenant_id=?""",
                (chunk_id, tenant_id),
            ).fetchone()
            if not row:
                raise OrganizationDataError("Document chunk not found")
            return dict(row)
        finally:
            conn.close()

    def mark_document_indexed(self, tenant_id: str, document_id: str, model: str, status: str = "indexed") -> None:
        conn = self._connect()
        try:
            result = conn.execute(
                "UPDATE organization_document_chunks SET embedding_status=?, embedding_model=? WHERE document_id=? AND tenant_id=?",
                (status, model[:160], document_id, tenant_id),
            )
            if not result.rowcount:
                raise OrganizationDataError("Document not found")
            conn.commit()
        finally:
            conn.close()

    def has_indexed_chunks(self, tenant_id: str, department: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM organization_document_chunks WHERE tenant_id=? AND department=? AND embedding_status='indexed' LIMIT 1",
                (tenant_id, department),
            ).fetchone()
            return bool(row)
        finally:
            conn.close()


def get_organization_data_store() -> OrganizationDataStore:
    return OrganizationDataStore()

"""
infrastructure/document_library.py — Governed Document Library

Central document registry for all tenant documents:
  • Produced by agent skills (DOCX, PPTX, XLSX, HTML)
  • Uploaded by users via /library/upload
  • Pulled from project_documents tables in project DBs

Access control
──────────────
  • Tenant isolation — only tenant's documents visible
  • Project membership — for project-scoped docs, user must be a member
  • Role-based — board_member/ceo see all; employees see their dept only

Schema (in platform DB)
───────────────────────
  library_documents (
    doc_id PK, tenant_id, project_id, title, file_path, file_format,
    report_type, produced_by, dept_id, access_level, file_size_kb,
    page_count, status, created_at, updated_at
  )
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Optional

import config

logger = logging.getLogger("rapid.document_library")


# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS library_documents (
    doc_id        TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    project_id    TEXT,
    title         TEXT NOT NULL,
    file_path     TEXT,
    file_format   TEXT NOT NULL DEFAULT 'docx',
    report_type   TEXT,
    produced_by   TEXT,
    dept_id       TEXT,
    access_level  TEXT NOT NULL DEFAULT 'project',
    file_size_kb  REAL DEFAULT 0,
    page_count    INTEGER DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_libdoc_tenant   ON library_documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_libdoc_project  ON library_documents(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_libdoc_dept     ON library_documents(tenant_id, dept_id);
CREATE INDEX IF NOT EXISTS idx_libdoc_format   ON library_documents(tenant_id, file_format);
CREATE INDEX IF NOT EXISTS idx_libdoc_created  ON library_documents(tenant_id, created_at DESC);
"""

# access_level values
ACCESS_PUBLIC  = "public"   # all tenant members
ACCESS_PROJECT = "project"  # project members only
ACCESS_DEPT    = "dept"     # same-dept members only
ACCESS_ADMIN   = "admin"    # admin/c-suite only


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class LibraryDocument:
    doc_id:       str
    tenant_id:    str
    title:        str
    file_format:  str        = "docx"
    project_id:   Optional[str] = None
    file_path:    Optional[str] = None
    report_type:  Optional[str] = None
    produced_by:  Optional[str] = None
    dept_id:      Optional[str] = None
    access_level: str        = ACCESS_PROJECT
    file_size_kb: float      = 0.0
    page_count:   int        = 0
    status:       str        = "active"
    created_at:   str        = ""
    updated_at:   str        = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # Add download URL if file exists
        if self.file_path and os.path.exists(self.file_path):
            import os as _os
            fname = _os.path.basename(self.file_path)
            pid   = self.project_id or "global"
            d["download_url"] = f"/projects/{pid}/skills/download/{fname}"
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "LibraryDocument":
        d = dict(row)
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})  # type: ignore[attr-defined]


# ── DocumentLibrary ───────────────────────────────────────────────────────────

class DocumentLibrary:
    def __init__(self, db_path: str = None):
        self._db_path = db_path or config.DB_PATH
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _connect_ro(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            f"file:{self._db_path}?mode=ro", uri=True, timeout=10
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    # ── Write ──────────────────────────────────────────────────────────────────

    def register(
        self,
        tenant_id:    str,
        title:        str,
        file_format:  str  = "docx",
        project_id:   str | None = None,
        file_path:    str | None = None,
        report_type:  str | None = None,
        produced_by:  str | None = None,
        dept_id:      str | None = None,
        access_level: str  = ACCESS_PROJECT,
        page_count:   int  = 0,
        doc_id:       str | None = None,
    ) -> LibraryDocument:
        """Register a new document in the library (does not move the file)."""
        now  = self._now()
        did  = doc_id or str(uuid.uuid4())
        size = 0.0
        if file_path and os.path.exists(file_path):
            size = os.path.getsize(file_path) / 1024

        doc = LibraryDocument(
            doc_id=did, tenant_id=tenant_id, title=title,
            file_format=file_format, project_id=project_id,
            file_path=file_path, report_type=report_type,
            produced_by=produced_by, dept_id=dept_id,
            access_level=access_level, file_size_kb=size,
            page_count=page_count, status="active",
            created_at=now, updated_at=now,
        )
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO library_documents
                  (doc_id, tenant_id, project_id, title, file_path, file_format,
                   report_type, produced_by, dept_id, access_level,
                   file_size_kb, page_count, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (did, tenant_id, project_id, title, file_path, file_format,
                 report_type, produced_by, dept_id, access_level,
                 size, page_count, "active", now, now),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info(f"[Library] Registered doc={did} '{title}' format={file_format}")
        return doc

    def delete(self, doc_id: str) -> bool:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE library_documents SET status='deleted', updated_at=? WHERE doc_id=?",
                (self._now(), doc_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    # ── Read ───────────────────────────────────────────────────────────────────

    def get(self, doc_id: str) -> Optional[LibraryDocument]:
        conn = self._connect_ro()
        try:
            row = conn.execute(
                "SELECT * FROM library_documents WHERE doc_id=? AND status='active'",
                (doc_id,),
            ).fetchone()
            return LibraryDocument.from_row(row) if row else None
        finally:
            conn.close()

    def list(
        self,
        tenant_id:   str,
        project_id:  str | None = None,
        dept_id:     str | None = None,
        file_format: str | None = None,
        report_type: str | None = None,
        produced_by: str | None = None,
        limit:       int        = 50,
        offset:      int        = 0,
    ) -> list[LibraryDocument]:
        conds = ["tenant_id=?", "status='active'"]
        params: list[Any] = [tenant_id]
        if project_id:
            conds.append("project_id=?"); params.append(project_id)
        if dept_id:
            conds.append("dept_id=?"); params.append(dept_id)
        if file_format:
            conds.append("file_format=?"); params.append(file_format)
        if report_type:
            conds.append("report_type=?"); params.append(report_type)
        if produced_by:
            conds.append("produced_by=?"); params.append(produced_by)
        params.extend([limit, offset])

        sql = (
            f"SELECT * FROM library_documents WHERE {' AND '.join(conds)} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        conn = self._connect_ro()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [LibraryDocument.from_row(r) for r in rows]
        finally:
            conn.close()

    def search(
        self,
        tenant_id: str,
        query:     str,
        limit:     int = 20,
    ) -> list[LibraryDocument]:
        """Search doc titles and report types."""
        q = f"%{query}%"
        conn = self._connect_ro()
        try:
            rows = conn.execute(
                """
                SELECT * FROM library_documents
                WHERE tenant_id=? AND status='active'
                  AND (title LIKE ? OR report_type LIKE ? OR dept_id LIKE ?
                       OR produced_by LIKE ? OR file_format LIKE ?)
                ORDER BY created_at DESC LIMIT ?
                """,
                (tenant_id, q, q, q, q, q, limit),
            ).fetchall()
            return [LibraryDocument.from_row(r) for r in rows]
        finally:
            conn.close()

    def stats(self, tenant_id: str) -> dict:
        """Summary statistics for the tenant's library."""
        conn = self._connect_ro()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM library_documents WHERE tenant_id=? AND status='active'",
                (tenant_id,),
            ).fetchone()[0]

            by_format = {}
            rows = conn.execute(
                "SELECT file_format, COUNT(*) c FROM library_documents "
                "WHERE tenant_id=? AND status='active' GROUP BY file_format",
                (tenant_id,),
            ).fetchall()
            for r in rows:
                by_format[r[0]] = r[1]

            size_total = conn.execute(
                "SELECT COALESCE(SUM(file_size_kb),0) FROM library_documents "
                "WHERE tenant_id=? AND status='active'",
                (tenant_id,),
            ).fetchone()[0]

            return {
                "total_documents": total,
                "by_format":       by_format,
                "total_size_kb":   round(size_total, 1),
            }
        finally:
            conn.close()

    def sync_from_project_db(
        self,
        db_path:    str,
        project_id: str,
        tenant_id:  str,
    ) -> int:
        """
        Pull documents from a project DB's project_documents table into the library.
        Returns number of documents synced.
        """
        if not db_path or not os.path.exists(db_path):
            return 0
        synced = 0
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM project_documents ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            conn.close()
            for row in rows:
                r = dict(row)
                doc_id = r.get("doc_id") or str(uuid.uuid4())
                # Skip if already in library
                existing = self.get(doc_id)
                if existing:
                    continue
                self.register(
                    tenant_id   = tenant_id,
                    title       = r.get("title") or "Untitled",
                    file_format = r.get("file_format") or "docx",
                    project_id  = project_id,
                    file_path   = r.get("file_path"),
                    report_type = r.get("report_type"),
                    produced_by = r.get("produced_by"),
                    dept_id     = r.get("dept_id"),
                    page_count  = r.get("pages") or 0,
                    doc_id      = doc_id,
                )
                synced += 1
        except Exception as e:
            logger.debug(f"[Library] Sync from {project_id} failed: {e}")
        return synced


# ── Singleton ─────────────────────────────────────────────────────────────────

_library: Optional[DocumentLibrary] = None


def get_document_library() -> DocumentLibrary:
    global _library
    if _library is None:
        _library = DocumentLibrary()
    return _library

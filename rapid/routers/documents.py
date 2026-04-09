"""
routers/documents.py — Document ingestion endpoints.

  POST /ingest   — Ingest by server-side file path (admin/manager)
  POST /upload   — Multipart file upload from browser (admin/manager)
"""

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel

from .deps import get_current_user

router = APIRouter(tags=["documents"])

_ALLOWED_EXTENSIONS = {".txt", ".pdf", ".md", ".csv", ".json", ".docx"}
_UPLOAD_ROOT = Path("data/documents")


def _require_uploader(current_user: dict):
    if current_user.get("role") not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Admin or manager role required for document ingestion")
    return current_user


# ── Ingest by file path ───────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    file_path: str
    dept_tag:  str


class IngestResponse(BaseModel):
    chunks_created: int
    file:           str
    dept_tag:       str


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest, current_user: dict = Depends(get_current_user)):
    """Ingest a document by server-side path. Admin/manager only."""
    _require_uploader(current_user)
    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()
    chunks = await doc.ingest_document(req.file_path, req.dept_tag)
    return IngestResponse(chunks_created=chunks, file=req.file_path, dept_tag=req.dept_tag)


# ── Browser file upload ───────────────────────────────────────────────────────

@router.post("/upload", response_model=IngestResponse)
async def upload_document(
    file:         UploadFile = File(...),
    dept_tag:     str        = Form(...),
    current_user: dict       = Depends(get_current_user),
):
    """Accept a multipart file upload, save it, and ingest into RAG. Admin/manager only."""
    _require_uploader(current_user)

    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}"
        )

    upload_dir = _UPLOAD_ROOT / dept_tag / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / (file.filename or "uploaded_file")

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()
    chunks = await doc.ingest_document(str(save_path), dept_tag)
    return IngestResponse(chunks_created=chunks, file=file.filename or str(save_path), dept_tag=dept_tag)

"""
OneDrive integration endpoints — /cloud/onedrive/*
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from infrastructure.cloud_tokens import is_connected, delete_token
from infrastructure import onedrive_connector as od
from .deps import get_current_user

router = APIRouter(prefix="/cloud/onedrive", tags=["cloud-onedrive"])


# ── Connect ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def connect(current_user: dict = Depends(get_current_user)):
    """Return the Microsoft OAuth2 URL. Flutter opens this in the browser."""
    user_id = current_user["sub"]
    try:
        url = od.get_auth_url(user_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"auth_url": url}


@router.get("/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    """
    Microsoft redirects here after user authorizes.
    We exchange the code, save the token, then redirect Flutter back.
    """
    flutter_base = os.getenv("FLUTTER_BASE_URL", "http://localhost:3000")
    if error:
        return RedirectResponse(f"{flutter_base}/cloud?error=onedrive&detail={error}")
    if not code or not state:
        return RedirectResponse(f"{flutter_base}/cloud?error=onedrive&detail=missing_params")
    try:
        await od.exchange_code(code, state)
    except Exception as e:
        return RedirectResponse(f"{flutter_base}/cloud?error=onedrive&detail={str(e)[:80]}")
    return RedirectResponse(f"{flutter_base}/cloud?connected=onedrive")


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def status(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    connected = is_connected("onedrive", user_id)
    email = await od.get_user_email(user_id) if connected else None
    return {"connected": connected, "email": email}


# ── Files ─────────────────────────────────────────────────────────────────────

@router.get("/files")
async def list_files(folder_path: str = "/",
                     current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    try:
        files = await od.list_files(user_id, folder_path)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"files": files}


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncBody(BaseModel):
    dept_tag:    str
    folder_path: str = "/"


@router.post("/sync")
async def sync(body: SyncBody, current_user: dict = Depends(get_current_user)):
    """
    Sync all supported files from a OneDrive folder into the RAG index.
    Walks the given folder (default: root), downloads every supported file,
    and ingests it. Returns a per-file summary.
    """
    user_id = current_user["sub"]
    allowed = {".txt", ".pdf", ".md", ".csv", ".json", ".docx"}

    try:
        items = await od.list_files(user_id, body.folder_path)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    results = []
    upload_dir = Path("data/documents") / body.dept_tag / "onedrive"
    upload_dir.mkdir(parents=True, exist_ok=True)

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()

    for item in items:
        if item["type"] == "folder":
            results.append({"name": item["name"], "skipped": True, "reason": "folder"})
            continue
        suffix = Path(item["name"]).suffix.lower()
        if suffix not in allowed:
            results.append({"name": item["name"], "skipped": True, "reason": "unsupported type"})
            continue
        try:
            file_bytes, filename = await od.download_file(user_id, item["id"])
            save_path = upload_dir / filename
            save_path.write_bytes(file_bytes)
            chunks = await doc.ingest_document(str(save_path), body.dept_tag)
            results.append({"name": filename, "skipped": False, "chunks": chunks})
        except Exception as e:
            results.append({"name": item["name"], "skipped": True, "reason": str(e)})

    ingested = sum(1 for r in results if not r.get("skipped"))
    return {"status": "ok", "ingested": ingested, "total": len(items), "files": results}


# ── Import ────────────────────────────────────────────────────────────────────

class ImportBody(BaseModel):
    item_id:  str
    dept_tag: str


@router.post("/import")
async def import_file(body: ImportBody, current_user: dict = Depends(get_current_user)):
    """Download a file from OneDrive and ingest it into the RAG index."""
    user_id = current_user["sub"]
    try:
        file_bytes, filename = await od.download_file(user_id, body.item_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Validate file type
    allowed = {".txt", ".pdf", ".md", ".csv", ".json", ".docx"}
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}'")

    # Save to temp file and ingest
    upload_dir = Path("data/documents") / body.dept_tag / "onedrive"
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / filename
    save_path.write_bytes(file_bytes)

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()
    chunks = await doc.ingest_document(str(save_path), body.dept_tag)
    return {"status": "ingested", "file": filename, "chunks": chunks, "dept_tag": body.dept_tag}


# ── Disconnect ────────────────────────────────────────────────────────────────

@router.delete("/disconnect")
async def disconnect(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    delete_token("onedrive", user_id)
    return {"status": "disconnected"}

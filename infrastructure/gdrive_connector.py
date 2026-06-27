"""
Google Drive connector — OAuth2 Authorization Code flow.

Reuses the same GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET as Gmail,
but requests the drive.readonly scope (separate token stored under "gdrive").

Environment variables (shared with Gmail):
  GOOGLE_CLIENT_ID            — Google Cloud OAuth 2.0 Client ID
  GOOGLE_CLIENT_SECRET        — Google Cloud OAuth 2.0 Client Secret
  GOOGLE_DRIVE_REDIRECT_URI   — e.g. http://localhost:8000/cloud/gdrive/callback

Supported file types for ingestion:
  Google Docs    → exported as plain text
  Google Sheets  → exported as CSV
  PDF, DOCX, TXT, MD, CSV, JSON — downloaded directly
"""

from __future__ import annotations

import logging
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from .cloud_tokens import get_token, save_token, delete_token

logger = logging.getLogger("rapid.gdrive")

AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL   = "https://www.googleapis.com/drive/v3"

# Drive scope — read-only access to files
SCOPES = (
    "https://www.googleapis.com/auth/drive.readonly "
    "https://www.googleapis.com/auth/userinfo.email"
)

# MIME types we can ingest → (export_mime or None, local extension)
_INGESTIBLE: dict[str, tuple[Optional[str], str]] = {
    "application/vnd.google-apps.document":
        ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet":
        ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation":
        ("text/plain", ".txt"),
    "application/pdf":
        (None, ".pdf"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        (None, ".docx"),
    "text/plain":          (None, ".txt"),
    "text/markdown":       (None, ".md"),
    "text/csv":            (None, ".csv"),
    "application/json":    (None, ".json"),
}

_MAX_FILE_SIZE = 10 * 1024 * 1024   # 10 MB
_pending: dict[str, str] = {}       # state → user_id


# ── Env helpers ───────────────────────────────────────────────────────────────

def _client_id() -> str:
    v = os.getenv("GOOGLE_CLIENT_ID", "")
    if not v:
        raise RuntimeError("GOOGLE_CLIENT_ID is not set. See .env")
    return v

def _client_secret() -> str:
    v = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not v:
        raise RuntimeError("GOOGLE_CLIENT_SECRET is not set. See .env")
    return v

def _redirect_uri() -> str:
    return os.getenv("GOOGLE_DRIVE_REDIRECT_URI", "http://localhost:8000/cloud/gdrive/callback")


# ── OAuth2 ────────────────────────────────────────────────────────────────────

def get_auth_url(user_id: str) -> str:
    state = secrets.token_urlsafe(16)
    _pending[state] = user_id
    params = {
        "client_id":     _client_id(),
        "redirect_uri":  _redirect_uri(),
        "response_type": "code",
        "scope":         SCOPES,
        "state":         state,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


async def exchange_code(code: str, state: str) -> dict:
    if state not in _pending:
        raise ValueError("Invalid or expired OAuth state")
    user_id = _pending.pop(state)
    data = {
        "client_id":     _client_id(),
        "client_secret": _client_secret(),
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  _redirect_uri(),
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(TOKEN_URL, data=data)
    if res.status_code != 200:
        raise RuntimeError(f"Token exchange failed: {res.text}")
    token = res.json()
    token["expires_at"] = datetime.now(timezone.utc).timestamp() + token.get("expires_in", 3600)
    token["user_id"]    = user_id
    save_token("gdrive", user_id, token)
    return token


async def _get_access_token(user_id: str) -> str:
    stored = get_token("gdrive", user_id)
    if not stored:
        raise RuntimeError("Google Drive not connected for this user")
    now = datetime.now(timezone.utc).timestamp()
    if now >= stored.get("expires_at", 0) - 60:
        data = {
            "client_id":     _client_id(),
            "client_secret": _client_secret(),
            "grant_type":    "refresh_token",
            "refresh_token": stored["refresh_token"],
        }
        async with httpx.AsyncClient() as client:
            res = await client.post(TOKEN_URL, data=data)
        if res.status_code != 200:
            delete_token("gdrive", user_id)
            raise RuntimeError("Token refresh failed — please reconnect Google Drive")
        new_token = res.json()
        new_token["expires_at"]    = now + new_token.get("expires_in", 3600)
        new_token["user_id"]       = user_id
        new_token["refresh_token"] = stored["refresh_token"]
        save_token("gdrive", user_id, new_token)
        return new_token["access_token"]
    return stored["access_token"]


# ── Drive API helpers ──────────────────────────────────────────────────────────

async def get_connected_email(user_id: str) -> str:
    try:
        token = await _get_access_token(user_id)
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://www.googleapis.com/userinfo/v2/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        return res.json().get("email", "") if res.status_code == 200 else ""
    except Exception:
        return ""


async def list_folder(
    user_id: str,
    folder_id: str = "root",
    page_size: int = 50,
) -> list[dict]:
    """
    List files in a Drive folder.
    Returns metadata: {id, name, mimeType, size, modifiedTime, webViewLink}.
    """
    token = await _get_access_token(user_id)
    query = f"'{folder_id}' in parents and trashed = false"
    fields = "files(id,name,mimeType,size,modifiedTime,webViewLink)"

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{API_URL}/files",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "fields": fields, "pageSize": page_size},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Drive list failed: {res.text}")

    files = res.json().get("files", [])
    # Annotate with ingestibility
    for f in files:
        f["ingestible"] = f.get("mimeType") in _INGESTIBLE
    return files


async def search_files(
    user_id: str,
    query_text: str,
    page_size: int = 30,
) -> list[dict]:
    """Full-text search across the user's Drive."""
    token = await _get_access_token(user_id)
    query = f"fullText contains '{query_text}' and trashed = false"
    fields = "files(id,name,mimeType,size,modifiedTime,webViewLink)"

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{API_URL}/files",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "fields": fields, "pageSize": page_size},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Drive search failed: {res.text}")
    return res.json().get("files", [])


async def _download_file(user_id: str, file_id: str, mime_type: str) -> tuple[bytes, str]:
    """
    Download a file's content.
    Google Workspace formats are exported; others downloaded directly.
    Returns (content_bytes, local_extension).
    """
    token = await _get_access_token(user_id)
    export_mime, ext = _INGESTIBLE.get(mime_type, (None, ".bin"))

    async with httpx.AsyncClient(timeout=60) as client:
        if export_mime:
            # Google Workspace file — export to plain format
            res = await client.get(
                f"{API_URL}/files/{file_id}/export",
                headers={"Authorization": f"Bearer {token}"},
                params={"mimeType": export_mime},
            )
        else:
            # Regular binary/text file
            res = await client.get(
                f"{API_URL}/files/{file_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"alt": "media"},
            )

    if res.status_code != 200:
        raise RuntimeError(f"Download failed (status {res.status_code})")
    return res.content, ext


# ── Ingestion ──────────────────────────────────────────────────────────────────

async def ingest_folder(
    user_id: str,
    folder_id: str = "root",
    dept_tag: Optional[str] = None,
    project_id: Optional[str] = None,
    recursive: bool = False,
) -> dict:
    """
    Download all ingestible files from a Drive folder and add them to the KB.

    - dept_tag   → company-wide KB (admin only, enforced in router)
    - project_id → project-scoped KB
    """
    if not dept_tag and not project_id:
        raise ValueError("Supply either dept_tag or project_id")

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()

    files = await list_folder(user_id, folder_id, page_size=100)
    ingestible = [f for f in files if f.get("ingestible")]

    total_chunks = 0
    ingested = 0
    skipped = 0
    errors = []

    with tempfile.TemporaryDirectory() as tmp:
        for file_meta in ingestible:
            try:
                content, ext = await _download_file(
                    user_id, file_meta["id"], file_meta["mimeType"]
                )
                if len(content) > _MAX_FILE_SIZE:
                    skipped += 1
                    logger.debug(f"Skipping {file_meta['name']} — too large")
                    continue

                safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in file_meta["name"])
                tmp_path = Path(tmp) / f"{safe_name}{ext}"
                tmp_path.write_bytes(content)

                tag = dept_tag or f"project_{project_id}"
                chunks = await doc.ingest_document(str(tmp_path), tag)
                total_chunks += chunks
                ingested += 1
                logger.info(f"[gdrive] Ingested '{file_meta['name']}' → {chunks} chunks")

            except Exception as exc:
                logger.warning(f"[gdrive] Skipped '{file_meta['name']}': {exc}")
                errors.append({"file": file_meta["name"], "error": str(exc)})
                skipped += 1

    return {
        "folder_id":      folder_id,
        "files_found":    len(ingestible),
        "files_ingested": ingested,
        "chunks_created": total_chunks,
        "skipped":        skipped,
        "errors":         errors[:10],
    }


async def ingest_file(
    user_id: str,
    file_id: str,
    file_name: str,
    mime_type: str,
    dept_tag: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict:
    """Ingest a single Drive file by ID."""
    if not dept_tag and not project_id:
        raise ValueError("Supply either dept_tag or project_id")
    if mime_type not in _INGESTIBLE:
        raise ValueError(f"File type '{mime_type}' is not supported for ingestion")

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()

    content, ext = await _download_file(user_id, file_id, mime_type)
    with tempfile.TemporaryDirectory() as tmp:
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in file_name)
        tmp_path = Path(tmp) / f"{safe_name}{ext}"
        tmp_path.write_bytes(content)

        tag = dept_tag or f"project_{project_id}"
        chunks = await doc.ingest_document(str(tmp_path), tag)

    return {"file_id": file_id, "file_name": file_name, "chunks_created": chunks}

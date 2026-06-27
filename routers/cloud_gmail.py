"""
Gmail integration endpoints — /cloud/gmail/*
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from infrastructure.cloud_tokens import is_connected, delete_token
from infrastructure import gmail_connector as gm
from .deps import get_current_user

router = APIRouter(prefix="/cloud/gmail", tags=["cloud-gmail"])


# ── Connect ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def connect(current_user: dict = Depends(get_current_user)):
    """Return the Google OAuth2 URL. Flutter opens this in the browser."""
    user_id = current_user["sub"]
    try:
        url = gm.get_auth_url(user_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"auth_url": url}


@router.get("/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    """
    Google redirects here after user authorizes.
    We exchange the code, save the token, then redirect Flutter back.
    """
    flutter_base = os.getenv("FLUTTER_BASE_URL", "http://localhost:3000")
    if error:
        return RedirectResponse(f"{flutter_base}/cloud?error=gmail&detail={error}")
    if not code or not state:
        return RedirectResponse(f"{flutter_base}/cloud?error=gmail&detail=missing_params")
    try:
        await gm.exchange_code(code, state)
    except Exception as e:
        return RedirectResponse(f"{flutter_base}/cloud?error=gmail&detail={str(e)[:80]}")
    return RedirectResponse(f"{flutter_base}/cloud?connected=gmail")


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def status(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    connected = is_connected("gmail", user_id)
    email = await gm.get_user_email(user_id) if connected else None
    return {"connected": connected, "email": email}


# ── Labels ────────────────────────────────────────────────────────────────────

@router.get("/labels")
async def labels(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    try:
        lbls = await gm.list_labels(user_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"labels": lbls}


# ── Messages ─────────────────────────────────────────────────────────────────

@router.get("/messages")
async def messages(label_id: str = "INBOX", max: int = 20,
                   current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    try:
        msgs = await gm.list_messages(user_id, label_id, max)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"messages": msgs}


# ── Emails listing (metadata only) ────────────────────────────────────────────

@router.get("/emails")
async def list_emails(label_id: str = "INBOX", max: int = 50,
                      current_user: dict = Depends(get_current_user)):
    """
    List synced emails — returns subject, from, and date only (no body).
    Fetches directly from Gmail API using stored token.
    """
    user_id = current_user["sub"]
    try:
        msgs = await gm.list_messages(user_id, label_id, max)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Strip snippet, return only metadata
    return {
        "emails": [
            {"id": m["id"], "subject": m["subject"], "from": m["from"], "date": m["date"]}
            for m in msgs
        ]
    }


# ── Sync (bulk ingest last 30 days) ──────────────────────────────────────────

class GmailSyncBody(BaseModel):
    dept_tag: str
    max:      int = 100   # cap at 100 to avoid very long syncs


@router.post("/sync")
async def sync(body: GmailSyncBody, current_user: dict = Depends(get_current_user)):
    """
    Sync recent emails (up to `max`, default 100) into the RAG index.
    Only plain-text body is indexed; attachments are skipped.
    Returns a per-email summary.
    """
    user_id = current_user["sub"]
    max_count = min(body.max, 200)   # hard cap

    try:
        msgs = await gm.list_messages(user_id, "INBOX", max_count)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    save_dir = Path("data/documents") / body.dept_tag / "gmail"
    save_dir.mkdir(parents=True, exist_ok=True)

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()
    results = []

    for m in msgs:
        msg_id = m["id"]
        try:
            full = await gm.get_message_body(user_id, msg_id)
            text = (
                f"Subject: {full['subject']}\n"
                f"From: {full['from']}\n"
                f"Date: {full['date']}\n\n"
                f"{full['body_text']}"
            )
            if not full["body_text"].strip():
                results.append({"id": msg_id, "subject": full["subject"],
                                 "skipped": True, "reason": "empty body"})
                continue
            safe_subject = "".join(
                c if c.isalnum() or c in " -_" else "_"
                for c in full["subject"]
            )[:60]
            save_path = save_dir / f"{msg_id[:8]}_{safe_subject}.txt"
            save_path.write_text(text, encoding="utf-8")
            chunks = await doc.ingest_document(str(save_path), body.dept_tag)
            results.append({"id": msg_id, "subject": full["subject"],
                             "skipped": False, "chunks": chunks})
        except Exception as e:
            results.append({"id": msg_id, "skipped": True, "reason": str(e)})

    ingested = sum(1 for r in results if not r.get("skipped"))
    return {"status": "ok", "ingested": ingested, "total": len(msgs), "emails": results}


# ── Import email body ─────────────────────────────────────────────────────────

class ImportMessageBody(BaseModel):
    message_id: str
    dept_tag:   str


@router.post("/import/message")
async def import_message(body: ImportMessageBody,
                         current_user: dict = Depends(get_current_user)):
    """Ingest the plain-text body of a Gmail message into RAG."""
    user_id = current_user["sub"]
    try:
        msg = await gm.get_message_body(user_id, body.message_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    text = f"Subject: {msg['subject']}\nFrom: {msg['from']}\nDate: {msg['date']}\n\n{msg['body_text']}"
    if not text.strip():
        raise HTTPException(status_code=400, detail="Email body is empty")

    # Write as a temp .txt and ingest
    save_dir = Path("data/documents") / body.dept_tag / "gmail"
    save_dir.mkdir(parents=True, exist_ok=True)
    safe_subject = "".join(c if c.isalnum() or c in " -_" else "_" for c in msg["subject"])[:60]
    save_path = save_dir / f"{body.message_id[:8]}_{safe_subject}.txt"
    save_path.write_text(text, encoding="utf-8")

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()
    chunks = await doc.ingest_document(str(save_path), body.dept_tag)
    return {"status": "ingested", "file": save_path.name, "chunks": chunks, "dept_tag": body.dept_tag}


# ── Import attachment ─────────────────────────────────────────────────────────

class ImportAttachmentBody(BaseModel):
    message_id:    str
    attachment_id: str
    filename:      str
    dept_tag:      str


@router.post("/import/attachment")
async def import_attachment(body: ImportAttachmentBody,
                            current_user: dict = Depends(get_current_user)):
    """Download and ingest a Gmail email attachment into RAG."""
    user_id = current_user["sub"]
    allowed = {".txt", ".pdf", ".md", ".csv", ".json", ".docx"}
    suffix = Path(body.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}'")

    try:
        file_bytes = await gm.download_attachment(user_id, body.message_id, body.attachment_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    save_dir = Path("data/documents") / body.dept_tag / "gmail"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / body.filename
    save_path.write_bytes(file_bytes)

    from infrastructure.doc_master import get_doc_master
    doc = get_doc_master()
    chunks = await doc.ingest_document(str(save_path), body.dept_tag)
    return {"status": "ingested", "file": body.filename, "chunks": chunks, "dept_tag": body.dept_tag}


# ── Disconnect ────────────────────────────────────────────────────────────────

@router.delete("/disconnect")
async def disconnect(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    delete_token("gmail", user_id)
    return {"status": "disconnected"}

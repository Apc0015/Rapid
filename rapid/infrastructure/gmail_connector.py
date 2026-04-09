"""
Gmail connector — OAuth2 Authorization Code with server-side client secret.

Environment variables required:
  GOOGLE_CLIENT_ID       — Google Cloud OAuth 2.0 Client ID
  GOOGLE_CLIENT_SECRET   — Google Cloud OAuth 2.0 Client Secret
  GOOGLE_REDIRECT_URI    — e.g. http://localhost:8000/cloud/gmail/callback
"""

import base64
import os
import secrets
from datetime import datetime, timezone
from email import message_from_bytes
from typing import Optional

import httpx

from .cloud_tokens import get_token, save_token, delete_token

# ── OAuth2 constants ───────────────────────────────────────────────────────────

AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL   = "https://gmail.googleapis.com/gmail/v1"
SCOPES    = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/userinfo.email"

_pending: dict[str, str] = {}  # state → user_id


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
    return os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/cloud/gmail/callback")


# ── Auth ───────────────────────────────────────────────────────────────────────

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
    save_token("gmail", user_id, token)
    return token


async def _get_valid_access_token(user_id: str) -> str:
    stored = get_token("gmail", user_id)
    if not stored:
        raise RuntimeError("Gmail not connected")
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
            delete_token("gmail", user_id)
            raise RuntimeError("Token refresh failed — please reconnect Gmail")
        new_token = res.json()
        new_token["expires_at"]    = now + new_token.get("expires_in", 3600)
        new_token["user_id"]       = user_id
        new_token["refresh_token"] = stored["refresh_token"]  # Google may not resend it
        save_token("gmail", user_id, new_token)
        return new_token["access_token"]
    return stored["access_token"]


# ── Gmail API ─────────────────────────────────────────────────────────────────

async def get_user_email(user_id: str) -> str:
    try:
        token = await _get_valid_access_token(user_id)
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://www.googleapis.com/userinfo/v2/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        return res.json().get("email", "") if res.status_code == 200 else ""
    except Exception:
        return ""


async def list_labels(user_id: str) -> list[dict]:
    token = await _get_valid_access_token(user_id)
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{API_URL}/users/me/labels",
            headers={"Authorization": f"Bearer {token}"},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Labels fetch failed: {res.text}")
    labels = res.json().get("labels", [])
    # Show only user labels + common system ones
    keep_types = {"user", "system"}
    return [
        {"id": l["id"], "name": l["name"], "type": l.get("type", "user")}
        for l in labels
        if l.get("type") in keep_types
    ]


async def list_messages(user_id: str, label_id: str = "INBOX", max_results: int = 20) -> list[dict]:
    token = await _get_valid_access_token(user_id)
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{API_URL}/users/me/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"labelIds": label_id, "maxResults": max_results},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Messages fetch failed: {res.text}")
    msg_ids = [m["id"] for m in res.json().get("messages", [])]

    # Fetch each message's snippet + subject in parallel
    async def _get_snippet(msg_id: str) -> dict:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{API_URL}/users/me/messages/{msg_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "metadata", "metadataHeaders": "Subject,From,Date"},
            )
        if r.status_code != 200:
            return {"id": msg_id, "subject": "(error)", "from": "", "snippet": ""}
        data = r.json()
        headers_map = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        return {
            "id":      msg_id,
            "subject": headers_map.get("Subject", "(no subject)"),
            "from":    headers_map.get("From", ""),
            "date":    headers_map.get("Date", ""),
            "snippet": data.get("snippet", ""),
        }

    import asyncio
    return await asyncio.gather(*[_get_snippet(mid) for mid in msg_ids])


async def get_message_body(user_id: str, message_id: str) -> dict:
    """Returns {subject, from, date, body_text, attachments:[{id, filename, mime_type}]}."""
    token = await _get_valid_access_token(user_id)
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{API_URL}/users/me/messages/{message_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"format": "full"},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Message fetch failed: {res.text}")
    data = res.json()
    payload = data.get("payload", {})
    headers_map = {h["name"]: h["value"] for h in payload.get("headers", [])}

    body_text = ""
    attachments = []

    def _walk(part):
        nonlocal body_text
        mime = part.get("mimeType", "")
        if mime == "text/plain" and "data" in part.get("body", {}):
            raw = base64.urlsafe_b64decode(part["body"]["data"] + "==")
            body_text += raw.decode("utf-8", errors="replace")
        elif part.get("filename") and part.get("body", {}).get("attachmentId"):
            attachments.append({
                "id":        part["body"]["attachmentId"],
                "filename":  part["filename"],
                "mime_type": mime,
                "size":      part["body"].get("size", 0),
            })
        for sub in part.get("parts", []):
            _walk(sub)

    _walk(payload)

    return {
        "subject":     headers_map.get("Subject", "(no subject)"),
        "from":        headers_map.get("From", ""),
        "date":        headers_map.get("Date", ""),
        "body_text":   body_text,
        "attachments": attachments,
    }


async def download_attachment(user_id: str, message_id: str, attachment_id: str) -> bytes:
    token = await _get_valid_access_token(user_id)
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{API_URL}/users/me/messages/{message_id}/attachments/{attachment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Attachment download failed: {res.text}")
    data = res.json().get("data", "")
    return base64.urlsafe_b64decode(data + "==")

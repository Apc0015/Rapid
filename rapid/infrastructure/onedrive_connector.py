"""
OneDrive connector — OAuth2 PKCE (public client, no client secret).

Environment variables required:
  MICROSOFT_CLIENT_ID      — Azure App Registration client ID
  MICROSOFT_REDIRECT_URI   — must match Azure portal, e.g. http://localhost:8000/cloud/onedrive/callback
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from .cloud_tokens import get_token, save_token, delete_token

# ── OAuth2 PKCE constants ──────────────────────────────────────────────────────

AUTHORITY   = "https://login.microsoftonline.com/common"
SCOPES      = "Files.Read Files.ReadWrite offline_access User.Read"
TOKEN_URL   = f"{AUTHORITY}/oauth2/v2.0/token"
AUTH_URL    = f"{AUTHORITY}/oauth2/v2.0/authorize"
GRAPH_URL   = "https://graph.microsoft.com/v1.0"

# In-memory store for pending PKCE challenges (cleared after use)
# { state: (code_verifier, user_id) }
_pending: dict[str, tuple[str, str]] = {}


def _client_id() -> str:
    v = os.getenv("MICROSOFT_CLIENT_ID", "")
    if not v:
        raise RuntimeError("MICROSOFT_CLIENT_ID is not set. See .env")
    return v


def _redirect_uri() -> str:
    return os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/cloud/onedrive/callback")


def _flutter_redirect() -> str:
    return os.getenv("FLUTTER_BASE_URL", "http://localhost:3000")


# ── PKCE helpers ───────────────────────────────────────────────────────────────

def _code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# ── Public API ─────────────────────────────────────────────────────────────────

def get_auth_url(user_id: str) -> str:
    """Generate the Microsoft OAuth2 authorization URL with PKCE."""
    verifier   = _code_verifier()
    challenge  = _code_challenge(verifier)
    state      = secrets.token_urlsafe(16)
    _pending[state] = (verifier, user_id)

    params = {
        "client_id":             _client_id(),
        "response_type":         "code",
        "redirect_uri":          _redirect_uri(),
        "scope":                 SCOPES,
        "state":                 state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
        "response_mode":         "query",
        "prompt":                "select_account",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


async def exchange_code(code: str, state: str) -> dict:
    """Exchange authorization code for tokens (called from callback route)."""
    if state not in _pending:
        raise ValueError("Invalid or expired OAuth state")
    verifier, user_id = _pending.pop(state)

    data = {
        "client_id":     _client_id(),
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  _redirect_uri(),
        "code_verifier": verifier,
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(TOKEN_URL, data=data)
    if res.status_code != 200:
        raise RuntimeError(f"Token exchange failed: {res.text}")
    token = res.json()
    expires_at = datetime.now(timezone.utc).timestamp() + token.get("expires_in", 3600)
    token["expires_at"] = expires_at
    token["user_id"]    = user_id
    save_token("onedrive", user_id, token)
    return token


async def _get_valid_access_token(user_id: str) -> str:
    """Return a valid access token, refreshing if needed."""
    stored = get_token("onedrive", user_id)
    if not stored:
        raise RuntimeError("OneDrive not connected")
    now = datetime.now(timezone.utc).timestamp()
    if now >= stored.get("expires_at", 0) - 60:
        # Refresh
        data = {
            "client_id":    _client_id(),
            "grant_type":   "refresh_token",
            "refresh_token": stored["refresh_token"],
            "scope":         SCOPES,
        }
        async with httpx.AsyncClient() as client:
            res = await client.post(TOKEN_URL, data=data)
        if res.status_code != 200:
            delete_token("onedrive", user_id)
            raise RuntimeError("Token refresh failed — please reconnect OneDrive")
        new_token = res.json()
        new_token["expires_at"] = now + new_token.get("expires_in", 3600)
        new_token["user_id"]    = user_id
        save_token("onedrive", user_id, new_token)
        return new_token["access_token"]
    return stored["access_token"]


async def list_files(user_id: str, folder_path: str = "/") -> list[dict]:
    """List files/folders in a OneDrive folder."""
    token = await _get_valid_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    if folder_path == "/" or folder_path == "":
        url = f"{GRAPH_URL}/me/drive/root/children"
    else:
        encoded = folder_path.strip("/").replace("/", ":")
        url = f"{GRAPH_URL}/me/drive/root:/{encoded}:/children"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, params={"$top": 100})
    if res.status_code != 200:
        raise RuntimeError(f"OneDrive list failed: {res.text}")
    items = res.json().get("value", [])
    return [
        {
            "id":       item["id"],
            "name":     item["name"],
            "type":     "folder" if "folder" in item else "file",
            "size":     item.get("size", 0),
            "mimeType": item.get("file", {}).get("mimeType"),
            "path":     item.get("parentReference", {}).get("path", "") + "/" + item["name"],
        }
        for item in items
    ]


async def download_file(user_id: str, item_id: str) -> tuple[bytes, str]:
    """Download a file from OneDrive. Returns (bytes, filename)."""
    token = await _get_valid_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    # First get item metadata for filename
    async with httpx.AsyncClient() as client:
        meta = await client.get(f"{GRAPH_URL}/me/drive/items/{item_id}", headers=headers)
        if meta.status_code != 200:
            raise RuntimeError(f"Could not get file metadata: {meta.text}")
        filename = meta.json().get("name", "onedrive_file")
        # Download content
        dl = await client.get(f"{GRAPH_URL}/me/drive/items/{item_id}/content",
                              headers=headers, follow_redirects=True)
        if dl.status_code != 200:
            raise RuntimeError(f"Download failed: {dl.text}")
        return dl.content, filename


async def get_user_email(user_id: str) -> str:
    """Fetch the Microsoft account email for display."""
    try:
        token = await _get_valid_access_token(user_id)
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{GRAPH_URL}/me", headers=headers)
        if res.status_code == 200:
            data = res.json()
            return data.get("userPrincipalName") or data.get("mail") or ""
    except Exception:
        pass
    return ""

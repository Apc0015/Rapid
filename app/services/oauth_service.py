import os
import time
import secrets
from typing import Dict, Optional

import httpx
from fastapi import HTTPException


class OAuthService:
    """Minimal OAuth 2.0 helper for Google/Microsoft/Generic OIDC."""

    def __init__(self):
        self._state_store: Dict[str, Dict] = {}
        self._state_ttl_seconds = 600

    # ------------------------------------------------------------------
    # State handling
    # ------------------------------------------------------------------

    def create_state(self, provider: str, username: Optional[str] = None) -> str:
        state = secrets.token_urlsafe(24)
        self._state_store[state] = {
            "provider": provider,
            "username": username,
            "created_at": time.time(),
        }
        return state

    def validate_state(self, state: str, provider: str) -> Dict:
        data = self._state_store.get(state)
        if not data or data.get("provider") != provider:
            raise HTTPException(status_code=400, detail="Invalid OAuth state")
        if time.time() - data.get("created_at", 0) > self._state_ttl_seconds:
            del self._state_store[state]
            raise HTTPException(status_code=400, detail="Expired OAuth state")
        del self._state_store[state]
        return data

    # ------------------------------------------------------------------
    # Provider configuration
    # ------------------------------------------------------------------

    def _get_provider_config(self, provider: str) -> Dict[str, str]:
        provider = provider.lower()
        if provider == "google":
            return {
                "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
                "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
                "redirect_uri": os.getenv("GOOGLE_OAUTH_REDIRECT_URI", ""),
                "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
                "scope": "openid email profile",
            }
        if provider == "microsoft":
            tenant = os.getenv("MICROSOFT_OAUTH_TENANT", "common")
            return {
                "client_id": os.getenv("MICROSOFT_OAUTH_CLIENT_ID", ""),
                "client_secret": os.getenv("MICROSOFT_OAUTH_CLIENT_SECRET", ""),
                "redirect_uri": os.getenv("MICROSOFT_OAUTH_REDIRECT_URI", ""),
                "auth_url": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
                "token_url": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
                "scope": "openid email profile",
            }
        if provider == "oidc":
            return {
                "client_id": os.getenv("OIDC_CLIENT_ID", ""),
                "client_secret": os.getenv("OIDC_CLIENT_SECRET", ""),
                "redirect_uri": os.getenv("OIDC_REDIRECT_URI", ""),
                "auth_url": os.getenv("OIDC_AUTH_URL", ""),
                "token_url": os.getenv("OIDC_TOKEN_URL", ""),
                "userinfo_url": os.getenv("OIDC_USERINFO_URL", ""),
                "scope": os.getenv("OIDC_SCOPE", "openid email profile"),
            }
        if provider == "dropbox":
            return {
                "client_id": os.getenv("DROPBOX_OAUTH_CLIENT_ID", ""),
                "client_secret": os.getenv("DROPBOX_OAUTH_CLIENT_SECRET", ""),
                "redirect_uri": os.getenv("DROPBOX_OAUTH_REDIRECT_URI", ""),
                "auth_url": "https://www.dropbox.com/oauth2/authorize",
                "token_url": "https://api.dropboxapi.com/oauth2/token",
                "userinfo_url": "https://api.dropboxapi.com/2/users/get_current_account",
                "scope": "",
            }
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")

    # ------------------------------------------------------------------
    # OAuth Flow
    # ------------------------------------------------------------------

    def get_authorization_url(self, provider: str, state: str) -> str:
        cfg = self._get_provider_config(provider)
        if not cfg["client_id"] or not cfg["redirect_uri"] or not cfg["auth_url"]:
            raise HTTPException(status_code=400, detail="OAuth provider not configured")
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
        }
        # Dropbox uses token endpoint and no scope by default
        if provider == "dropbox":
            params.pop("scope", None)
        return f"{cfg['auth_url']}?{httpx.QueryParams(params)}"

    async def exchange_code(self, provider: str, code: str) -> Dict:
        cfg = self._get_provider_config(provider)
        if not cfg["client_id"] or not cfg["client_secret"] or not cfg["redirect_uri"]:
            raise HTTPException(status_code=400, detail="OAuth provider not configured")
        data = {
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": cfg["redirect_uri"],
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(cfg["token_url"], data=data, timeout=15)
            resp.raise_for_status()
            return resp.json()

    async def fetch_user_info(self, provider: str, token: Dict) -> Dict:
        cfg = self._get_provider_config(provider)
        access_token = token.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Missing access token")
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            if provider == "dropbox":
                resp = await client.post(cfg["userinfo_url"], headers=headers, timeout=15)
            else:
                resp = await client.get(cfg["userinfo_url"], headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        # Normalize common fields
        return {
            "id": data.get("sub") or data.get("id") or data.get("account_id"),
            "email": data.get("email") or data.get("mail") or data.get("userPrincipalName"),
            "name": data.get("name") or data.get("displayName") or data.get("given_name"),
            "raw": data,
        }

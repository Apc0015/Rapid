"""
Cloud token store — atomic JSON read/write for OneDrive and Gmail OAuth tokens.

File layout (data/cloud_tokens.json):
{
  "onedrive": {
    "<user_id>": {
      "access_token": "...",
      "refresh_token": "...",
      "expires_at": "2026-01-01T00:00:00+00:00"
    }
  },
  "gmail": {
    "<user_id>": { ... }
  }
}
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

_TOKEN_FILE = Path("data/cloud_tokens.json")
_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if not _TOKEN_FILE.exists():
        return {}
    try:
        return json.loads(_TOKEN_FILE.read_text())
    except Exception:
        return {}


def _save(data: dict) -> None:
    """Atomic write using a temp file + os.replace."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=_TOKEN_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, _TOKEN_FILE)
    except Exception:
        os.unlink(tmp_path)
        raise


def get_token(service: str, user_id: str) -> Optional[dict]:
    """Return the stored token dict for a user+service, or None."""
    data = _load()
    return data.get(service, {}).get(user_id)


def save_token(service: str, user_id: str, token_data: dict) -> None:
    """Save / overwrite a token for a user+service."""
    data = _load()
    data.setdefault(service, {})[user_id] = token_data
    _save(data)


def delete_token(service: str, user_id: str) -> None:
    """Remove a token (disconnect)."""
    data = _load()
    if service in data and user_id in data[service]:
        del data[service][user_id]
        _save(data)


def is_connected(service: str, user_id: str) -> bool:
    return get_token(service, user_id) is not None

from __future__ import annotations
"""
routers/backup.py — Admin-only backup management endpoints.

Routes:
  GET  /backup/config          → current config (secrets redacted)
  PUT  /backup/config          → update provider + credentials
  POST /backup/run             → trigger a backup now
  GET  /backup/list            → list recent local backup archives
  GET  /backup/providers       → list supported providers + required env keys
"""

import logging
from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from routers.deps import require_admin
from infrastructure.backup_manager import get_backup_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/backup", tags=["backup"])


# ── Request / Response models ─────────────────────────────────────────────────

class BackupConfigUpdate(BaseModel):
    provider:       Optional[str] = None   # "local" | "s3" | "gcs" | "azure"
    local_dir:      Optional[str] = None
    keep_local:     Optional[int] = None
    # S3
    s3_bucket:      Optional[str] = None
    s3_prefix:      Optional[str] = None
    s3_region:      Optional[str] = None
    s3_endpoint_url: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    # GCS
    gcs_bucket:     Optional[str] = None
    gcs_prefix:     Optional[str] = None
    google_credentials: Optional[str] = None
    # Azure
    azure_conn_str: Optional[str] = None
    azure_container: Optional[str] = None
    azure_prefix:   Optional[str] = None


_VALID_PROVIDERS = ("local", "s3", "gcs", "azure")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config(current_user: dict = Depends(require_admin)):
    """Return current backup configuration (secrets redacted)."""
    return get_backup_manager().safe_config()


@router.put("/config")
async def update_config(body: BackupConfigUpdate,
                        current_user: dict = Depends(require_admin)):
    """
    Update backup provider and credentials.
    Only supplied (non-None) fields are changed.
    """
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    provider = updates.get("provider")
    if provider and provider not in _VALID_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{provider}'. Valid: {_VALID_PROVIDERS}",
        )

    cfg = get_backup_manager().update_config(updates)
    logger.info(f"[backup] Config updated by admin={current_user['sub']}: {list(updates.keys())}")
    return {"status": "ok", "config": cfg}


@router.post("/run")
async def run_backup(label: str = "",
                     current_user: dict = Depends(require_admin)):
    """
    Trigger an immediate backup.
    Optional `label` is appended to the archive filename.
    """
    logger.info(f"[backup] Manual backup triggered by admin={current_user['sub']}")
    result = await get_backup_manager().run_backup(label=label)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Backup failed"))
    return result


@router.get("/list")
async def list_backups(current_user: dict = Depends(require_admin)):
    """List recent local backup archives (most-recent first)."""
    return {"backups": get_backup_manager().list_local_backups()}


@router.get("/providers")
async def list_providers(current_user: dict = Depends(require_admin)):
    """
    Return metadata about each supported backup provider —
    which env vars / config keys they require.
    """
    return {
        "providers": [
            {
                "id":          "local",
                "name":        "Local filesystem",
                "description": "Store backups in a directory on the same server.",
                "config_keys": ["local_dir", "keep_local"],
            },
            {
                "id":          "s3",
                "name":        "AWS S3 / S3-compatible",
                "description": "Upload to AWS S3, MinIO, Backblaze B2, etc.",
                "config_keys": [
                    "s3_bucket", "s3_prefix", "s3_region",
                    "s3_endpoint_url",   # optional — for S3-compatible services
                    "aws_access_key", "aws_secret_key",
                ],
            },
            {
                "id":          "gcs",
                "name":        "Google Cloud Storage",
                "description": "Upload to a GCS bucket. Set GOOGLE_APPLICATION_CREDENTIALS.",
                "config_keys": ["gcs_bucket", "gcs_prefix", "google_credentials"],
            },
            {
                "id":          "azure",
                "name":        "Azure Blob Storage",
                "description": "Upload to an Azure Blob container.",
                "config_keys": ["azure_conn_str", "azure_container", "azure_prefix"],
            },
        ]
    }

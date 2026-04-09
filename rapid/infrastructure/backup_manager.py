from __future__ import annotations
"""
infrastructure/backup_manager.py — RAPID backup system.

Supports four storage targets (admin selects via env / API):
  • local    — compressed tar.gz on the same machine
  • s3       — AWS S3 / S3-compatible (MinIO, Backblaze B2, etc.)
  • gcs      — Google Cloud Storage
  • azure    — Azure Blob Storage

What gets backed up:
  data/users.yaml          — user registry
  data/db/rapid.db         — chat history + refresh tokens + dept config
  data/faiss/              — all department FAISS indexes
  data/documents.db        — document registry
  data/*.yaml              — any other YAML configs
  rapid.db (if present)    — JWT refresh token store

Config is read from .env; can also be updated at runtime via BackupManager API
(admin stores preferences in data/backup_config.json).
"""

import gzip
import io
import json
import logging
import os
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("data/backup_config.json")
_BACKUP_DIR  = Path("data/backups")          # local storage

# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: Optional["BackupManager"] = None


def get_backup_manager() -> "BackupManager":
    global _manager
    if _manager is None:
        _manager = BackupManager()
    return _manager


# ── Paths that get backed up ──────────────────────────────────────────────────

_BACKUP_PATHS = [
    Path("data/users.yaml"),
    Path("data/governance.yaml"),
    Path("data/departments.yaml"),
    Path("data/db"),
    Path("data/faiss"),
    Path("data/documents.db"),
    Path("rapid.db"),           # JWT refresh tokens (may not exist)
]


class BackupManager:
    """
    Central backup coordinator.  Call run_backup() to create + upload.
    """

    def __init__(self):
        self._cfg: dict = self._load_config()

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        """Load persisted admin config, then overlay env vars."""
        cfg: dict = {}
        if _CONFIG_PATH.exists():
            try:
                cfg = json.loads(_CONFIG_PATH.read_text())
            except Exception:
                pass

        # Env vars always take precedence over saved JSON
        def _env(key: str, default: str = "") -> str:
            return os.getenv(key, cfg.get(key.lower(), default))

        cfg["provider"]         = _env("BACKUP_PROVIDER", cfg.get("provider", "local"))
        cfg["local_dir"]        = _env("BACKUP_LOCAL_DIR", cfg.get("local_dir", str(_BACKUP_DIR)))
        cfg["keep_local"]       = int(_env("BACKUP_KEEP_LOCAL", str(cfg.get("keep_local", 7))))
        # S3
        cfg["s3_bucket"]        = _env("BACKUP_S3_BUCKET")
        cfg["s3_prefix"]        = _env("BACKUP_S3_PREFIX", "rapid-backups/")
        cfg["s3_region"]        = _env("BACKUP_S3_REGION", "us-east-1")
        cfg["s3_endpoint_url"]  = _env("BACKUP_S3_ENDPOINT_URL")   # MinIO / B2 custom endpoint
        cfg["aws_access_key"]   = _env("AWS_ACCESS_KEY_ID")
        cfg["aws_secret_key"]   = _env("AWS_SECRET_ACCESS_KEY")
        # GCS
        cfg["gcs_bucket"]       = _env("BACKUP_GCS_BUCKET")
        cfg["gcs_prefix"]       = _env("BACKUP_GCS_PREFIX", "rapid-backups/")
        cfg["google_credentials"] = _env("GOOGLE_APPLICATION_CREDENTIALS")
        # Azure
        cfg["azure_conn_str"]   = _env("AZURE_STORAGE_CONNECTION_STRING")
        cfg["azure_container"]  = _env("BACKUP_AZURE_CONTAINER", "rapid-backups")
        cfg["azure_prefix"]     = _env("BACKUP_AZURE_PREFIX", "")

        return cfg

    def reload_config(self):
        self._cfg = self._load_config()

    def update_config(self, updates: dict) -> dict:
        """
        Merge updates into persisted config and reload.
        Returns sanitised config (no secrets).
        """
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        current: dict = {}
        if _CONFIG_PATH.exists():
            try:
                current = json.loads(_CONFIG_PATH.read_text())
            except Exception:
                pass
        current.update(updates)
        _CONFIG_PATH.write_text(json.dumps(current, indent=2))
        self.reload_config()
        return self.safe_config()

    def safe_config(self) -> dict:
        """Return config with secrets redacted."""
        hide = {"aws_access_key", "aws_secret_key", "azure_conn_str"}
        return {k: ("***" if k in hide and v else v) for k, v in self._cfg.items()}

    # ── Main entry point ──────────────────────────────────────────────────────

    async def run_backup(self, label: str = "") -> dict:
        """
        Create a backup archive and upload to the configured provider.
        Returns a result dict with status, filename, size, provider.
        """
        ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tag      = f"_{label}" if label else ""
        filename = f"rapid_backup_{ts}{tag}.tar.gz"

        logger.info(f"[backup] Starting backup → {filename}")

        # Build archive in memory
        archive_bytes = self._create_archive(filename)
        size_kb       = len(archive_bytes) // 1024
        logger.info(f"[backup] Archive built: {size_kb} KB")

        provider = self._cfg.get("provider", "local")
        result   = {
            "filename": filename,
            "size_kb":  size_kb,
            "provider": provider,
            "timestamp": ts,
        }

        try:
            if provider == "local":
                self._upload_local(filename, archive_bytes)
                self._prune_local()
                result["status"]   = "ok"
                result["location"] = str(Path(self._cfg["local_dir"]) / filename)

            elif provider == "s3":
                self._upload_s3(filename, archive_bytes)
                result["status"]   = "ok"
                result["location"] = f"s3://{self._cfg['s3_bucket']}/{self._cfg['s3_prefix']}{filename}"

            elif provider == "gcs":
                self._upload_gcs(filename, archive_bytes)
                result["status"]   = "ok"
                result["location"] = f"gs://{self._cfg['gcs_bucket']}/{self._cfg['gcs_prefix']}{filename}"

            elif provider == "azure":
                self._upload_azure(filename, archive_bytes)
                result["status"]   = "ok"
                result["location"] = (
                    f"azure://{self._cfg['azure_container']}/"
                    f"{self._cfg['azure_prefix']}{filename}"
                )
            else:
                raise ValueError(f"Unknown backup provider: '{provider}'")

        except Exception as e:
            logger.error(f"[backup] Failed: {e}")
            result["status"] = "error"
            result["error"]  = str(e)

        logger.info(f"[backup] Done: {result['status']}")
        return result

    # ── Archive builder ───────────────────────────────────────────────────────

    def _create_archive(self, archive_name: str) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for path in _BACKUP_PATHS:
                if not path.exists():
                    continue
                arcname = str(path)        # keep relative path inside archive
                if path.is_dir():
                    tar.add(str(path), arcname=arcname, recursive=True)
                else:
                    tar.add(str(path), arcname=arcname)
        return buf.getvalue()

    # ── Local ─────────────────────────────────────────────────────────────────

    def _upload_local(self, filename: str, data: bytes):
        out_dir = Path(self._cfg.get("local_dir", str(_BACKUP_DIR)))
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / filename).write_bytes(data)
        logger.info(f"[backup/local] Saved to {out_dir / filename}")

    def _prune_local(self):
        """Keep only the N most-recent local backup archives."""
        keep = self._cfg.get("keep_local", 7)
        out_dir = Path(self._cfg.get("local_dir", str(_BACKUP_DIR)))
        archives = sorted(out_dir.glob("rapid_backup_*.tar.gz"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        for old in archives[keep:]:
            try:
                old.unlink()
                logger.debug(f"[backup/local] Pruned {old.name}")
            except Exception:
                pass

    # ── AWS S3 ────────────────────────────────────────────────────────────────

    def _upload_s3(self, filename: str, data: bytes):
        try:
            import boto3  # type: ignore
        except ImportError:
            raise RuntimeError("boto3 not installed — run: pip install boto3")

        kwargs: dict = {
            "region_name":          self._cfg["s3_region"],
            "aws_access_key_id":    self._cfg["aws_access_key"] or None,
            "aws_secret_access_key": self._cfg["aws_secret_key"] or None,
        }
        if self._cfg.get("s3_endpoint_url"):
            kwargs["endpoint_url"] = self._cfg["s3_endpoint_url"]

        s3  = boto3.client("s3", **kwargs)
        key = f"{self._cfg['s3_prefix']}{filename}"
        s3.put_object(
            Bucket=self._cfg["s3_bucket"],
            Key=key,
            Body=data,
            ServerSideEncryption="AES256",
        )
        logger.info(f"[backup/s3] Uploaded to s3://{self._cfg['s3_bucket']}/{key}")

    # ── Google Cloud Storage ──────────────────────────────────────────────────

    def _upload_gcs(self, filename: str, data: bytes):
        try:
            from google.cloud import storage as gcs_storage  # type: ignore
        except ImportError:
            raise RuntimeError(
                "google-cloud-storage not installed — run: pip install google-cloud-storage"
            )

        client = gcs_storage.Client()
        bucket = client.bucket(self._cfg["gcs_bucket"])
        blob   = bucket.blob(f"{self._cfg['gcs_prefix']}{filename}")
        blob.upload_from_string(data, content_type="application/gzip")
        logger.info(f"[backup/gcs] Uploaded to gs://{self._cfg['gcs_bucket']}/{blob.name}")

    # ── Azure Blob ────────────────────────────────────────────────────────────

    def _upload_azure(self, filename: str, data: bytes):
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore
        except ImportError:
            raise RuntimeError(
                "azure-storage-blob not installed — run: pip install azure-storage-blob"
            )

        client    = BlobServiceClient.from_connection_string(self._cfg["azure_conn_str"])
        container = client.get_container_client(self._cfg["azure_container"])
        blob_name = f"{self._cfg.get('azure_prefix', '')}{filename}"
        container.upload_blob(blob_name, data, overwrite=True)
        logger.info(f"[backup/azure] Uploaded to azure://{self._cfg['azure_container']}/{blob_name}")

    # ── List recent local backups ─────────────────────────────────────────────

    def list_local_backups(self) -> list[dict]:
        out_dir = Path(self._cfg.get("local_dir", str(_BACKUP_DIR)))
        if not out_dir.exists():
            return []
        result = []
        for p in sorted(out_dir.glob("rapid_backup_*.tar.gz"),
                        key=lambda x: x.stat().st_mtime, reverse=True):
            result.append({
                "filename":    p.name,
                "size_kb":     p.stat().st_size // 1024,
                "modified_at": datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
        return result

import os
import uuid
import shutil
import sqlite3
import logging
import tempfile
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Import encryption service
try:
    from app.services.encryption_service import EncryptionService
    _encryption_service = EncryptionService()
except Exception as e:
    logger.warning(f"Encryption service not available: {e}")
    _encryption_service = None

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
USER_DB_PATH = os.path.join(DB_DIR, "users.db")
CLOUD_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cloud_cache")

# Supported file extensions (same as TextExtractor)
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".json", ".xlsx", ".xls", ".html", ".htm", ".md", ".markdown", ".xml", ".parquet"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CloudFile:
    """Represents a file in a cloud storage service."""
    file_id: str
    name: str
    path: str
    size: int
    file_type: str  # extension without dot
    is_folder: bool
    modified_at: Optional[str] = None
    cloud_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Abstract connector
# ---------------------------------------------------------------------------

class CloudStorageConnector(ABC):
    """Base class for all cloud storage connectors."""

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the canonical name of this service (e.g. 's3', 'local')."""

    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        """Validate credentials and establish connection. Return True on success."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if the connection is still valid."""

    @abstractmethod
    def list_files(self, folder_path: str = "/") -> List[CloudFile]:
        """List files and folders at the given path."""

    @abstractmethod
    def search_files(self, query: str) -> List[CloudFile]:
        """Search for files matching the query string."""

    @abstractmethod
    def download_file(self, file_id: str, dest_dir: str) -> str:
        """Download a file to dest_dir. Return the local file path."""

    @abstractmethod
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Return metadata for a specific file."""


# ---------------------------------------------------------------------------
# AWS S3 Connector
# ---------------------------------------------------------------------------

class S3Connector(CloudStorageConnector):
    """AWS S3 connector using boto3."""

    service_name = "s3"

    def __init__(self):
        self.client = None
        self.bucket = None
        self.region = None

    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 is required for S3. Install with: pip install boto3")

        access_key = credentials.get("access_key")
        secret_key = credentials.get("secret_key")
        self.bucket = credentials.get("bucket")
        self.region = credentials.get("region", "us-east-1")

        if not all([access_key, secret_key, self.bucket]):
            raise ValueError("S3 requires access_key, secret_key, and bucket")

        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=self.region,
        )
        # Verify access
        self.client.head_bucket(Bucket=self.bucket)
        return True

    def test_connection(self) -> bool:
        if not self.client or not self.bucket:
            return False
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False

    def list_files(self, folder_path: str = "/") -> List[CloudFile]:
        prefix = folder_path.strip("/")
        if prefix:
            prefix += "/"

        paginator = self.client.get_paginator("list_objects_v2")
        files = []

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            # Sub-folders
            for cp in page.get("CommonPrefixes", []):
                folder_name = cp["Prefix"].rstrip("/").split("/")[-1]
                files.append(CloudFile(
                    file_id=cp["Prefix"],
                    name=folder_name,
                    path=cp["Prefix"],
                    size=0,
                    file_type="folder",
                    is_folder=True,
                ))
            # Files
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key == prefix:
                    continue  # Skip the prefix itself
                name = key.split("/")[-1]
                ext = os.path.splitext(name)[1].lower().lstrip(".")
                files.append(CloudFile(
                    file_id=key,
                    name=name,
                    path=key,
                    size=obj.get("Size", 0),
                    file_type=ext,
                    is_folder=False,
                    modified_at=obj.get("LastModified", "").isoformat() if obj.get("LastModified") else None,
                    cloud_url=f"s3://{self.bucket}/{key}",
                ))

        return files

    def search_files(self, query: str) -> List[CloudFile]:
        """Search S3 by prefix/key name match (S3 has no native search)."""
        query_lower = query.lower()
        results = []
        paginator = self.client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if query_lower in key.lower():
                    name = key.split("/")[-1]
                    ext = os.path.splitext(name)[1].lower().lstrip(".")
                    results.append(CloudFile(
                        file_id=key,
                        name=name,
                        path=key,
                        size=obj.get("Size", 0),
                        file_type=ext,
                        is_folder=False,
                        modified_at=obj.get("LastModified", "").isoformat() if obj.get("LastModified") else None,
                        cloud_url=f"s3://{self.bucket}/{key}",
                    ))
                if len(results) >= 100:
                    break

        return results

    def download_file(self, file_id: str, dest_dir: str) -> str:
        name = file_id.split("/")[-1]
        local_path = os.path.join(dest_dir, name)
        self.client.download_file(self.bucket, file_id, local_path)
        return local_path

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        resp = self.client.head_object(Bucket=self.bucket, Key=file_id)
        return {
            "file_id": file_id,
            "size": resp.get("ContentLength", 0),
            "content_type": resp.get("ContentType", ""),
            "last_modified": resp.get("LastModified", "").isoformat() if resp.get("LastModified") else None,
            "etag": resp.get("ETag", ""),
        }


# ---------------------------------------------------------------------------
# Local Filesystem Connector
# ---------------------------------------------------------------------------

class LocalFilesystemConnector(CloudStorageConnector):
    """Connector for local/network file system paths."""

    service_name = "local"

    def __init__(self):
        self.base_path = None

    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        path = credentials.get("path")
        if not path:
            raise ValueError("Local filesystem requires a 'path' credential")
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            raise ValueError(f"Directory does not exist: {path}")
        self.base_path = os.path.abspath(path)
        return True

    def test_connection(self) -> bool:
        return self.base_path is not None and os.path.isdir(self.base_path)

    def list_files(self, folder_path: str = "/") -> List[CloudFile]:
        if folder_path in ("/", ""):
            target = self.base_path
        else:
            target = os.path.join(self.base_path, folder_path.lstrip("/"))

        target = os.path.abspath(target)
        if not target.startswith(self.base_path):
            raise ValueError("Path traversal not allowed")
        if not os.path.isdir(target):
            raise ValueError(f"Not a directory: {target}")

        files = []
        try:
            for entry in os.scandir(target):
                rel_path = os.path.relpath(entry.path, self.base_path)
                if entry.is_dir():
                    files.append(CloudFile(
                        file_id=rel_path,
                        name=entry.name,
                        path=rel_path,
                        size=0,
                        file_type="folder",
                        is_folder=True,
                    ))
                else:
                    stat = entry.stat()
                    ext = os.path.splitext(entry.name)[1].lower().lstrip(".")
                    files.append(CloudFile(
                        file_id=rel_path,
                        name=entry.name,
                        path=rel_path,
                        size=stat.st_size,
                        file_type=ext,
                        is_folder=False,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        cloud_url=f"file://{entry.path}",
                    ))
        except PermissionError:
            logger.warning("Permission denied: %s", target)

        return files

    def search_files(self, query: str) -> List[CloudFile]:
        query_lower = query.lower()
        results = []

        for root, dirs, filenames in os.walk(self.base_path):
            for name in filenames:
                if query_lower in name.lower():
                    full_path = os.path.join(root, name)
                    rel_path = os.path.relpath(full_path, self.base_path)
                    stat = os.stat(full_path)
                    ext = os.path.splitext(name)[1].lower().lstrip(".")
                    results.append(CloudFile(
                        file_id=rel_path,
                        name=name,
                        path=rel_path,
                        size=stat.st_size,
                        file_type=ext,
                        is_folder=False,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        cloud_url=f"file://{full_path}",
                    ))
                    if len(results) >= 100:
                        return results

        return results

    def download_file(self, file_id: str, dest_dir: str) -> str:
        source = os.path.join(self.base_path, file_id)
        source = os.path.abspath(source)
        if not source.startswith(self.base_path):
            raise ValueError("Path traversal not allowed")
        if not os.path.isfile(source):
            raise FileNotFoundError(f"File not found: {file_id}")
        dest = os.path.join(dest_dir, os.path.basename(source))
        shutil.copy2(source, dest)
        return dest

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        fpath = os.path.join(self.base_path, file_id)
        fpath = os.path.abspath(fpath)
        if not fpath.startswith(self.base_path):
            raise ValueError("Path traversal not allowed")
        stat = os.stat(fpath)
        return {
            "file_id": file_id,
            "size": stat.st_size,
            "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "absolute_path": fpath,
        }


# ---------------------------------------------------------------------------
# Azure Blob Storage Connector
# ---------------------------------------------------------------------------

class AzureBlobConnector(CloudStorageConnector):
    """Azure Blob Storage connector using azure-storage-blob SDK."""

    service_name = "azure_blob"

    def __init__(self):
        self.client = None
        self.container_client = None
        self.container_name = None
        self.account_name = None

    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError:
            raise RuntimeError(
                "azure-storage-blob is required. Install with: pip install azure-storage-blob"
            )

        conn_string = credentials.get("connection_string")
        self.container_name = credentials.get("container")
        if not self.container_name:
            raise ValueError("Azure Blob requires a 'container' name")

        if conn_string:
            self.client = BlobServiceClient.from_connection_string(conn_string)
        else:
            account_name = credentials.get("account_name")
            account_key = credentials.get("account_key")
            if not all([account_name, account_key]):
                raise ValueError(
                    "Azure Blob requires either 'connection_string' or "
                    "'account_name' + 'account_key'"
                )
            self.account_name = account_name
            account_url = f"https://{account_name}.blob.core.windows.net"
            self.client = BlobServiceClient(
                account_url=account_url, credential=account_key
            )

        self.container_client = self.client.get_container_client(self.container_name)
        # Verify access
        self.container_client.get_container_properties()
        return True

    def test_connection(self) -> bool:
        if not self.container_client:
            return False
        try:
            self.container_client.get_container_properties()
            return True
        except Exception:
            return False

    def list_files(self, folder_path: str = "/") -> List[CloudFile]:
        prefix = folder_path.strip("/")
        if prefix:
            prefix += "/"

        files = []
        seen_folders: set = set()

        blobs = self.container_client.walk_blobs(name_starts_with=prefix if prefix != "/" else "", delimiter="/")
        for item in blobs:
            if hasattr(item, "prefix"):  # virtual folder
                folder_name = item.prefix.rstrip("/").split("/")[-1]
                if folder_name not in seen_folders:
                    seen_folders.add(folder_name)
                    files.append(CloudFile(
                        file_id=item.prefix,
                        name=folder_name,
                        path=item.prefix,
                        size=0,
                        file_type="folder",
                        is_folder=True,
                    ))
            else:
                name = item.name.split("/")[-1]
                if not name:
                    continue
                ext = os.path.splitext(name)[1].lower().lstrip(".")
                files.append(CloudFile(
                    file_id=item.name,
                    name=name,
                    path=item.name,
                    size=item.size or 0,
                    file_type=ext,
                    is_folder=False,
                    modified_at=item.last_modified.isoformat() if item.last_modified else None,
                    cloud_url=f"https://{self.account_name or 'azure'}.blob.core.windows.net/{self.container_name}/{item.name}",
                ))

        return files

    def search_files(self, query: str) -> List[CloudFile]:
        """Search Azure Blob by name match (list all and filter)."""
        query_lower = query.lower()
        results = []

        for blob in self.container_client.list_blobs():
            if query_lower in blob.name.lower():
                name = blob.name.split("/")[-1]
                ext = os.path.splitext(name)[1].lower().lstrip(".")
                results.append(CloudFile(
                    file_id=blob.name,
                    name=name,
                    path=blob.name,
                    size=blob.size or 0,
                    file_type=ext,
                    is_folder=False,
                    modified_at=blob.last_modified.isoformat() if blob.last_modified else None,
                    cloud_url=f"https://{self.account_name or 'azure'}.blob.core.windows.net/{self.container_name}/{blob.name}",
                ))
                if len(results) >= 100:
                    break

        return results

    def download_file(self, file_id: str, dest_dir: str) -> str:
        name = file_id.split("/")[-1]
        local_path = os.path.join(dest_dir, name)
        blob_client = self.container_client.get_blob_client(file_id)
        with open(local_path, "wb") as f:
            stream = blob_client.download_blob()
            f.write(stream.readall())
        return local_path

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        blob_client = self.container_client.get_blob_client(file_id)
        props = blob_client.get_blob_properties()
        return {
            "file_id": file_id,
            "size": props.size,
            "content_type": props.content_settings.content_type if props.content_settings else "",
            "last_modified": props.last_modified.isoformat() if props.last_modified else None,
            "etag": props.etag or "",
        }


# ---------------------------------------------------------------------------
# Lazy connector imports (avoid ImportError when optional SDKs missing)
# ---------------------------------------------------------------------------

def _lazy_import_google_drive():
    from app.services.google_drive_connector import GoogleDriveConnector
    return GoogleDriveConnector

def _lazy_import_onedrive():
    from app.services.onedrive_connector import OneDriveConnector
    return OneDriveConnector

def _lazy_import_dropbox():
    from app.services.dropbox_connector import DropboxConnector
    return DropboxConnector


# ---------------------------------------------------------------------------
# Connector registry
# ---------------------------------------------------------------------------

CONNECTOR_REGISTRY: Dict[str, type] = {
    "s3": S3Connector,
    "local": LocalFilesystemConnector,
    "azure_blob": AzureBlobConnector,
}

# Register OAuth connectors if their modules load (SDKs may not be installed)
for _name, _loader in [("google_drive", _lazy_import_google_drive),
                        ("onedrive", _lazy_import_onedrive),
                        ("dropbox", _lazy_import_dropbox)]:
    try:
        CONNECTOR_REGISTRY[_name] = _loader()
    except Exception:  # noqa: broad-except OK for optional connectors
        logger.debug("Optional connector '%s' not available (missing SDK)", _name)


# ---------------------------------------------------------------------------
# CloudStorageService — manages per-user connections
# ---------------------------------------------------------------------------

class CloudStorageService:
    """Manages cloud storage connections per user with SQLite persistence."""

    def __init__(self):
        self._connectors: Dict[str, CloudStorageConnector] = {}  # conn_id → live connector
        self._init_db()
        os.makedirs(CLOUD_CACHE_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _init_db(self):
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(USER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cloud_connections (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                service_name TEXT NOT NULL,
                display_name TEXT,
                credentials TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_used TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cloud_file_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                connection_id TEXT NOT NULL,
                service_name TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT,
                file_size INTEGER,
                cloud_url TEXT,
                doc_id TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                FOREIGN KEY (connection_id) REFERENCES cloud_connections(id)
            )
        """)
        conn.commit()
        conn.close()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(USER_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect_service(
        self,
        username: str,
        service_name: str,
        credentials: Dict[str, Any],
        display_name: Optional[str] = None,
    ) -> str:
        """Connect to a cloud service. Returns connection_id."""
        service_name = service_name.lower()
        connector_cls = CONNECTOR_REGISTRY.get(service_name)
        if connector_cls is None:
            raise ValueError(
                f"Unsupported service: {service_name}. "
                f"Available: {', '.join(CONNECTOR_REGISTRY.keys())}"
            )

        connector = connector_cls()
        connector.authenticate(credentials)

        conn_id = f"{service_name}_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        # Encrypt and store credentials
        creds_json = json.dumps(credentials)
        if _encryption_service and _encryption_service.is_available():
            encrypted_creds = _encryption_service.encrypt(creds_json)
            if encrypted_creds is None:
                raise ValueError("Failed to encrypt credentials")
            stored_creds = encrypted_creds
            logger.info("Credentials encrypted successfully")
        else:
            logger.warning("Storing credentials without encryption (INSECURE!)")
            stored_creds = creds_json

        db = self._get_db()
        try:
            db.execute(
                """INSERT INTO cloud_connections
                   (id, username, service_name, display_name, credentials, is_active, created_at, last_used)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (conn_id, username, service_name,
                 display_name or f"{service_name.upper()} Connection",
                 stored_creds, now, now),
            )
            db.commit()
        finally:
            db.close()

        self._connectors[conn_id] = connector
        logger.info("User %s connected %s (conn_id=%s)", username, service_name, conn_id)
        return conn_id

    def disconnect_service(self, username: str, connection_id: str) -> bool:
        """Disconnect and remove a cloud service connection."""
        db = self._get_db()
        try:
            row = db.execute(
                "SELECT * FROM cloud_connections WHERE id = ? AND username = ?",
                (connection_id, username),
            ).fetchone()
            if not row:
                return False

            db.execute(
                "UPDATE cloud_connections SET is_active = 0 WHERE id = ?",
                (connection_id,),
            )
            db.commit()
        finally:
            db.close()

        self._connectors.pop(connection_id, None)
        logger.info("User %s disconnected %s", username, connection_id)
        return True

    def get_user_services(self, username: str) -> List[Dict[str, Any]]:
        """List all connected services for a user."""
        db = self._get_db()
        try:
            rows = db.execute(
                "SELECT id, service_name, display_name, credentials, is_active, created_at, last_used "
                "FROM cloud_connections WHERE username = ? AND is_active = 1 ORDER BY created_at DESC",
                (username,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            db.close()

    def _get_connector(self, connection_id: str, username: str) -> CloudStorageConnector:
        """Get a live connector, reconnecting if needed."""
        if connection_id in self._connectors:
            return self._connectors[connection_id]
        raise ValueError(
            f"Connection {connection_id} not found or not active. "
            "Please reconnect the service."
        )

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def list_files(self, username: str, connection_id: str, folder_path: str = "/") -> List[Dict[str, Any]]:
        connector = self._get_connector(connection_id, username)
        self._update_last_used(connection_id)
        files = connector.list_files(folder_path)
        return [f.to_dict() for f in files]

    def search_files(self, username: str, connection_id: str, query: str) -> List[Dict[str, Any]]:
        connector = self._get_connector(connection_id, username)
        self._update_last_used(connection_id)
        files = connector.search_files(query)
        return [f.to_dict() for f in files]

    def _update_last_used(self, connection_id: str):
        now = datetime.now(timezone.utc).isoformat()
        db = self._get_db()
        try:
            db.execute(
                "UPDATE cloud_connections SET last_used = ? WHERE id = ?",
                (now, connection_id),
            )
            db.commit()
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Indexing (download → TextExtractor → RAGEngine)
    # ------------------------------------------------------------------

    def index_file(
        self,
        username: str,
        connection_id: str,
        file_id: str,
        rag_engine,
    ) -> Dict[str, Any]:
        """Download a cloud file and index it into the RAG engine."""
        connector = self._get_connector(connection_id, username)

        # Get file info
        meta = connector.get_file_metadata(file_id)
        file_name = file_id.split("/")[-1]
        ext = os.path.splitext(file_name)[1].lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
            )

        # Download to temp directory
        tmp_dir = tempfile.mkdtemp(dir=CLOUD_CACHE_DIR)
        try:
            local_path = connector.download_file(file_id, tmp_dir)
            doc_id = str(uuid.uuid4())

            # Get connection info for source metadata
            db = self._get_db()
            try:
                row = db.execute(
                    "SELECT service_name FROM cloud_connections WHERE id = ?",
                    (connection_id,),
                ).fetchone()
                service_name = row["service_name"] if row else "unknown"
            finally:
                db.close()

            # Index through RAG engine
            source_metadata = {
                "source_type": f"cloud_{service_name}",
                "cloud_service": service_name,
                "cloud_path": file_id,
                "cloud_url": meta.get("cloud_url", meta.get("absolute_path", "")),
                "connection_id": connection_id,
            }
            rag_engine.upload_document(local_path, doc_id, username=username,
                                        source_metadata=source_metadata)

            # Record in cloud_file_index
            now = datetime.now(timezone.utc).isoformat()
            db = self._get_db()
            try:
                db.execute(
                    """INSERT INTO cloud_file_index
                       (username, connection_id, service_name, file_id, file_name,
                        file_path, file_type, file_size, cloud_url, doc_id, indexed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (username, connection_id, service_name, file_id, file_name,
                     file_id, ext.lstrip("."), meta.get("size", meta.get("ContentLength", 0)),
                     meta.get("cloud_url", meta.get("absolute_path", "")),
                     doc_id, now),
                )
                db.commit()
            finally:
                db.close()

            self._update_last_used(connection_id)
            logger.info("Indexed cloud file %s (doc_id=%s) for user %s", file_id, doc_id, username)

            return {
                "doc_id": doc_id,
                "file_name": file_name,
                "service": service_name,
                "file_path": file_id,
            }
        finally:
            # Clean up temp files
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def index_folder(
        self,
        username: str,
        connection_id: str,
        folder_path: str,
        rag_engine,
        recursive: bool = True,
    ) -> List[Dict[str, Any]]:
        """Index all supported files in a cloud folder."""
        connector = self._get_connector(connection_id, username)
        files = connector.list_files(folder_path)
        indexed = []

        for f in files:
            if f.is_folder and recursive:
                sub_results = self.index_folder(
                    username, connection_id, f.path, rag_engine, recursive=True
                )
                indexed.extend(sub_results)
            elif not f.is_folder:
                ext = f".{f.file_type}" if f.file_type else ""
                if ext in SUPPORTED_EXTENSIONS:
                    try:
                        result = self.index_file(username, connection_id, f.file_id, rag_engine)
                        indexed.append(result)
                    except Exception as e:
                        logger.warning("Failed to index %s: %s", f.file_id, e)
                        indexed.append({
                            "file_name": f.name,
                            "file_path": f.path,
                            "error": str(e),
                        })

        return indexed

    def get_indexed_files(self, username: str) -> List[Dict[str, Any]]:
        """Get all cloud files that have been indexed for this user."""
        db = self._get_db()
        try:
            rows = db.execute(
                "SELECT * FROM cloud_file_index WHERE username = ? ORDER BY indexed_at DESC",
                (username,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            db.close()

    def get_available_services(self) -> List[Dict[str, str]]:
        """Return list of available cloud services."""
        return [
            {"name": "s3", "label": "AWS S3", "auth_type": "credentials",
             "description": "Amazon S3 bucket access"},
            {"name": "azure_blob", "label": "Azure Blob Storage", "auth_type": "credentials",
             "description": "Azure Blob Storage container access"},
            {"name": "local", "label": "Local Filesystem", "auth_type": "path",
             "description": "Local or network drive folders"},
            {"name": "google_drive", "label": "Google Drive", "auth_type": "oauth",
             "description": "Google Drive via OAuth2 access token",
             "available": "google_drive" in CONNECTOR_REGISTRY},
            {"name": "onedrive", "label": "Microsoft OneDrive", "auth_type": "oauth",
             "description": "OneDrive / SharePoint via Microsoft Graph",
             "available": "onedrive" in CONNECTOR_REGISTRY},
            {"name": "dropbox", "label": "Dropbox", "auth_type": "oauth",
             "description": "Dropbox via access token or app credentials",
             "available": "dropbox" in CONNECTOR_REGISTRY},
        ]

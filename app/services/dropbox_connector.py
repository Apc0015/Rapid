"""
Dropbox connector for RAPID cloud storage.

Uses the official Dropbox SDK for Python.
Requires a Dropbox app with an access token or OAuth2 refresh token.
"""

import os
import logging
from typing import List, Dict, Any

from app.services.cloud_storage_service import CloudStorageConnector, CloudFile

logger = logging.getLogger(__name__)


class DropboxConnector(CloudStorageConnector):
    """Dropbox connector using the official SDK."""

    service_name = "dropbox"

    def __init__(self):
        self.dbx = None

    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        try:
            import dropbox as _dbx_mod
        except ImportError:
            raise RuntimeError("dropbox SDK is required. Install with: pip install dropbox")

        access_token = credentials.get("access_token")
        refresh_token = credentials.get("refresh_token")
        app_key = credentials.get("app_key")
        app_secret = credentials.get("app_secret")

        if access_token:
            self.dbx = _dbx_mod.Dropbox(access_token)
        elif all([refresh_token, app_key, app_secret]):
            self.dbx = _dbx_mod.Dropbox(
                oauth2_refresh_token=refresh_token,
                app_key=app_key,
                app_secret=app_secret,
            )
        else:
            raise ValueError(
                "Dropbox requires 'access_token' or "
                "'refresh_token' + 'app_key' + 'app_secret'"
            )

        # Verify access
        self.dbx.users_get_current_account()
        return True

    def test_connection(self) -> bool:
        if not self.dbx:
            return False
        try:
            self.dbx.users_get_current_account()
            return True
        except Exception:
            return False

    def list_files(self, folder_path: str = "/") -> List[CloudFile]:
        import dropbox as _dbx_mod

        path = "" if folder_path in ("/", "") else folder_path

        result = self.dbx.files_list_folder(path)
        files = []

        for entry in result.entries:
            is_folder = isinstance(entry, _dbx_mod.files.FolderMetadata)
            name = entry.name
            ext = os.path.splitext(name)[1].lower().lstrip(".") if not is_folder else "folder"

            cf = CloudFile(
                file_id=entry.path_lower or entry.id,
                name=name,
                path=entry.path_display or entry.path_lower,
                size=getattr(entry, "size", 0) or 0,
                file_type="folder" if is_folder else ext,
                is_folder=is_folder,
                modified_at=(
                    entry.client_modified.isoformat()
                    if hasattr(entry, "client_modified") and entry.client_modified
                    else None
                ),
                cloud_url=None,
            )
            files.append(cf)

        return files

    def search_files(self, query: str) -> List[CloudFile]:
        import dropbox as _dbx_mod

        result = self.dbx.files_search_v2(query)
        files = []

        for match in result.matches:
            meta = match.metadata.get_metadata()
            is_folder = isinstance(meta, _dbx_mod.files.FolderMetadata)
            name = meta.name
            ext = os.path.splitext(name)[1].lower().lstrip(".") if not is_folder else "folder"

            files.append(
                CloudFile(
                    file_id=meta.path_lower or meta.id,
                    name=name,
                    path=meta.path_display or meta.path_lower,
                    size=getattr(meta, "size", 0) or 0,
                    file_type="folder" if is_folder else ext,
                    is_folder=is_folder,
                    modified_at=(
                        meta.client_modified.isoformat()
                        if hasattr(meta, "client_modified") and meta.client_modified
                        else None
                    ),
                    cloud_url=None,
                )
            )
            if len(files) >= 100:
                break

        return files

    def download_file(self, file_id: str, dest_dir: str) -> str:
        name = os.path.basename(file_id)
        local_path = os.path.join(dest_dir, name)

        self.dbx.files_download_to_file(local_path, file_id)
        return local_path

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        meta = self.dbx.files_get_metadata(file_id)
        return {
            "file_id": file_id,
            "name": meta.name,
            "size": getattr(meta, "size", 0) or 0,
            "content_type": "",
            "last_modified": (
                meta.client_modified.isoformat()
                if hasattr(meta, "client_modified") and meta.client_modified
                else None
            ),
            "cloud_url": "",
        }

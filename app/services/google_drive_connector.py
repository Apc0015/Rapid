"""
Google Drive connector for RAPID cloud storage.

Uses google-api-python-client + google-auth-oauthlib for OAuth2 access.
Requires a Google Cloud project with Drive API enabled and OAuth credentials.
"""

import os
import logging
from typing import List, Dict, Any

from app.services.cloud_storage_service import CloudStorageConnector, CloudFile

logger = logging.getLogger(__name__)

# MIME types that map to readable extensions
_MIME_TO_EXT = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/html": ".html",
    "text/markdown": ".md",
    # Google Workspace export mappings
    "application/vnd.google-apps.document": ".docx",
    "application/vnd.google-apps.spreadsheet": ".xlsx",
    "application/vnd.google-apps.presentation": ".pdf",
}

# Matching export MIME types for Google Workspace files
_EXPORT_MIME = {
    "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.presentation": "application/pdf",
}


class GoogleDriveConnector(CloudStorageConnector):
    """Google Drive connector using OAuth2 credentials."""

    service_name = "google_drive"

    def __init__(self):
        self.service = None
        self.creds = None

    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            raise RuntimeError(
                "google-api-python-client and google-auth are required. "
                "Install with: pip install google-api-python-client google-auth-oauthlib"
            )

        access_token = credentials.get("access_token")
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        token_uri = credentials.get("token_uri", "https://oauth2.googleapis.com/token")

        if not access_token:
            raise ValueError(
                "Google Drive requires 'access_token'. "
                "Optionally provide 'refresh_token', 'client_id', 'client_secret' for auto-refresh."
            )

        self.creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri=token_uri,
        )

        self.service = build("drive", "v3", credentials=self.creds)
        # Verify access
        self.service.about().get(fields="user").execute()
        return True

    def test_connection(self) -> bool:
        if not self.service:
            return False
        try:
            self.service.about().get(fields="user").execute()
            return True
        except Exception:
            return False

    def list_files(self, folder_path: str = "/") -> List[CloudFile]:
        folder_id = folder_path if folder_path not in ("/", "") else "root"

        query = f"'{folder_id}' in parents and trashed = false"
        results = (
            self.service.files()
            .list(
                q=query,
                fields="files(id, name, mimeType, size, modifiedTime, webViewLink)",
                pageSize=200,
                orderBy="folder,name",
            )
            .execute()
        )

        files = []
        for item in results.get("files", []):
            is_folder = item["mimeType"] == "application/vnd.google-apps.folder"
            mime = item["mimeType"]
            ext = _MIME_TO_EXT.get(mime, os.path.splitext(item["name"])[1]).lstrip(".")

            files.append(
                CloudFile(
                    file_id=item["id"],
                    name=item["name"],
                    path=item["id"],  # Drive uses IDs, not paths
                    size=int(item.get("size", 0)),
                    file_type="folder" if is_folder else ext,
                    is_folder=is_folder,
                    modified_at=item.get("modifiedTime"),
                    cloud_url=item.get("webViewLink"),
                )
            )

        return files

    def search_files(self, query: str) -> List[CloudFile]:
        safe_query = query.replace("'", "\\'")
        drive_query = f"name contains '{safe_query}' and trashed = false"

        results = (
            self.service.files()
            .list(
                q=drive_query,
                fields="files(id, name, mimeType, size, modifiedTime, webViewLink)",
                pageSize=100,
            )
            .execute()
        )

        files = []
        for item in results.get("files", []):
            is_folder = item["mimeType"] == "application/vnd.google-apps.folder"
            mime = item["mimeType"]
            ext = _MIME_TO_EXT.get(mime, os.path.splitext(item["name"])[1]).lstrip(".")

            files.append(
                CloudFile(
                    file_id=item["id"],
                    name=item["name"],
                    path=item["id"],
                    size=int(item.get("size", 0)),
                    file_type="folder" if is_folder else ext,
                    is_folder=is_folder,
                    modified_at=item.get("modifiedTime"),
                    cloud_url=item.get("webViewLink"),
                )
            )

        return files

    def download_file(self, file_id: str, dest_dir: str) -> str:
        from googleapiclient.http import MediaIoBaseDownload
        import io

        # Get file metadata to determine name and mime type
        meta = self.service.files().get(fileId=file_id, fields="name, mimeType").execute()
        name = meta["name"]
        mime = meta["mimeType"]

        # Google Workspace files need to be exported
        if mime in _EXPORT_MIME:
            export_mime = _EXPORT_MIME[mime]
            ext = _MIME_TO_EXT.get(mime, "")
            if not name.endswith(ext):
                name += ext
            request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            request = self.service.files().get_media(fileId=file_id)

        local_path = os.path.join(dest_dir, name)
        fh = io.FileIO(local_path, "wb")
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.close()

        return local_path

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        meta = (
            self.service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, webViewLink, createdTime",
            )
            .execute()
        )
        return {
            "file_id": meta["id"],
            "name": meta["name"],
            "size": int(meta.get("size", 0)),
            "content_type": meta.get("mimeType", ""),
            "last_modified": meta.get("modifiedTime"),
            "cloud_url": meta.get("webViewLink", ""),
        }

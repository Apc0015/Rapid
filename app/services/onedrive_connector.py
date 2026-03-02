"""
Microsoft OneDrive / SharePoint connector for RAPID cloud storage.

Uses MSAL (Microsoft Authentication Library) + Microsoft Graph API.
Requires an Azure AD app registration with Files.Read or Files.ReadWrite permissions.
"""

import os
import logging
from typing import List, Dict, Any

from app.services.cloud_storage_service import CloudStorageConnector, CloudFile

logger = logging.getLogger(__name__)


class OneDriveConnector(CloudStorageConnector):
    """OneDrive / SharePoint connector using Microsoft Graph API."""

    service_name = "onedrive"

    def __init__(self):
        self.access_token = None
        self.headers = {}

    def authenticate(self, credentials: Dict[str, Any]) -> bool:
        try:
            import requests as _req  # noqa: local alias to avoid clash
        except ImportError:
            raise RuntimeError("requests is required for OneDrive connector")

        access_token = credentials.get("access_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        tenant_id = credentials.get("tenant_id", "common")
        refresh_token = credentials.get("refresh_token")

        if access_token:
            self.access_token = access_token
        elif all([client_id, client_secret, refresh_token]):
            # Acquire token using refresh token
            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/.default",
            }
            resp = _req.post(token_url, data=data, timeout=15)
            if resp.status_code != 200:
                raise ValueError(f"Token refresh failed: {resp.text}")
            self.access_token = resp.json()["access_token"]
        else:
            raise ValueError(
                "OneDrive requires 'access_token' or "
                "'client_id' + 'client_secret' + 'refresh_token'"
            )

        self.headers = {"Authorization": f"Bearer {self.access_token}"}

        # Verify access
        import requests as _req
        resp = _req.get("https://graph.microsoft.com/v1.0/me/drive", headers=self.headers, timeout=10)
        if resp.status_code != 200:
            raise ValueError(f"OneDrive authentication failed: {resp.status_code}")
        return True

    def test_connection(self) -> bool:
        if not self.access_token:
            return False
        try:
            import requests as _req
            resp = _req.get("https://graph.microsoft.com/v1.0/me/drive", headers=self.headers, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def _graph_get(self, url: str) -> dict:
        import requests as _req
        resp = _req.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_files(self, folder_path: str = "/") -> List[CloudFile]:
        if folder_path in ("/", ""):
            url = "https://graph.microsoft.com/v1.0/me/drive/root/children?$top=200"
        else:
            # folder_path is an item ID
            url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_path}/children?$top=200"

        data = self._graph_get(url)
        files = []

        for item in data.get("value", []):
            is_folder = "folder" in item
            name = item["name"]
            ext = os.path.splitext(name)[1].lower().lstrip(".") if not is_folder else "folder"

            files.append(
                CloudFile(
                    file_id=item["id"],
                    name=name,
                    path=item["id"],
                    size=item.get("size", 0),
                    file_type="folder" if is_folder else ext,
                    is_folder=is_folder,
                    modified_at=item.get("lastModifiedDateTime"),
                    cloud_url=item.get("webUrl"),
                )
            )

        return files

    def search_files(self, query: str) -> List[CloudFile]:
        import urllib.parse
        safe_query = urllib.parse.quote(query)
        url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{safe_query}')?$top=100"

        data = self._graph_get(url)
        files = []

        for item in data.get("value", []):
            is_folder = "folder" in item
            name = item["name"]
            ext = os.path.splitext(name)[1].lower().lstrip(".") if not is_folder else "folder"

            files.append(
                CloudFile(
                    file_id=item["id"],
                    name=name,
                    path=item["id"],
                    size=item.get("size", 0),
                    file_type="folder" if is_folder else ext,
                    is_folder=is_folder,
                    modified_at=item.get("lastModifiedDateTime"),
                    cloud_url=item.get("webUrl"),
                )
            )

        return files

    def download_file(self, file_id: str, dest_dir: str) -> str:
        import requests as _req

        # Get download URL
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
        meta = self._graph_get(url)
        name = meta["name"]

        content_url = f"{url}/content"
        resp = _req.get(content_url, headers=self.headers, timeout=60, stream=True)
        resp.raise_for_status()

        local_path = os.path.join(dest_dir, name)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return local_path

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
        meta = self._graph_get(url)
        return {
            "file_id": meta["id"],
            "name": meta["name"],
            "size": meta.get("size", 0),
            "content_type": meta.get("file", {}).get("mimeType", ""),
            "last_modified": meta.get("lastModifiedDateTime"),
            "cloud_url": meta.get("webUrl", ""),
        }

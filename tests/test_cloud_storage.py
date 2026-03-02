import pytest
import os
import shutil
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch
from app.services.cloud_storage_service import (
    CloudStorageService,
    CloudStorageConnector,
    LocalFilesystemConnector,
    S3Connector,
    CloudFile,
    CONNECTOR_REGISTRY,
    SUPPORTED_EXTENSIONS,
)

# Use a temporary database for testing
TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_cloud_users.db")


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    """Use a temporary DB and clean up after each test."""
    monkeypatch.setattr("app.services.cloud_storage_service.USER_DB_PATH", TEST_DB_PATH)
    yield
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture
def service():
    return CloudStorageService()


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files for local connector tests."""
    d = tempfile.mkdtemp()
    # Create test files
    with open(os.path.join(d, "report.txt"), "w") as f:
        f.write("This is a test report about quarterly results.")
    with open(os.path.join(d, "data.csv"), "w") as f:
        f.write("name,value\nfoo,1\nbar,2")
    os.makedirs(os.path.join(d, "subfolder"), exist_ok=True)
    with open(os.path.join(d, "subfolder", "nested.txt"), "w") as f:
        f.write("Nested file content.")
    with open(os.path.join(d, "image.png"), "wb") as f:
        f.write(b"\x89PNG\r\n")  # Unsupported type
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# CloudFile tests
# ---------------------------------------------------------------------------


class TestCloudFile:
    def test_to_dict(self):
        f = CloudFile(
            file_id="abc", name="test.pdf", path="/docs/test.pdf",
            size=1024, file_type="pdf", is_folder=False,
        )
        d = f.to_dict()
        assert d["file_id"] == "abc"
        assert d["name"] == "test.pdf"
        assert d["is_folder"] is False


# ---------------------------------------------------------------------------
# LocalFilesystemConnector
# ---------------------------------------------------------------------------


class TestLocalFilesystemConnector:
    def test_authenticate_valid_path(self, temp_dir):
        conn = LocalFilesystemConnector()
        assert conn.authenticate({"path": temp_dir}) is True

    def test_authenticate_invalid_path(self):
        conn = LocalFilesystemConnector()
        with pytest.raises(ValueError, match="does not exist"):
            conn.authenticate({"path": "/nonexistent/path/12345"})

    def test_authenticate_no_path(self):
        conn = LocalFilesystemConnector()
        with pytest.raises(ValueError, match="path"):
            conn.authenticate({})

    def test_test_connection(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        assert conn.test_connection() is True

    def test_list_files(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        files = conn.list_files("/")
        names = {f.name for f in files}
        assert "report.txt" in names
        assert "data.csv" in names
        assert "subfolder" in names

    def test_list_files_subfolder(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        files = conn.list_files("subfolder")
        assert len(files) == 1
        assert files[0].name == "nested.txt"

    def test_list_files_path_traversal_blocked(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        with pytest.raises(ValueError, match="traversal"):
            conn.list_files("../../etc")

    def test_search_files(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        results = conn.search_files("report")
        assert len(results) == 1
        assert results[0].name == "report.txt"

    def test_search_finds_nested(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        results = conn.search_files("nested")
        assert len(results) == 1

    def test_download_file(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        dest = tempfile.mkdtemp()
        try:
            path = conn.download_file("report.txt", dest)
            assert os.path.exists(path)
            with open(path) as f:
                assert "quarterly" in f.read()
        finally:
            shutil.rmtree(dest, ignore_errors=True)

    def test_download_traversal_blocked(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        with pytest.raises(ValueError, match="traversal"):
            conn.download_file("../../etc/passwd", tempfile.mkdtemp())

    def test_get_file_metadata(self, temp_dir):
        conn = LocalFilesystemConnector()
        conn.authenticate({"path": temp_dir})
        meta = conn.get_file_metadata("report.txt")
        assert meta["size"] > 0
        assert "last_modified" in meta

    def test_service_name(self):
        assert LocalFilesystemConnector.service_name == "local"


# ---------------------------------------------------------------------------
# S3Connector (mocked)
# ---------------------------------------------------------------------------


try:
    import boto3 as _boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


@pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed")
class TestS3Connector:
    def test_service_name(self):
        assert S3Connector.service_name == "s3"

    @patch("boto3.client")
    def test_authenticate(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        conn = S3Connector()
        result = conn.authenticate({
            "access_key": "AKID",
            "secret_key": "secret",
            "bucket": "test-bucket",
        })
        assert result is True
        mock_client.head_bucket.assert_called_once_with(Bucket="test-bucket")

    def test_authenticate_missing_credentials(self):
        conn = S3Connector()
        with pytest.raises((ValueError, RuntimeError)):
            conn.authenticate({"access_key": "AKID"})

    @patch("boto3.client")
    def test_test_connection(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        conn = S3Connector()
        conn.authenticate({"access_key": "AKID", "secret_key": "s", "bucket": "b"})
        assert conn.test_connection() is True

    @patch("boto3.client")
    def test_list_files(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                "CommonPrefixes": [{"Prefix": "docs/"}],
                "Contents": [
                    {"Key": "report.pdf", "Size": 1024, "LastModified": ""},
                ],
            }
        ]
        conn = S3Connector()
        conn.authenticate({"access_key": "A", "secret_key": "S", "bucket": "B"})
        files = conn.list_files("/")
        assert len(files) == 2  # 1 folder + 1 file
        folder = [f for f in files if f.is_folder]
        assert len(folder) == 1
        assert folder[0].name == "docs"


# ---------------------------------------------------------------------------
# CloudStorageService
# ---------------------------------------------------------------------------


class TestCloudStorageService:
    def test_connect_local_service(self, service, temp_dir):
        conn_id = service.connect_service("testuser", "local", {"path": temp_dir})
        assert conn_id.startswith("local_")

    def test_connect_unsupported_service(self, service):
        with pytest.raises(ValueError, match="Unsupported"):
            service.connect_service("testuser", "ftp_server", {})

    def test_get_user_services(self, service, temp_dir):
        service.connect_service("testuser", "local", {"path": temp_dir})
        services = service.get_user_services("testuser")
        assert len(services) == 1
        assert services[0]["service_name"] == "local"

    def test_user_isolation(self, service, temp_dir):
        service.connect_service("alice", "local", {"path": temp_dir})
        service.connect_service("bob", "local", {"path": temp_dir})
        assert len(service.get_user_services("alice")) == 1
        assert len(service.get_user_services("bob")) == 1

    def test_disconnect_service(self, service, temp_dir):
        conn_id = service.connect_service("testuser", "local", {"path": temp_dir})
        result = service.disconnect_service("testuser", conn_id)
        assert result is True
        assert len(service.get_user_services("testuser")) == 0

    def test_disconnect_nonexistent(self, service):
        assert service.disconnect_service("testuser", "fake_id") is False

    def test_disconnect_wrong_user(self, service, temp_dir):
        conn_id = service.connect_service("alice", "local", {"path": temp_dir})
        assert service.disconnect_service("bob", conn_id) is False

    def test_list_files(self, service, temp_dir):
        conn_id = service.connect_service("testuser", "local", {"path": temp_dir})
        files = service.list_files("testuser", conn_id)
        names = {f["name"] for f in files}
        assert "report.txt" in names

    def test_search_files(self, service, temp_dir):
        conn_id = service.connect_service("testuser", "local", {"path": temp_dir})
        results = service.search_files("testuser", conn_id, "data")
        assert len(results) == 1
        assert results[0]["name"] == "data.csv"

    def test_get_available_services(self, service):
        available = service.get_available_services()
        names = {s["name"] for s in available}
        assert "s3" in names
        assert "local" in names
        assert "google_drive" in names  # Listed but not available

    def test_index_file_local(self, service, temp_dir):
        conn_id = service.connect_service("testuser", "local", {"path": temp_dir})

        # Mock RAGEngine
        mock_engine = MagicMock()
        result = service.index_file("testuser", conn_id, "report.txt", mock_engine)

        assert result["file_name"] == "report.txt"
        assert result["doc_id"] is not None
        mock_engine.upload_document.assert_called_once()

        # Check source_metadata was passed
        call_kwargs = mock_engine.upload_document.call_args
        assert call_kwargs.kwargs["source_metadata"]["source_type"] == "cloud_local"

    def test_index_unsupported_file_type(self, service, temp_dir):
        conn_id = service.connect_service("testuser", "local", {"path": temp_dir})
        mock_engine = MagicMock()
        with pytest.raises(ValueError, match="Unsupported file type"):
            service.index_file("testuser", conn_id, "image.png", mock_engine)

    def test_index_folder(self, service, temp_dir):
        conn_id = service.connect_service("testuser", "local", {"path": temp_dir})
        mock_engine = MagicMock()
        results = service.index_folder("testuser", conn_id, "/", mock_engine, recursive=True)
        # Should index report.txt, data.csv, nested.txt (3 supported files, skip image.png)
        indexed = [r for r in results if "error" not in r]
        assert len(indexed) == 3

    def test_get_indexed_files(self, service, temp_dir):
        conn_id = service.connect_service("testuser", "local", {"path": temp_dir})
        mock_engine = MagicMock()
        service.index_file("testuser", conn_id, "report.txt", mock_engine)
        indexed = service.get_indexed_files("testuser")
        assert len(indexed) == 1
        assert indexed[0]["file_name"] == "report.txt"


# ---------------------------------------------------------------------------
# Connector registry
# ---------------------------------------------------------------------------


class TestConnectorRegistry:
    def test_registry_contains_s3(self):
        assert "s3" in CONNECTOR_REGISTRY

    def test_registry_contains_local(self):
        assert "local" in CONNECTOR_REGISTRY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

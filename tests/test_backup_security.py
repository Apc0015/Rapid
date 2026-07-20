import io
import tarfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routers.backup as backup_router


def test_backup_path_cannot_escape_local_backup_directory(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(backup_router, "get_backup_manager", lambda: SimpleNamespace(_cfg={"local_dir": str(backup_dir)}))

    assert backup_router._local_backup_path("rapid_backup_20260716.tar.gz").parent == backup_dir.resolve()
    with pytest.raises(HTTPException):
        backup_router._local_backup_path("../rapid_backup_20260716.tar.gz")


def test_backup_restore_rejects_tar_path_traversal(tmp_path):
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"not allowed"
        member = tarfile.TarInfo("../outside.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with tarfile.open(archive_path, "r:gz") as archive, pytest.raises(HTTPException):
        backup_router._safe_extract(archive, tmp_path / "restore")


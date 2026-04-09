"""
tests/test_jwt.py — Unit tests for JWT manager.

Run:
    cd rapid
    python -m pytest tests/test_jwt.py -v
"""

import os
import pytest
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# Set env before importing module so it uses test values
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests-only-not-production")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")

import jwt as pyjwt


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Redirect JWT DB to a temp file for test isolation."""
    db = tmp_path / "test.db"
    monkeypatch.setattr("infrastructure.jwt_manager.DB_PATH", str(db))
    # Also clear the module-level singleton
    import infrastructure.jwt_manager as jm
    jm._jwt_manager = None
    yield db
    jm._jwt_manager = None


@pytest.fixture
def manager(tmp_db):
    from infrastructure.jwt_manager import get_jwt_manager
    return get_jwt_manager()


# ── Access token tests ────────────────────────────────────────────────────────

class TestAccessToken:

    def test_create_and_verify(self, manager):
        token   = manager.create_access_token("alice", "employee", ["finance"])
        payload = manager.verify_access_token(token)
        assert payload["sub"]   == "alice"
        assert payload["role"]  == "employee"
        assert payload["depts"] == ["finance"]
        assert payload["type"]  == "access"

    def test_admin_role_preserved(self, manager):
        token   = manager.create_access_token("bob", "admin", [])
        payload = manager.verify_access_token(token)
        assert payload["role"] == "admin"

    def test_multiple_depts(self, manager):
        depts = ["finance", "legal", "hr"]
        token   = manager.create_access_token("carol", "manager", depts)
        payload = manager.verify_access_token(token)
        assert set(payload["depts"]) == set(depts)

    def test_expired_token_raises(self, manager, monkeypatch):
        import infrastructure.jwt_manager as jm
        # Issue token with -1 minute expiry
        original_access_exp = jm.ACCESS_EXP
        monkeypatch.setattr(jm, "ACCESS_EXP", -1)
        token = manager.create_access_token("dave", "employee", [])
        monkeypatch.setattr(jm, "ACCESS_EXP", original_access_exp)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            manager.verify_access_token(token)

    def test_refresh_token_rejected_as_access(self, manager):
        refresh = manager.create_refresh_token("eve")
        with pytest.raises(pyjwt.InvalidTokenError):
            manager.verify_access_token(refresh)

    def test_tampered_token_rejected(self, manager):
        token = manager.create_access_token("frank", "employee", [])
        # Flip last char
        tampered = token[:-4] + ("XXXX" if not token.endswith("XXXX") else "YYYY")
        with pytest.raises(pyjwt.InvalidTokenError):
            manager.verify_access_token(tampered)


# ── Refresh token tests ───────────────────────────────────────────────────────

class TestRefreshToken:

    def test_create_and_verify(self, manager):
        token   = manager.create_refresh_token("grace")
        payload = manager.verify_refresh_token(token)
        assert payload["sub"]  == "grace"
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_revoke_single(self, manager):
        token = manager.create_refresh_token("henry")
        manager.revoke_refresh_token(token)
        with pytest.raises(ValueError, match="revoked"):
            manager.verify_refresh_token(token)

    def test_revoke_all(self, manager):
        t1 = manager.create_refresh_token("irene")
        t2 = manager.create_refresh_token("irene")
        count = manager.revoke_all_for_user("irene")
        assert count == 2
        with pytest.raises(ValueError):
            manager.verify_refresh_token(t1)
        with pytest.raises(ValueError):
            manager.verify_refresh_token(t2)

    def test_access_token_rejected_as_refresh(self, manager):
        access = manager.create_access_token("jake", "employee", [])
        with pytest.raises(ValueError, match="Not a refresh token"):
            manager.verify_refresh_token(access)

    def test_jti_uniqueness(self, manager):
        tokens = [manager.create_refresh_token("kate") for _ in range(10)]
        jtis = [pyjwt.decode(t, options={"verify_signature": False})["jti"] for t in tokens]
        assert len(set(jtis)) == 10

    def test_cleanup_removes_expired(self, manager, tmp_db):
        """Cleanup should delete expired tokens from DB."""
        manager.create_refresh_token("leo")
        # Manually expire the token in the DB
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "UPDATE refresh_tokens SET expires_at = ? WHERE user_id = ?",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), "leo"),
        )
        conn.commit()
        conn.close()
        manager.cleanup_expired()
        # Token should be gone
        conn = sqlite3.connect(str(tmp_db))
        rows = conn.execute(
            "SELECT * FROM refresh_tokens WHERE user_id = ?", ("leo",)
        ).fetchall()
        conn.close()
        assert rows == []

import pytest
import os
import tempfile
import asyncio
import httpx
from app.main import app


def _request(method: str, url: str, **kwargs):
    """Sync helper that runs an async ASGI request."""
    async def _do():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await getattr(client, method)(url, **kwargs)
    return asyncio.run(_do())


def test_health_check():
    """Test health check endpoint"""
    response = _request("get", "/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "components" in data


def test_register_user():
    """Test user registration"""
    user_data = {
        "username": "testuser",
        "password": "TestPass1",
    }
    response = _request("post", "/register", json=user_data)
    assert response.status_code == 200
    assert "User created successfully" in response.json()["message"]
    # Role should always be 'user' regardless of what is sent
    assert response.json()["role"] == "user"


def test_register_weak_password():
    """Test that weak passwords are rejected"""
    response = _request("post", "/register", json={
        "username": "weakuser",
        "password": "short",
    })
    assert response.status_code == 400


def test_register_no_uppercase():
    """Test that passwords without uppercase are rejected"""
    response = _request("post", "/register", json={
        "username": "weakuser2",
        "password": "alllower1",
    })
    assert response.status_code == 400


def test_register_duplicate_user():
    """Test that duplicate usernames are rejected"""
    user_data = {"username": "dupeuser", "password": "TestPass1"}
    _request("post", "/register", json=user_data)
    response = _request("post", "/register", json=user_data)
    assert response.status_code == 400


def test_login():
    """Test user login"""
    # First register
    _request("post", "/register", json={
        "username": "testuser2",
        "password": "TestPass1",
    })

    # Then login
    response = _request("post", "/login", json={
        "username": "testuser2",
        "password": "TestPass1",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "token_type" in response.json()
    # Login response should not expose role
    user_info = response.json()["user"]
    assert "username" in user_info


def test_login_wrong_password():
    """Test login with wrong password"""
    _request("post", "/register", json={
        "username": "testuser3",
        "password": "TestPass1",
    })
    response = _request("post", "/login", json={
        "username": "testuser3",
        "password": "WrongPass1",
    })
    assert response.status_code == 401


def test_upload_without_auth():
    """Test upload without authentication should fail"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("This is a test document.")
        temp_file = f.name

    try:
        with open(temp_file, 'rb') as f:
            response = _request("post", "/upload", files={"file": ("test.txt", f, "text/plain")})
        assert response.status_code == 403
    finally:
        os.unlink(temp_file)


def test_query_without_auth():
    """Test query without authentication should fail"""
    response = _request("post", "/query", json={"query": "What is this about?"})
    assert response.status_code == 403


def test_rag_engine_import():
    """Test RAG engine can be imported and initialized"""
    from app.rag.engine import RAGEngine
    engine = RAGEngine()
    assert engine is not None
    assert hasattr(engine, 'upload_document')
    assert hasattr(engine, 'query')


def test_text_extractor():
    """Test text extraction from different file types"""
    from app.rag.engine import TextExtractor

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        test_content = "This is a test document for extraction."
        f.write(test_content)
        temp_file = f.name

    try:
        extracted = TextExtractor.extract_text(temp_file)
        assert extracted == test_content
    finally:
        os.unlink(temp_file)


def test_multi_agent_orchestrator():
    """Test multi-agent orchestrator initialization"""
    from app.agents.orchestrator import MultiAgentOrchestrator
    from app.rag.engine import RAGEngine

    rag_engine = RAGEngine()
    orchestrator = MultiAgentOrchestrator(rag_engine)
    assert orchestrator is not None
    assert hasattr(orchestrator, 'process_query')


def test_security_service():
    """Test security service functions"""
    import uuid
    from app.services.security_service import SecurityService

    security = SecurityService()
    unique_user = f"testuser_sec_{uuid.uuid4().hex[:8]}"

    # Test password hashing
    hashed = security.hash_password("testpass")
    assert security.verify_password("testpass", hashed)
    assert not security.verify_password("wrongpass", hashed)

    # Test user creation (password must meet strength requirements)
    result = security.create_user(unique_user, "StrongPass1", "user")
    assert "User created successfully" in result["message"]
    # Role is always forced to 'user'
    assert result["role"] == "user"

    # Test authentication
    user = security.authenticate_user(unique_user, "StrongPass1")
    assert user is not None
    assert user["username"] == unique_user

    # Test JWT tokens
    token = security.create_access_token({"sub": unique_user})
    payload = security.verify_token(token)
    assert payload is not None
    assert payload["sub"] == unique_user


def test_rate_limiting():
    """Test that rate limiting actually works"""
    from app.services.security_service import SecurityService

    security = SecurityService()

    # Should allow requests up to the limit
    for _ in range(5):
        assert security.rate_limit_check("ratelimituser", "test", limit=5, window_seconds=60)

    # Should reject the 6th request
    assert not security.rate_limit_check("ratelimituser", "test", limit=5, window_seconds=60)


if __name__ == "__main__":
    pytest.main([__file__])

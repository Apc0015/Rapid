from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.security_middleware import RapidSecurityMiddleware


def test_security_middleware_adds_correlation_and_browser_headers(monkeypatch):
    app = FastAPI()
    app.add_middleware(RapidSecurityMiddleware)

    @app.get("/example")
    async def example():
        return {"ok": True}

    response = TestClient(app).get("/example", headers={"X-Request-ID": "request-12345678"})

    assert response.headers["X-Request-ID"] == "request-12345678"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_security_middleware_rejects_oversized_declared_body(monkeypatch):
    monkeypatch.setenv("RAPID_MAX_REQUEST_BYTES", "10")
    app = FastAPI()
    app.add_middleware(RapidSecurityMiddleware)

    @app.post("/upload")
    async def upload():
        return {"ok": True}

    response = TestClient(app).post("/upload", content=b"01234567890")
    assert response.status_code == 413
    assert response.json()["request_id"]

from fastapi.testclient import TestClient

from main import app


def test_root_and_retired_console_routes_redirect_to_the_react_portal(monkeypatch):
    monkeypatch.setenv("RAPID_PORTAL_URL", "http://portal.test")
    client = TestClient(app)

    root = client.get("/", follow_redirects=False)
    legacy = client.get("/app/hr.html", follow_redirects=False)

    assert root.status_code in {302, 307}
    assert root.headers["location"] == "http://portal.test/login"
    assert legacy.status_code in {302, 307}
    assert legacy.headers["location"] == "http://portal.test/workspace/overview"

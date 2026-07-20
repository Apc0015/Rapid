from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.chat_history import ChatHistory
from routers.chat_sessions import router as sessions_router
from routers.deps import get_current_user
from routers.intelligence import router as intelligence_router


def _client(user: dict) -> TestClient:
    app = FastAPI()
    app.include_router(sessions_router)
    app.include_router(intelligence_router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _reset_history(monkeypatch, tmp_path):
    monkeypatch.setattr("infrastructure.chat_history.DB_PATH", tmp_path / "rapid.db")
    ChatHistory._initialized = False
    ChatHistory._initialization_lock = None


def test_chat_sessions_are_tenant_and_user_scoped(monkeypatch, tmp_path):
    _reset_history(monkeypatch, tmp_path)
    owner = {"sub": "shared-user", "role": "ceo", "tenant_id": "northstar", "depts": []}
    client = _client(owner)
    created = client.post("/chat-sessions", json={"title": "Operating review"})

    assert created.status_code == 200
    session_id = created.json()["id"]
    assert [item["id"] for item in client.get("/chat-sessions").json()["sessions"]] == [session_id]

    # The same login key in another tenant cannot enumerate or open the chat.
    other_tenant = _client({"sub": "shared-user", "role": "ceo", "tenant_id": "other-tenant", "depts": []})
    assert other_tenant.get("/chat-sessions").json()["sessions"] == []
    assert other_tenant.get(f"/chat-sessions/{session_id}/messages").status_code == 404

    # A different user in the same tenant is also denied.
    other_user = _client({"sub": "another-user", "role": "ceo", "tenant_id": "northstar", "depts": []})
    assert other_user.get(f"/chat-sessions/{session_id}").status_code == 404


def test_intelligence_chat_persists_governed_turns(monkeypatch, tmp_path):
    _reset_history(monkeypatch, tmp_path)
    monkeypatch.setenv("RAPID_WORKSPACE_DB_PATH", str(tmp_path / "workspace.db"))
    user = {"sub": "founder", "role": "ceo", "tenant_id": "northstar", "depts": []}
    client = _client(user)
    session_id = client.post("/chat-sessions", json={"title": "New Chat"}).json()["id"]

    response = client.post(
        "/intelligence/ask",
        json={
            "question": "What needs attention today?",
            "session_id": session_id,
            "workspace_view": "actions",
        },
    )

    assert response.status_code == 200
    messages = client.get(f"/chat-sessions/{session_id}/messages").json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "What needs attention today?"
    assert messages[1]["metadata"]["response"]["scope"] == "workspace:actions"


def test_chat_history_migrates_legacy_database(monkeypatch, tmp_path):
    import asyncio
    import sqlite3

    database = tmp_path / "rapid.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE chat_sessions (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE chat_messages (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    connection.close()
    _reset_history(monkeypatch, tmp_path)

    session = asyncio.get_event_loop().run_until_complete(
        ChatHistory().create_session("founder", "northstar")
    )

    assert session["tenant_id"] == "northstar"
    check = sqlite3.connect(database)
    session_columns = {row[1] for row in check.execute("PRAGMA table_info(chat_sessions)")}
    message_columns = {row[1] for row in check.execute("PRAGMA table_info(chat_messages)")}
    check.close()
    assert {"tenant_id"} <= session_columns
    assert {"metadata"} <= message_columns

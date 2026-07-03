"""Master spec v1 public API smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# /api/feed, /api/categories, /api/businesses were removed 2026-07-02 (no
# consumers, no promised API). Their smoke tests went with them.


def test_removed_public_data_endpoints_are_gone() -> None:
    """The consumer-less v1 data endpoints no longer resolve (404)."""
    for path in ("/api/feed", "/api/categories", "/api/businesses"):
        assert client.get(path).status_code == 404, path


def test_api_events_list() -> None:
    r = client.get("/api/events", params={"group": "today"})
    assert r.status_code == 200
    assert "items" in r.json()


def test_api_gas_exists() -> None:
    r = client.get("/api/gas")
    assert r.status_code == 200


def test_api_chat_history_requires_session() -> None:
    r = client.get("/api/chat/history", params={"session_id": "test-session-1"})
    assert r.status_code == 200
    assert r.json()["session_id"] == "test-session-1"


def test_contribute_flow_json_start() -> None:
    r = client.post(
        "/api/contribute",
        json={"session_id": "sess-contrib-1", "text": "Farmers market every Saturday morning"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("flow_id")
    assert body.get("type") in ("event", "business", "tip")


def test_lake_havasu_seo_redirect_home() -> None:
    r = client.get("/lake-havasu", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/home"


def test_chat_contribute_mode_returns_flow_component() -> None:
    r = client.post(
        "/api/chat",
        json={
            "message": "I want to add an event to the calendar",
            "session_id": "spec-contrib-chat",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("mode") == "contribute"
    assert body.get("component", {}).get("type") == "contribute_flow"
    assert body["component"]["data"].get("flow_id")


def test_admin_overview_requires_auth() -> None:
    r = client.get("/admin/overview", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/admin/login" in (r.headers.get("location") or "")

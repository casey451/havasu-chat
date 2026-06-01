"""Master spec v1 public API smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_api_feed_returns_json() -> None:
    r = client.get("/api/feed")
    assert r.status_code == 200
    body = r.json()
    assert "events_soon" in body
    assert "generated_at" in body


def test_api_categories_seven_buckets() -> None:
    r = client.get("/api/categories")
    assert r.status_code == 200
    buckets = r.json()["buckets"]
    assert len(buckets) == 7
    ids = {b["id"] for b in buckets}
    assert "events" in ids
    assert "food-drink" in ids


def test_api_businesses_list_paginated() -> None:
    r = client.get("/api/businesses", params={"limit": 5, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert body["limit"] == 5


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
        json={"message": "I want to add an event to the calendar", "session_id": "spec-contrib-chat"},
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

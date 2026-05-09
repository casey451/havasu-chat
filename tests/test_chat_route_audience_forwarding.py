"""Backlog #37 — FastAPI forwards request headers / client IP into ``route()``."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import ChatLog
from app.main import app


def test_post_api_chat_forwards_geo_headers_audience_signal_local() -> None:
    """CDN-style headers reach ``classify_audience`` so geo_bucket is not stuck at unknown."""
    sid = "route-audience-fwd-local"
    query = "find a plumber"
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"query": query, "session_id": sid},
            headers={
                "CF-IPCountry": "US",
                "X-Zip": "86404",
                "Accept-Language": "en-US",
            },
        )
    assert r.status_code == 200
    body = r.json()
    chat_log_id = body.get("chat_log_id")
    assert chat_log_id
    with SessionLocal() as db:
        row = db.get(ChatLog, chat_log_id)
    assert row is not None
    assert row.audience_signal == "local"

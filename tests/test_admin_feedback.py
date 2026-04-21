"""Admin feedback analytics page tests (Phase 6.2.3)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import ChatLog
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


def _clear_chat_logs() -> None:
    with SessionLocal() as db:
        db.query(ChatLog).delete()
        db.commit()


def _seed_log(
    *,
    days_ago: int,
    tier_used: str = "3",
    mode: str = "ask",
    sub_intent: str = "OPEN_ENDED",
    feedback_signal: str | None = None,
    normalized_query: str | None = None,
    response_text: str = "Assistant response",
) -> str:
    with SessionLocal() as db:
        row = ChatLog(
            id=str(uuid4()),
            session_id=f"s-{uuid4().hex[:8]}",
            message=response_text,
            role="assistant",
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
            mode=mode,
            sub_intent=sub_intent,
            tier_used=tier_used,
            feedback_signal=feedback_signal,
            normalized_query=normalized_query,
        )
        db.add(row)
        db.commit()
        return row.id


def test_feedback_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/feedback", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/admin/login")


def test_feedback_empty_state_renders(client: TestClient) -> None:
    _clear_chat_logs()
    _login(client)
    r = client.get("/admin/feedback?window=7d")
    assert r.status_code == 200
    assert "No Tier 3 responses in this window." in r.text
    assert "No negative feedback yet." in r.text
    assert "Feedback analytics" in r.text


def test_feedback_summary_and_recent_negatives(client: TestClient) -> None:
    _clear_chat_logs()
    _login(client)
    neg_id = _seed_log(
        days_ago=1,
        mode="ask",
        sub_intent="OPEN_ENDED",
        feedback_signal="negative",
        normalized_query="best places to eat with kids",
        response_text="Try these places around downtown and by the lake.",
    )
    _seed_log(
        days_ago=2,
        mode="ask",
        sub_intent="OPEN_ENDED",
        feedback_signal="positive",
        normalized_query="family events this weekend",
        response_text="Here are some family events this weekend.",
    )
    _seed_log(
        days_ago=3,
        mode="ask",
        sub_intent="OPEN_ENDED",
        feedback_signal=None,
        normalized_query="things to do tonight",
        response_text="You can check the channel area and local venues.",
    )
    _seed_log(
        days_ago=1,
        mode="ask",
        sub_intent="OPEN_ENDED",
        tier_used="1",
        feedback_signal="negative",
        normalized_query="tier1 row should not count",
        response_text="Tier 1 row.",
    )

    r = client.get("/admin/feedback?window=7d")
    assert r.status_code == 200
    body = r.text
    assert "OPEN_ENDED" in body
    assert "<td>3</td>" in body  # total tier3 rows in group
    assert "<td>1</td>" in body  # positive
    assert "<td>1</td>" in body  # negative
    assert "66.7%" in body  # feedback_rate = 2/3
    assert "50.0%" in body  # positive_rate = 1/2
    assert "best places to eat with kids" in body
    assert neg_id in body
    assert "tier1 row should not count" not in body


def test_feedback_window_filters_and_invalid_fallback(client: TestClient) -> None:
    _clear_chat_logs()
    _login(client)
    _seed_log(days_ago=2, sub_intent="RECENT_2D", feedback_signal=None)
    _seed_log(days_ago=10, sub_intent="RECENT_10D", feedback_signal="positive")
    _seed_log(days_ago=40, sub_intent="OLD_40D", feedback_signal="negative")

    r7 = client.get("/admin/feedback?window=7d")
    assert r7.status_code == 200
    s7 = r7.text.split("<h2>Recent negatives (latest 25)</h2>")[0]
    assert "RECENT_2D" in s7
    assert "RECENT_10D" not in s7
    assert "OLD_40D" not in s7

    r30 = client.get("/admin/feedback?window=30d")
    assert r30.status_code == 200
    s30 = r30.text.split("<h2>Recent negatives (latest 25)</h2>")[0]
    assert "RECENT_2D" in s30
    assert "RECENT_10D" in s30
    assert "OLD_40D" not in s30

    rall = client.get("/admin/feedback?window=all")
    assert rall.status_code == 200
    sall = rall.text.split("<h2>Recent negatives (latest 25)</h2>")[0]
    assert "RECENT_2D" in sall
    assert "RECENT_10D" in sall
    assert "OLD_40D" in sall

    rinvalid = client.get("/admin/feedback?window=banana")
    assert rinvalid.status_code == 200
    sinv = rinvalid.text.split("<h2>Recent negatives (latest 25)</h2>")[0]
    assert "RECENT_2D" in sinv
    assert "RECENT_10D" not in sinv
    assert "OLD_40D" not in sinv


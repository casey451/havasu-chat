"""C3 conversation restore — history endpoint, session rehydration, prompt block.

The in-memory session dict dies with the process; chat_logs already persists
one row per assistant turn. C3 reads that back three ways: GET
/api/chat/history for the frontend thread, rehydrate_session_from_logs for
pronoun follow-ups across restarts, and format_history_block for the Tier-3
prompt.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.chat.tier3_handler import (
    _HISTORY_QUERY_MAX,
    _HISTORY_RESPONSE_MAX,
    format_history_block,
)
from app.core.session import rehydrate_session_from_logs
from app.db.chat_logging import recent_turns_for_session
from app.db.database import SessionLocal
from app.db.models import ChatLog
from app.main import app

_SID_PREFIX = "c3-test-"


_T0 = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)


def _seed_turn(db, sid: str, n: int, *, role: str = "assistant", entity: str | None = None):
    row = ChatLog(
        id=str(uuid4()),
        session_id=sid,
        message=f"answer {n}",
        role=role,
        normalized_query=f"query {n}",
        entity_matched=entity,
        tier_used="3",
        # explicit, strictly increasing timestamps — identical defaults would
        # make the recency ordering nondeterministic on fast inserts
        created_at=_T0 + timedelta(seconds=n),
    )
    db.add(row)
    return row


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
        s.execute(delete(ChatLog).where(ChatLog.session_id.like(f"{_SID_PREFIX}%")))
        s.commit()
    finally:
        s.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --- GET /api/chat/history ----------------------------------------------------


def test_history_returns_last_turns_oldest_first(db, client) -> None:
    sid = f"{_SID_PREFIX}{uuid4().hex[:12]}"
    for n in range(8):
        _seed_turn(db, sid, n)
    db.commit()
    r = client.get("/api/chat/history", params={"session_id": sid, "limit": 6})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == sid
    queries = [t["query"] for t in body["turns"]]
    assert queries == [f"query {n}" for n in range(2, 8)]  # last 6, oldest first
    assert all(t["chat_log_id"] and t["response"] for t in body["turns"])


def test_history_excludes_other_sessions_and_user_rows(db, client) -> None:
    sid = f"{_SID_PREFIX}{uuid4().hex[:12]}"
    other = f"{_SID_PREFIX}{uuid4().hex[:12]}"
    _seed_turn(db, sid, 0)
    _seed_turn(db, sid, 1, role="user")
    _seed_turn(db, other, 2)
    db.commit()
    r = client.get("/api/chat/history", params={"session_id": sid})
    assert r.status_code == 200
    queries = [t["query"] for t in r.json()["turns"]]
    assert queries == ["query 0"]


def test_history_unknown_session_is_empty(client) -> None:
    r = client.get(
        "/api/chat/history", params={"session_id": f"{_SID_PREFIX}{uuid4().hex[:12]}"}
    )
    assert r.status_code == 200
    assert r.json()["turns"] == []


def test_history_validates_params(client) -> None:
    assert client.get("/api/chat/history").status_code == 422
    assert client.get("/api/chat/history", params={"session_id": "short"}).status_code == 422
    sid = f"{_SID_PREFIX}{uuid4().hex[:12]}"
    assert (
        client.get("/api/chat/history", params={"session_id": sid, "limit": 50}).status_code
        == 422
    )


# --- recent_turns_for_session ---------------------------------------------------


def test_recent_turns_shape(db) -> None:
    sid = f"{_SID_PREFIX}{uuid4().hex[:12]}"
    _seed_turn(db, sid, 0, entity="Mudshark Brewery")
    db.commit()
    turns = recent_turns_for_session(db, sid)
    assert len(turns) == 1
    t = turns[0]
    assert t["query"] == "query 0"
    assert t["response"] == "answer 0"
    assert t["entity_matched"] == "Mudshark Brewery"
    assert t["tier_used"] == "3"


# --- rehydrate_session_from_logs -------------------------------------------------


def test_rehydrate_restores_turn_count_and_prior_entity(db) -> None:
    sid = f"{_SID_PREFIX}{uuid4().hex[:12]}"
    _seed_turn(db, sid, 0, entity="Havasu Lanes")
    _seed_turn(db, sid, 1)
    _seed_turn(db, sid, 2)
    db.commit()
    session: dict = {}
    assert rehydrate_session_from_logs(db, sid, session) is True
    assert session["turn_number"] == 3
    pe = session["prior_entity"]
    assert pe["name"] == "Havasu Lanes"
    # the entity came from the oldest of the last three turns -> turn 1
    assert pe["turn_number"] == 1


def test_rehydrate_no_rows_is_noop(db) -> None:
    session: dict = {}
    assert rehydrate_session_from_logs(db, f"{_SID_PREFIX}{uuid4().hex[:12]}", session) is False
    assert "turn_number" not in session


# --- format_history_block --------------------------------------------------------


def test_history_block_formats_and_truncates() -> None:
    turns = [
        {"query": "q" * 500, "response": "r" * 500},
        {"query": "where is the best sushi", "response": "Try Sushi Ya."},
    ]
    block = format_history_block(turns)
    assert block is not None
    assert block.startswith("Conversation so far (oldest first):")
    lines = block.split("\n")
    assert lines[1] == "User: " + "q" * _HISTORY_QUERY_MAX
    assert lines[2] == "Hava: " + "r" * _HISTORY_RESPONSE_MAX
    assert lines[3] == "User: where is the best sushi"
    assert lines[4] == "Hava: Try Sushi Ya."


def test_history_block_empty_is_none() -> None:
    assert format_history_block([]) is None
    assert format_history_block([{"query": "", "response": ""}]) is None

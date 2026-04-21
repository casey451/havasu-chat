"""Tests for ``POST /api/chat/feedback`` (Phase 6.2.1)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import ChatLog
from app.main import app


def _make_chat_log() -> str:
    with SessionLocal() as db:
        row = ChatLog(session_id="fb-test", message="assistant turn", role="assistant")
        db.add(row)
        db.commit()
        db.refresh(row)
        return str(row.id)


def _feedback_signal(chat_log_id: str) -> str | None:
    with SessionLocal() as db:
        r = db.execute(select(ChatLog.feedback_signal).where(ChatLog.id == chat_log_id))
        return r.scalar_one()


def _delete_chat_log(chat_log_id: str) -> None:
    with SessionLocal() as db:
        row = db.get(ChatLog, chat_log_id)
        if row:
            db.delete(row)
            db.commit()


def test_feedback_positive_happy_path() -> None:
    cid = _make_chat_log()
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/chat/feedback",
                json={"chat_log_id": cid, "signal": "positive"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body == {"ok": True, "chat_log_id": cid, "signal": "positive"}
        assert _feedback_signal(cid) == "positive"
    finally:
        _delete_chat_log(cid)


def test_feedback_negative_happy_path() -> None:
    cid = _make_chat_log()
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/chat/feedback",
                json={"chat_log_id": cid, "signal": "negative"},
            )
        assert r.status_code == 200
        assert r.json()["signal"] == "negative"
        assert _feedback_signal(cid) == "negative"
    finally:
        _delete_chat_log(cid)


def test_feedback_overwrite_positive_then_negative() -> None:
    cid = _make_chat_log()
    try:
        with TestClient(app) as client:
            assert client.post(
                "/api/chat/feedback",
                json={"chat_log_id": cid, "signal": "positive"},
            ).status_code == 200
            r2 = client.post(
                "/api/chat/feedback",
                json={"chat_log_id": cid, "signal": "negative"},
            )
        assert r2.status_code == 200
        assert r2.json()["signal"] == "negative"
        assert _feedback_signal(cid) == "negative"
    finally:
        _delete_chat_log(cid)


def test_feedback_404_unknown_id() -> None:
    missing = str(uuid.uuid4())
    with TestClient(app) as client:
        r = client.post(
            "/api/chat/feedback",
            json={"chat_log_id": missing, "signal": "positive"},
        )
    assert r.status_code == 404
    assert r.json() == {"error": "chat_log_id not found"}


def test_feedback_422_invalid_signal() -> None:
    cid = _make_chat_log()
    try:
        with TestClient(app) as client:
            r = client.post(
                "/api/chat/feedback",
                json={"chat_log_id": cid, "signal": "maybe"},
            )
        assert r.status_code == 422
    finally:
        _delete_chat_log(cid)


def test_feedback_422_missing_chat_log_id() -> None:
    with TestClient(app) as client:
        r = client.post("/api/chat/feedback", json={"signal": "positive"})
    assert r.status_code == 422

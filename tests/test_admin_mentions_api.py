"""JSON admin API for LLM mentions (Phase 5.5)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.llm_mention_store import create_mention
from app.db.models import ChatLog
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


def _seed() -> int:
    with SessionLocal() as db:
        log = ChatLog(session_id="adm-api", message="About Api Test Diner here.", role="assistant")
        db.add(log)
        db.commit()
        db.refresh(log)
        m = create_mention(db, str(log.id), "Api Test Diner", "ctx")
        assert m is not None
        return m.id


def test_list_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/api/mentioned-entities")
    assert r.status_code == 401


def test_list_with_auth(client: TestClient) -> None:
    mid = _seed()
    _login(client)
    r = client.get("/admin/api/mentioned-entities?status=unreviewed")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(x["id"] == mid for x in data)
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        if row:
            log = db.get(ChatLog, row.chat_log_id)
            db.delete(row)
            if log:
                db.delete(log)
            db.commit()


def test_get_detail(client: TestClient) -> None:
    mid = _seed()
    _login(client)
    r = client.get(f"/admin/api/mentioned-entities/{mid}")
    assert r.status_code == 200
    assert r.json()["mentioned_name"] == "Api Test Diner"
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        if row:
            log = db.get(ChatLog, row.chat_log_id)
            db.delete(row)
            if log:
                db.delete(log)
            db.commit()


def test_post_dismiss(client: TestClient) -> None:
    mid = _seed()
    _login(client)
    r = client.post(
        f"/admin/api/mentioned-entities/{mid}/dismiss",
        json={"reason": "not_relevant"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        if row:
            log = db.get(ChatLog, row.chat_log_id)
            db.delete(row)
            if log:
                db.delete(log)
            db.commit()


def test_post_promote(client: TestClient) -> None:
    mid = _seed()
    _login(client)
    with patch("app.api.routes.admin_mentions.enrich_contribution"):
        r = client.post(
            f"/admin/api/mentioned-entities/{mid}/promote",
            json={
                "entity_type": "program",
                "submission_name": "Api Test Diner Program",
                "submission_url": "https://api-test-diner.example/prog",
                "submission_notes": "n",
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "promoted"
    assert body["promoted_to_contribution_id"] is not None
    with SessionLocal() as db:
        from app.db.models import Contribution, LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        assert row is not None
        c = db.get(Contribution, row.promoted_to_contribution_id)
        assert c is not None
        assert c.source == "llm_inferred"
        log = db.get(ChatLog, row.chat_log_id)
        db.delete(c)
        db.delete(row)
        if log:
            db.delete(log)
        db.commit()

"""HTML admin routes for LLM mentions (Phase 5.5)."""

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


def _seed_mention() -> int:
    with SessionLocal() as db:
        log = ChatLog(session_id="adm-html", message="Tier3 reply about Foo Bar Grill.", role="assistant")
        db.add(log)
        db.commit()
        db.refresh(log)
        m = create_mention(db, str(log.id), "Foo Bar Grill", "… Foo Bar Grill …")
        assert m is not None
        mid = m.id
        db.expunge(m)
        db.expunge(log)
        return mid


def test_list_authenticated(client: TestClient) -> None:
    mid = _seed_mention()
    client.cookies.clear()
    _login(client)
    r = client.get("/admin/mentioned-entities")
    assert r.status_code == 200
    assert "Foo Bar Grill" in r.text
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        if row:
            log = db.get(ChatLog, row.chat_log_id)
            db.delete(row)
            if log:
                db.delete(log)
            db.commit()


def test_list_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/mentioned-entities", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/admin/login")


def test_detail_ok(client: TestClient) -> None:
    mid = _seed_mention()
    _login(client)
    r = client.get(f"/admin/mentioned-entities/{mid}")
    assert r.status_code == 200
    assert "Foo Bar Grill" in r.text
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        if row:
            log = db.get(ChatLog, row.chat_log_id)
            db.delete(row)
            if log:
                db.delete(log)
            db.commit()


def test_promote_get_prefills_name(client: TestClient) -> None:
    mid = _seed_mention()
    _login(client)
    r = client.get(f"/admin/mentioned-entities/{mid}/promote")
    assert r.status_code == 200
    assert 'name="submission_name"' in r.text
    assert "Foo Bar Grill" in r.text
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        if row:
            log = db.get(ChatLog, row.chat_log_id)
            db.delete(row)
            if log:
                db.delete(log)
            db.commit()


def test_post_promote_creates_contribution(client: TestClient) -> None:
    mid = _seed_mention()
    _login(client)
    with patch("app.admin.mentions_html.enrich_contribution"):
        r = client.post(
            f"/admin/mentioned-entities/{mid}/promote",
            data={
                "entity_type": "provider",
                "submission_name": "Foo Bar Grill",
                "submission_url": "https://foo-bar-grill.example",
                "submission_category_hint": "food",
                "submission_notes": "from mention",
                "event_date": "",
            },
            follow_redirects=False,
        )
    assert r.status_code == 303
    assert "/admin/mentioned-entities" in (r.headers.get("location") or "")
    with SessionLocal() as db:
        from app.db.models import Contribution, LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        assert row is not None
        assert row.status == "promoted"
        assert row.promoted_to_contribution_id is not None
        c = db.get(Contribution, row.promoted_to_contribution_id)
        assert c is not None
        assert c.source == "llm_inferred"
        assert c.llm_source_chat_log_id == row.chat_log_id
        log = db.get(ChatLog, row.chat_log_id)
        db.delete(c)
        db.delete(row)
        if log:
            db.delete(log)
        db.commit()


def test_post_promote_provider_missing_url_validation(client: TestClient) -> None:
    mid = _seed_mention()
    _login(client)
    r = client.post(
        f"/admin/mentioned-entities/{mid}/promote",
        data={
            "entity_type": "provider",
            "submission_name": "No Url Place",
            "submission_url": "",
        },
    )
    assert r.status_code == 400
    assert "URL is required" in r.text
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        if row:
            log = db.get(ChatLog, row.chat_log_id)
            db.delete(row)
            if log:
                db.delete(log)
            db.commit()


def test_dismiss_get_renders(client: TestClient) -> None:
    mid = _seed_mention()
    _login(client)
    r = client.get(f"/admin/mentioned-entities/{mid}/dismiss")
    assert r.status_code == 200
    assert "dismissal_reason" in r.text or "Dismiss" in r.text
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        if row:
            log = db.get(ChatLog, row.chat_log_id)
            db.delete(row)
            if log:
                db.delete(log)
            db.commit()


def test_post_dismiss_redirects(client: TestClient) -> None:
    mid = _seed_mention()
    _login(client)
    r = client.post(
        f"/admin/mentioned-entities/{mid}/dismiss",
        data={"dismissal_reason": "noise"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with SessionLocal() as db:
        from app.db.models import LlmMentionedEntity

        row = db.get(LlmMentionedEntity, mid)
        assert row is not None
        assert row.status == "dismissed"
        log = db.get(ChatLog, row.chat_log_id)
        db.delete(row)
        if log:
            db.delete(log)
        db.commit()

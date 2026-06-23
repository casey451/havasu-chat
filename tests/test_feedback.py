"""P5 feedback channel — DB-backed dual-write (row + mocked Resend email), the
public form, the phantom-button removal from privacy/terms, and the admin queue.

The email sender is mocked everywhere (no Resend key needed): we assert the row
is always persisted (source of truth) and that the operator forward is attempted
with the right recipient/subject when ``FEEDBACK_NOTIFY_EMAIL`` is set.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin.auth import COOKIE_NAME, sign_admin_cookie
from app.admin_portal.audit_models import PortalBase
from app.admin_portal.router import portal_router
from app.db.database import SessionLocal, get_db
from app.db.models import Base, Feedback
from app.feedback import store
from app.main import app

# --------------------------------------------------------------------------- #
# Dual-write: a submission persists a row AND forwards one email.
# --------------------------------------------------------------------------- #


def test_create_feedback_persists_row() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        row = store.create_feedback(
            db,
            kind="wrong_info",
            message=f"hours are wrong {suf}",
            target_type="provider",
            target_ref="some-biz",
            email="me@example.com",
        )
        rid = row.id
        try:
            fetched = db.get(Feedback, rid)
            assert fetched is not None
            assert fetched.kind == "wrong_info"
            assert fetched.status == "new"
            assert fetched.target_type == "provider"
            assert fetched.email == "me@example.com"
        finally:
            db.execute(delete(Feedback).where(Feedback.id == rid))
            db.commit()


def test_notify_feedback_calls_sender_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("FEEDBACK_NOTIFY_EMAIL", "casey@example.com")
    sent: list[dict] = []
    monkeypatch.setattr(
        store,
        "send_alert_email",
        lambda **kw: sent.append(kw),
    )
    with SessionLocal() as db:
        row = store.create_feedback(db, kind="bug", message="broken link")
        rid = row.id
        try:
            attempted = store.notify_feedback(row)
            assert attempted is True
            assert len(sent) == 1
            assert sent[0]["to_email"] == "casey@example.com"
            assert f"#{rid}" in sent[0]["subject"]
            assert "broken link" in sent[0]["text_body"]
        finally:
            db.execute(delete(Feedback).where(Feedback.id == rid))
            db.commit()


def test_notify_feedback_noop_without_recipient(monkeypatch) -> None:
    monkeypatch.delenv("FEEDBACK_NOTIFY_EMAIL", raising=False)
    called = []
    monkeypatch.setattr(store, "send_alert_email", lambda **kw: called.append(kw))
    with SessionLocal() as db:
        row = store.create_feedback(db, kind="general", message="hi")
        rid = row.id
        try:
            assert store.notify_feedback(row) is False
            assert called == []  # row saved, no send attempted
        finally:
            db.execute(delete(Feedback).where(Feedback.id == rid))
            db.commit()


def test_notify_swallows_send_failure(monkeypatch) -> None:
    monkeypatch.setenv("FEEDBACK_NOTIFY_EMAIL", "casey@example.com")

    def _boom(**kw):
        raise RuntimeError("resend down")

    monkeypatch.setattr(store, "send_alert_email", _boom)
    with SessionLocal() as db:
        row = store.create_feedback(db, kind="general", message="hi")
        rid = row.id
        try:
            # A send failure must not raise — the row is already the source of truth.
            assert store.notify_feedback(row) is True
        finally:
            db.execute(delete(Feedback).where(Feedback.id == rid))
            db.commit()


# --------------------------------------------------------------------------- #
# Public form (GET + POST against the real app).
# --------------------------------------------------------------------------- #


def test_feedback_form_renders() -> None:
    with TestClient(app) as c:
        r = c.get("/feedback?type=wrong_info&target_type=provider&ref=acme&name=Acme")
        assert r.status_code == 200
        assert "Send feedback" in r.text
        assert "Acme" in r.text


def test_post_feedback_writes_row_and_forwards(monkeypatch) -> None:
    monkeypatch.setenv("FEEDBACK_NOTIFY_EMAIL", "casey@example.com")
    sent: list[dict] = []
    monkeypatch.setattr(store, "send_alert_email", lambda **kw: sent.append(kw))
    marker = f"missing hours {uuid.uuid4().hex[:8]}"
    with TestClient(app) as c:
        r = c.post(
            "/feedback",
            data={
                "message": marker,
                "kind": "missing_info",
                "target_type": "provider",
                "target_ref": "acme",
                "email": "user@example.com",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == "/feedback?submitted=1"
    # Row persisted...
    with SessionLocal() as db:
        rows = db.scalars(select(Feedback).where(Feedback.message == marker)).all()
        assert len(rows) == 1
        rid = rows[0].id
        try:
            assert rows[0].kind == "missing_info"
            # ...and the background forward fired (TestClient runs background tasks).
            assert len(sent) == 1
            assert sent[0]["to_email"] == "casey@example.com"
        finally:
            db.execute(delete(Feedback).where(Feedback.id == rid))
            db.commit()


def test_post_feedback_empty_message_400() -> None:
    with TestClient(app) as c:
        r = c.post("/feedback", data={"message": "   "})
        assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Privacy/terms no longer reference the phantom "feedback button".
# --------------------------------------------------------------------------- #


def test_privacy_and_terms_point_at_real_feedback_path() -> None:
    with TestClient(app) as c:
        privacy = c.get("/privacy").text.lower()
        terms = c.get("/terms").text.lower()
    for body in (privacy, terms):
        assert "feedback button" not in body
        assert "feedback control in the chat" not in body
        assert "/feedback" in body


# --------------------------------------------------------------------------- #
# Admin queue (throwaway portal app, like the smoke test).
# --------------------------------------------------------------------------- #


@pytest.fixture()
def portal_client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    PortalBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    portal_app = FastAPI()
    portal_app.include_router(portal_router)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    portal_app.dependency_overrides[get_db] = override_get_db
    with Session() as db:
        db.add(Feedback(kind="wrong_info", message="hours off", status="new"))
        db.commit()

    c = TestClient(portal_app)
    c.cookies.set(COOKIE_NAME, sign_admin_cookie())
    yield c


def test_admin_feedback_queue_lists_and_triages(portal_client):
    page = portal_client.get("/admin/portal/feedback")
    assert page.status_code == 200
    assert "hours off" in page.text

    import re

    fid = re.search(r"/admin/portal/feedback/(\d+)/status", page.text)
    assert fid, "feedback status form not found"
    feedback_id = fid.group(1)

    resp = portal_client.post(
        f"/admin/portal/feedback/{feedback_id}/status",
        data={"new_status": "resolved", "return_status": "new"},
    )
    assert resp.status_code == 200  # after redirect

    # Now resolved: gone from the default "new" view, present under resolved.
    new_view = portal_client.get("/admin/portal/feedback?status=new")
    assert "hours off" not in new_view.text
    resolved_view = portal_client.get("/admin/portal/feedback?status=resolved")
    assert "hours off" in resolved_view.text

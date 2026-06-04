"""WP-2 (Chat surface) -- template + feedback-route smoke tests.

These pin the WP-2 contract on the /chat surface:

- ``chat_cards.css`` is wired (carries all new card / feedback / clearance
  rules; if the <link> is dropped, icons/photos lose their bounds).
- The SPONSORED loading interstitial markup is gone (DL-13).
- The composer disclaimer ships and the composer input is labelled (F1 / a11y).
- The loading overlay no longer carries the aria-live + aria-hidden
  contradiction (the live region must not also be hidden).
- ``POST /api/chat/feedback`` is wired and surfaces ``chat_log_id`` so the
  ported thumbs handler in chat-new.js has something to key on (A4 / DL-1).

JS behavior (thumbs/Save/Share handlers, card separators) has no test harness
in this repo and is verified manually -- see the PR body.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import ChatLog
from app.main import app


def test_chat_loads_chat_cards_css() -> None:
    """/chat references the WP-2 stylesheet that carries the new card rules."""
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    assert "/static/styles/chat_cards.css" in r.text


def test_chat_drops_sponsored_interstitial_markup() -> None:
    """DL-13: the hardcoded SPONSORED loading interstitial markup is removed."""
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    assert "SPONSORED" not in r.text
    # The sponsor "fact" line and its hook are gone too.
    assert 'id="ll-loading-fact"' not in r.text


def test_chat_composer_disclaimer_and_label() -> None:
    """F1 + a11y: composer carries the mistakes disclaimer and an aria label."""
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    assert "confirm hours by phone" in r.text
    assert 'aria-label="Ask Hava"' in r.text


def test_chat_overlay_has_no_aria_hidden_contradiction() -> None:
    """The loading overlay is a live region and must NOT also be aria-hidden."""
    with TestClient(app) as client:
        r = client.get("/chat")
    assert r.status_code == 200
    # Locate the overlay element's opening tag and assert it is not hidden.
    marker = 'id="ll-loading-overlay"'
    assert marker in r.text
    start = r.text.index(marker)
    open_tag = r.text[start - 80 : r.text.index(">", start) + 1]
    assert "aria-live" in open_tag
    assert "aria-hidden" not in open_tag


def test_feedback_route_surfaces_chat_log_id() -> None:
    """A4/DL-1: POST /api/chat/feedback is wired and echoes chat_log_id.

    The ported thumbs handler in chat-new.js keys feedback on the
    ``chat_log_id`` the /api/chat response returns, so the round-trip the JS
    depends on must hold.
    """
    with SessionLocal() as db:
        row = ChatLog(session_id="wp2-fb", message="assistant turn", role="assistant")
        db.add(row)
        db.commit()
        db.refresh(row)
        cid = str(row.id)
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/feedback",
                json={"chat_log_id": cid, "signal": "positive"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["chat_log_id"] == cid
        assert body["signal"] == "positive"
    finally:
        with SessionLocal() as db:
            obj = db.get(ChatLog, cid)
            if obj:
                db.delete(obj)
                db.commit()

"""Phase A3 — weekend digest builder, saved-venue surfacing, render, opt-in."""

from __future__ import annotations

from datetime import date, time, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.entity_dual_write import create_event_and_entity
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import (
    AuthSession,
    DigestSubscription,
    Entity,
    Event,
    Provider,
    User,
    UserFavorite,
)
from app.digest.builder import build_weekend_digest
from app.digest.render import build_render_digest, render_weekend_digest
from app.events.queries import event_window_for_chip
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _capture_send(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    toks: list[str] = []

    def _fake(email: str, tok: str, *, next_path: str | None = None) -> None:
        toks.append(tok)

    monkeypatch.setattr("app.auth.email_sender.send_magic_link", _fake)
    return toks


def _login_email(client: TestClient, monkeypatch: pytest.MonkeyPatch, email: str) -> None:
    toks = _capture_send(monkeypatch)
    client.post("/api/auth/request-link", data={"email": email})
    client.get(f"/auth/callback?token={toks[0]}", follow_redirects=False)


def _next_weekend_saturday(today: date) -> date:
    start, end = event_window_for_chip("this-weekend", today=today)
    # Saturday is start+1 when start is Friday.
    sat = start + timedelta(days=1)
    if sat > end:
        sat = start
    return sat


def _make_venue_with_event(
    db, *, suf: str, on_date: date, title: str
) -> tuple[str, str, str]:
    """Create a venue Entity+Provider and an event hosted by that provider.

    Returns (venue_entity_id, provider_id, event_id).
    """
    venue_eid = str(uuid4())
    db.add(
        Entity(
            id=venue_eid,
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"digest-venue-{suf}",
            name=f"Digest Venue {suf}",
            source="test-digest",
        )
    )
    prov = Provider(
        provider_name=f"Digest Venue {suf}",
        category="entertainment",
        source="test-digest",
        slug=f"digest-prov-{suf}",
        draft=False,
        is_active=True,
        verified=False,
        entity_id=venue_eid,
    )
    db.add(prov)
    db.flush()
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on_date,
        start_time=time(18, 0),
        location_name=f"Digest Venue {suf}",
        location_normalized=f"digest venue {suf}",
        description="Test event",
        event_url="https://example.com/e",
        status="live",
        source="test-digest",
        is_recurring=False,
        provider_id=prov.id,
    )
    db.add(ev)
    create_event_and_entity(db, ev)
    db.flush()
    return venue_eid, prov.id, ev.id


def _cleanup(emails: list[str], entity_ids: list[str], event_ids: list[str]) -> None:
    with SessionLocal() as db:
        for evid in event_ids:
            db.query(Event).filter_by(id=evid).delete()
        for em in emails:
            u = db.query(User).filter(User.email == em).first()
            if u:
                db.query(UserFavorite).filter_by(user_id=u.id).delete()
                db.query(DigestSubscription).filter_by(user_id=u.id).delete()
                db.query(AuthSession).filter_by(user_id=u.id).delete()
                db.delete(u)
        for eid in entity_ids:
            db.query(Provider).filter_by(entity_id=eid).delete()
            db.query(Event).filter_by(entity_id=eid).delete()
        db.commit()
        # Event entities created by dual-write are cleaned by event delete cascade
        # is not guaranteed; drop any orphan event entities by id is skipped (the
        # leaked event entity has a distinct uuid). Entities we explicitly made:
        with SessionLocal() as db2:
            for eid in entity_ids:
                db2.query(Entity).filter_by(id=eid).delete()
            db2.commit()


def test_builder_includes_weekend_event() -> None:
    suf = uuid4().hex[:8]
    today = date(2026, 6, 1)  # a Monday
    sat = _next_weekend_saturday(today)
    venue_eid = None
    evid = None
    user_id = None
    try:
        with SessionLocal() as db:
            venue_eid, _pid, evid = _make_venue_with_event(
                db, suf=suf, on_date=sat, title=f"Weekend Show {suf}"
            )
            u = User(id=str(uuid4()), email=f"dig-{suf}@example.com")
            db.add(u)
            db.commit()
            user_id = u.id
            digest = build_weekend_digest(db, user_id, today=today)
        titles = {e.title for e in digest.weekend_events}
        assert f"Weekend Show {suf}" in titles
        assert digest.has_content is True
    finally:
        _cleanup(
            [f"dig-{suf}@example.com"],
            [venue_eid] if venue_eid else [],
            [evid] if evid else [],
        )


def test_builder_saved_venue_filter() -> None:
    suf = uuid4().hex[:8]
    today = date(2026, 6, 1)
    sat = _next_weekend_saturday(today)
    venue_eid = None
    evid = None
    user_id = None
    try:
        with SessionLocal() as db:
            venue_eid, _pid, evid = _make_venue_with_event(
                db, suf=suf, on_date=sat, title=f"Saved Venue Gig {suf}"
            )
            u = User(id=str(uuid4()), email=f"dsv-{suf}@example.com")
            db.add(u)
            db.flush()
            user_id = u.id
            # Before following: no saved-venue events.
            d0 = build_weekend_digest(db, user_id, today=today)
            assert d0.saved_venue_events == []
            # Follow the venue.
            db.add(UserFavorite(user_id=user_id, entity_id=venue_eid))
            db.commit()
            d1 = build_weekend_digest(db, user_id, today=today)
        saved_titles = {e.title for e in d1.saved_venue_events}
        assert f"Saved Venue Gig {suf}" in saved_titles
        assert d1.has_saved_venue_events is True
    finally:
        _cleanup(
            [f"dsv-{suf}@example.com"],
            [venue_eid] if venue_eid else [],
            [evid] if evid else [],
        )


def test_builder_empty_state_is_honest() -> None:
    suf = uuid4().hex[:8]
    # Far-future weekend with no events for this user/venue.
    today = date(2030, 1, 7)  # Monday
    user_id = None
    try:
        with SessionLocal() as db:
            u = User(id=str(uuid4()), email=f"dempty-{suf}@example.com")
            db.add(u)
            db.commit()
            user_id = u.id
            digest = build_weekend_digest(db, user_id, today=today)
        assert digest.saved_venue_events == []
        # has_content reflects only real data (may be False if no city events).
        assert isinstance(digest.has_content, bool)
        subject, html_body, text_body = render_weekend_digest(
            digest, digest_url="https://example.com/account/digest"
        )
        if not digest.has_content:
            assert "Nothing on the Lake Havasu calendar" in text_body
            assert "Nothing on the Lake Havasu calendar" in html_body
    finally:
        _cleanup([f"dempty-{suf}@example.com"], [], [])


def test_render_dry_run_does_not_send(monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid4().hex[:8]
    today = date(2026, 6, 1)
    sat = _next_weekend_saturday(today)
    venue_eid = None
    evid = None
    user_id = None
    sends: list[str] = []
    monkeypatch.setattr(
        "app.auth.email_sender.send_alert_email",
        lambda **kw: sends.append(kw.get("to_email", "")),
    )
    try:
        with SessionLocal() as db:
            venue_eid, _pid, evid = _make_venue_with_event(
                db, suf=suf, on_date=sat, title=f"DryRun Show {suf}"
            )
            u = User(id=str(uuid4()), email=f"ddry-{suf}@example.com")
            db.add(u)
            db.commit()
            user_id = u.id
            result = build_render_digest(
                db,
                user_id,
                to_email=f"ddry-{suf}@example.com",
                digest_url="https://example.com/account/digest",
                today=today,
                dry_run=True,
            )
        assert result.sent is False
        assert sends == []
        assert result.subject == "This weekend in Havasu"
        assert f"DryRun Show {suf}" in result.text_body
    finally:
        _cleanup(
            [f"ddry-{suf}@example.com"],
            [venue_eid] if venue_eid else [],
            [evid] if evid else [],
        )


def test_render_non_dry_run_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    suf = uuid4().hex[:8]
    today = date(2026, 6, 1)
    sat = _next_weekend_saturday(today)
    venue_eid = None
    evid = None
    user_id = None
    sends: list[str] = []
    monkeypatch.setattr(
        "app.auth.email_sender.send_alert_email",
        lambda **kw: sends.append(kw.get("to_email", "")),
    )
    try:
        with SessionLocal() as db:
            venue_eid, _pid, evid = _make_venue_with_event(
                db, suf=suf, on_date=sat, title=f"Send Show {suf}"
            )
            u = User(id=str(uuid4()), email=f"dsend-{suf}@example.com")
            db.add(u)
            db.commit()
            user_id = u.id
            result = build_render_digest(
                db,
                user_id,
                to_email=f"dsend-{suf}@example.com",
                digest_url="https://example.com/account/digest",
                today=today,
                dry_run=False,
            )
        assert result.sent is True
        assert sends == [f"dsend-{suf}@example.com"]
    finally:
        _cleanup(
            [f"dsend-{suf}@example.com"],
            [venue_eid] if venue_eid else [],
            [evid] if evid else [],
        )


def test_follow_and_optin_routes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suf = uuid4().hex[:8]
    email = f"droute-{suf}@example.com"
    venue_eid = str(uuid4())
    try:
        with SessionLocal() as db:
            db.add(
                Entity(
                    id=venue_eid,
                    entity_type=ENTITY_TYPE_COMMERCIAL,
                    slug=f"droute-venue-{suf}",
                    name=f"Route Venue {suf}",
                    source="test-digest",
                )
            )
            db.commit()
        # Anonymous is rejected.
        assert client.post("/api/venues/follow", json={"entity_id": venue_eid}).status_code == 401

        _login_email(client, monkeypatch, email)
        r = client.post("/api/venues/follow", json={"entity_id": venue_eid})
        assert r.status_code == 200
        assert r.json() == {"action": "added", "following": True}
        # Idempotent.
        r2 = client.post("/api/venues/follow", json={"entity_id": venue_eid})
        assert r2.json()["action"] == "exists"

        # Opt-in defaults to not-subscribed.
        assert client.get("/api/digest/subscription").json() == {"opted_in": False}
        assert client.post("/api/digest/subscription", json={"enabled": True}).json() == {
            "opted_in": True
        }
        assert client.get("/api/digest/subscription").json() == {"opted_in": True}
        assert client.post("/api/digest/subscription", json={"enabled": False}).json() == {
            "opted_in": False
        }

        r3 = client.post("/api/venues/unfollow", json={"entity_id": venue_eid})
        assert r3.json() == {"action": "removed", "following": False}
    finally:
        _cleanup([email], [venue_eid], [])


def test_follow_rejects_non_venue(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = f"dnv-{uuid4().hex[:8]}@example.com"
    _login_email(client, monkeypatch, email)
    r = client.post("/api/venues/follow", json={"entity_id": str(uuid4())})
    assert r.status_code == 404
    _cleanup([email], [], [])

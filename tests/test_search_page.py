"""WP-11 — ``GET /search`` keyword results page (DL-6 phase 2)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_EVENT
from app.db.models import Entity, Event, Provider
from app.main import app


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def _commercial_entity(*, name: str, slug: str) -> Entity:
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=slug,
        name=name,
        description=f"{name} description",
        source="test-search-page",
    )


def _event_entity(*, name: str) -> Entity:
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_EVENT,
        slug=f"ev-{uuid.uuid4().hex[:12]}",
        name=name,
        description=name,
        source="test-search-page",
    )


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_search_page_returns_200_with_provider_row(db: Session) -> None:
    suf = _suffix()
    mark = f"PipeFix {suf}"
    slug = f"pipefix-{suf}"
    ent = _commercial_entity(name=f"{mark} Plumbing Services", slug=slug)
    p = Provider(
        provider_name=ent.name,
        slug=slug,
        category="home_services",
        google_primary_category="plumber",
        phone="928-555-0142",
        address="123 Main St",
        source="test-search-page",
        draft=False,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": "plumber"})
    assert r.status_code == 200
    body = r.text
    # Provider row exposes name, link, and phone.
    assert mark in body
    assert f"/provider/{slug}" in body
    assert "928-555-0142" in body


def test_search_question_query_redirects_to_ai(db: Session) -> None:
    """F13: a question / NL query on /search routes straight to the AI concierge."""
    with TestClient(app) as client:
        r = client.get(
            "/search", params={"q": "is In-N-Out Burger open right now"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert r.headers["location"].startswith("/chat?q=")
    assert "nf=1" not in r.headers["location"]  # direct AI, not the 0-result note


def test_search_zero_result_renders_serp_with_escalation_and_logs(db: Session) -> None:
    """WS9b: a real keyword query that matches nothing no longer 302s to /chat —
    it renders the SERP with an 'Ask Hava' escalation card, and the miss is
    logged to QueryLog (result_count == 0) for the coverage backlog."""
    from sqlalchemy import select

    from app.db.models import QueryLog

    nomatch = f"zzqqx{_suffix()}plumberless"
    with TestClient(app) as client:
        r = client.get("/search", params={"q": nomatch}, follow_redirects=False)
    assert r.status_code == 200  # no redirect — the SERP owns the miss
    body = r.text
    assert "No exact matches" in body
    assert f"/chat?q={nomatch}" in body  # escalation card links to chat
    assert "Businesses" not in body  # no result sections rendered
    # The zero-result miss is captured for the demand dashboard.
    logged = db.scalars(
        select(QueryLog).where(QueryLog.normalized_intent == nomatch.lower())
    ).all()
    assert logged, "zero-result query should be logged"
    assert all(row.result_count == 0 for row in logged)


def test_search_keyword_hit_still_renders_results_no_redirect(db: Session) -> None:
    """F13 regression guard: a keyword-class query WITH matches renders the
    keyword page (no AI redirect) — working lookups are untouched."""
    suf = _suffix()
    mark = f"Pizza Palace {suf}"
    slug = f"pizza-palace-{suf}"
    ent = _commercial_entity(name=mark, slug=slug)
    p = Provider(
        provider_name=mark, slug=slug, category="eat_and_drink",
        source="test-search-page", draft=False, is_active=True, entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()
    with TestClient(app) as client:
        r = client.get("/search", params={"q": "pizza"}, follow_redirects=False)
    assert r.status_code == 200  # keyword page, not a 302 to /chat
    assert mark in r.text


def test_chat_q_serves_ai_scaffold_for_family_card(db: Session) -> None:
    """F13: the Family-card style /chat?q= link lands on the AI scaffold (which
    fires the turn from ?q on load), not the keyword /search page."""
    with TestClient(app) as client:
        r = client.get(
            "/chat", params={"q": "swimming and splash pads"}, follow_redirects=False
        )
    assert r.status_code == 200
    assert 'id="thread"' in r.text  # the chat scaffold, not a redirect


def test_like_escape_neutralizes_wildcards() -> None:
    """F13: a query's LIKE wildcards are escaped so it matches as literal text."""
    from app.search.routes import _like_escape

    assert _like_escape("In-N-Out") == "In-N-Out"  # hyphens are not wildcards
    assert _like_escape("50% off") == "50\\% off"
    assert _like_escape("a_b") == "a\\_b"
    assert _like_escape("c\\d") == "c\\\\d"


def test_search_page_matches_hyphenated_business_name(db: Session) -> None:
    """F13: a punctuated proper-noun query ("In-N-Out") finds the business by
    name. It used to return nothing on Postgres because to_tsquery dropped the
    hyphenated token; /search now also matches the name as a substring."""
    suf = _suffix()
    mark = f"Zorp-Q-Blat {suf}"
    slug = f"zorp-q-blat-{suf}"
    ent = _commercial_entity(name=mark, slug=slug)
    p = Provider(
        provider_name=mark, slug=slug, category="eat_and_drink",
        source="test-search-page", draft=False, is_active=True, entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": "Zorp-Q-Blat"})
    assert r.status_code == 200
    assert mark in r.text
    assert f"/provider/{slug}" in r.text


def test_search_page_event_row_links_to_permalink(db: Session) -> None:
    suf = _suffix()
    mark = f"LanternFest{suf}"
    ent = _event_entity(name=mark)
    ev = Event(
        id=str(uuid.uuid4()),
        title=f"{mark} on the Channel",
        normalized_title=mark.lower(),
        date=dt.date(2030, 7, 4),
        start_time=dt.time(18, 0),
        location_name="London Bridge",
        location_normalized="london bridge",
        description="A lantern festival.",
        status="live",
        source="test-search-page",
        entity_id=ent.id,
    )
    db.add_all([ent, ev])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": mark})
    assert r.status_code == 200
    body = r.text
    assert mark in body
    assert f"/events/{ev.id}" in body
    assert "London Bridge" in body


def test_search_page_blank_q_shows_empty_state() -> None:
    with TestClient(app) as client:
        r = client.get("/search", params={"q": "   "})
    assert r.status_code == 200
    # Empty state references Ask Hava and does not render result sections.
    assert "/chat" in r.text
    assert "Businesses" not in r.text


def test_search_page_no_match_renders_escalation_card_not_redirect() -> None:
    # WS9b: a non-empty keyword query with zero matches renders the SERP with an
    # Ask Hava escalation card + popular-category suggestions — never a 302 to a
    # dead end (the audit's "No exact matches" redirect is gone).
    with TestClient(app) as client:
        r = client.get(
            "/search", params={"q": f"zzqqxx{_suffix()}nomatch"}, follow_redirects=False
        )
    assert r.status_code == 200
    body = r.text
    assert "No exact matches" in body
    assert 'class="srch-suggest"' in body  # popular-category suggestion chips
    assert "Eat &amp; Drink" in body


def test_search_page_does_not_leak_internal_fields(db: Session) -> None:
    suf = _suffix()
    slug = f"leakcheck-{suf}"
    ent = _commercial_entity(name=f"LeakCheck {suf} Cafe", slug=slug)
    p = Provider(
        provider_name=ent.name,
        slug=slug,
        category="food_drink",
        google_primary_category="cafe",
        phone="928-555-0199",
        source="test-search-page",
        draft=False,
        is_active=True,
        entity_id=ent.id,
        embedding=[0.1, 0.2, 0.3],
        raw_enrichment_json={"secret": "do-not-leak"},
        attributes={"hero_pin_photo_url": "https://example.com/h.jpg"},
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": "cafe"})
    assert r.status_code == 200
    body = r.text
    assert "LeakCheck" in body
    assert "do-not-leak" not in body
    assert "raw_enrichment_json" not in body
    assert ent.id not in body  # internal entity id not exposed


def test_search_page_excludes_draft_and_inactive(db: Session) -> None:
    suf = _suffix()
    mark = f"DraftDojo{suf}"
    ent = _commercial_entity(name=f"{mark} Karate", slug=f"draftdojo-{suf}")
    p = Provider(
        provider_name=ent.name,
        slug=f"draftdojo-{suf}",
        category="misc",
        source="test-search-page",
        draft=True,
        is_active=True,
        entity_id=ent.id,
    )
    db.add_all([ent, p])
    db.commit()

    with TestClient(app) as client:
        r = client.get("/search", params={"q": mark}, follow_redirects=False)
    # The draft provider is excluded, so the keyword search matches nothing and
    # renders the no-match SERP (WS9b: no redirect). The draft's slug/name must
    # not leak into the page; a leaked row would render a Businesses section.
    assert r.status_code == 200
    body = r.text
    assert "No exact matches" in body
    assert f"draftdojo-{suf}" not in body
    assert "Businesses" not in body


def test_home_has_single_search_form_to_chat() -> None:
    # Workstream E (search consolidation): the home hero is ONE search box wired
    # to the 3-tier /chat router. The old secondary directory form
    # (class="header-search" action="/search") and its "Ask Hava instead"
    # (/chat?q=) CTA were removed — /chat now serves directory lookups too.
    with TestClient(app) as client:
        h = client.get("/home")
    assert h.status_code == 200
    assert h.text.count('id="rd-search"') == 1
    assert 'action="/chat"' in h.text
    # The removed second directory form / "Ask Hava instead" CTA must not reappear.
    # (A /chat?q= urlTemplate legitimately remains in the SearchAction JSON-LD;
    # the guard targets the old visible secondary form, not the schema.)
    assert 'action="/search"' not in h.text
    assert 'class="header-search"' not in h.text

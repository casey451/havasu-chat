"""v54 Track B — analytics_events table + helper + emit sites.

Mirrors the test discipline in ``tests/test_sponsor_click_route.py`` and
``tests/test_sponsor_store_tiers.py`` — fresh per-test ``_wipe``, the
session-scoped SQLite fixture from ``conftest.py``, and the
``follow_redirects=False`` TestClient pattern.

Covers:

1. ``record_event`` writes a row with all fields populated.
2. ``record_event`` swallows DB errors silently (analytics must never
   break the request).
3. ``active_spotlights`` emits one impression event per row, with
   ``ranking_score`` matching ``Sponsor.weight``.
4. ``GET /sponsor/click?slot=spotlight`` emits a
   ``home.spotlight.click`` row with ``ranking_score`` matching weight.
5. ``build_card_row`` emits one ``chat.card_row.impression`` per render
   with ``provider_count`` in the payload.
6. ``build_single_business_card`` emits one ``chat.single_card.open``
   per render with ``provider_id`` populated.
7. End-to-end: the ``ranking_score`` on the analytics row matches the
   ``Sponsor.weight`` value at emit time (defensive against a future
   refactor that loses the read at the source).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.analytics import record_event
from app.chat.component_builders import (
    SLOT_ORIGIN_TIER2_CARD_ROW,
    SLOT_ORIGIN_TIER2_SINGLE_CARD,
    build_card_row,
    build_single_business_card,
)
from app.chat.intent_classifier import IntentResult
from app.chat.tier2_schema import Tier2Filters
from app.db.database import SessionLocal
from app.db.models import AdSlot, AnalyticsEvent, Sponsor, SponsorStatus
from app.home import sponsor_store
from app.main import app


def _wipe(db: Session) -> None:
    db.query(AnalyticsEvent).delete()
    db.query(Sponsor).delete()
    db.commit()


def _add_sponsor(
    db: Session,
    *,
    slot: str = AdSlot.SPOTLIGHT.value,
    status: str = SponsorStatus.APPROVED.value,
    active: bool = True,
    name: str = "Acme",
    weight: int = 5,
    cta_url: str = "https://example.com/landing",
) -> Sponsor:
    sp = Sponsor(
        name=name,
        slot=slot,
        status=status,
        active=active,
        cta_url=cta_url,
        weight=weight,
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return sp


@pytest.fixture
def db() -> Session:
    with SessionLocal() as session:
        _wipe(session)
        yield session
        _wipe(session)


@pytest.fixture
def client() -> TestClient:
    # follow_redirects=False so /sponsor/click 302 is asserted directly
    # instead of chasing the redirect onto an unreachable external URL.
    return TestClient(app, follow_redirects=False)


def _events(db: Session, *, event_name: str | None = None) -> list[AnalyticsEvent]:
    q = db.query(AnalyticsEvent)
    if event_name is not None:
        q = q.filter(AnalyticsEvent.event_name == event_name)
    return q.order_by(AnalyticsEvent.created_at.asc()).all()


# 1. record_event basic insert ------------------------------------------------


def test_record_event_inserts_row(db: Session) -> None:
    record_event(
        db,
        "home.spotlight.impression",
        slot="spotlight",
        sponsor_id="sponsor-abc",
        provider_id="provider-xyz",
        ranking_score=7,
        slot_origin="some_surface",
        payload={"k": "v"},
    )
    rows = _events(db)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_name == "home.spotlight.impression"
    assert row.slot == "spotlight"
    # FK is SET NULL on delete; the values themselves stick at insert time.
    assert row.ranking_score == 7
    assert row.slot_origin == "some_surface"
    assert row.payload_json == {"k": "v"}
    assert row.created_at is not None


# 2. record_event swallows DB errors -----------------------------------------


def test_record_event_handles_db_failure_silently(db: Session) -> None:
    """A db.execute() that raises must not propagate out of record_event."""
    with patch.object(db, "execute", side_effect=RuntimeError("boom")):
        # Must return None, must not raise. ``record_event`` is best-effort.
        result = record_event(
            db,
            "home.spotlight.impression",
            slot="spotlight",
            sponsor_id="sponsor-abc",
        )
    assert result is None
    # Nothing was written either — the simulated failure happened mid-INSERT.
    assert _events(db, event_name="home.spotlight.impression") == []


# 3. active_spotlights emits impressions --------------------------------------


def test_spotlight_impression_event_fired_on_active_spotlights(db: Session) -> None:
    a = _add_sponsor(db, name="alpha", weight=10)
    b = _add_sponsor(db, name="beta", weight=3)
    sponsor_store.active_spotlights(db)
    impressions = _events(db, event_name="home.spotlight.impression")
    sponsor_ids = {ev.sponsor_id for ev in impressions}
    assert sponsor_ids == {a.id, b.id}
    # ranking_score should mirror Sponsor.weight at emit time
    by_id = {ev.sponsor_id: ev for ev in impressions}
    assert by_id[a.id].ranking_score == 10
    assert by_id[b.id].ranking_score == 3
    assert all(ev.slot == AdSlot.SPOTLIGHT.value for ev in impressions)


# 3b. other tiers emit impressions (v55 Track B follow-up) --------------------


def test_marquee_impression_event_fired_on_active_marquee(db: Session) -> None:
    m = _add_sponsor(db, name="marq", slot=AdSlot.MARQUEE.value, weight=6)
    sponsor_store.active_marquee(db)
    impressions = _events(db, event_name="home.marquee.impression")
    assert len(impressions) == 1
    ev = impressions[0]
    assert ev.sponsor_id == m.id
    assert ev.slot == AdSlot.MARQUEE.value
    assert ev.ranking_score == 6


def test_promoted_impression_event_fired_on_active_promoted(db: Session) -> None:
    p = _add_sponsor(db, name="promo", slot=AdSlot.PROMOTED.value, weight=4)
    sponsor_store.active_promoted(db)
    impressions = _events(db, event_name="home.promoted.impression")
    assert len(impressions) == 1
    ev = impressions[0]
    assert ev.sponsor_id == p.id
    assert ev.slot == AdSlot.PROMOTED.value
    assert ev.ranking_score == 4


def test_supporter_impression_event_fired_per_supporter(db: Session) -> None:
    a = _add_sponsor(db, name="sup-a", slot=AdSlot.SUPPORTER.value, weight=9)
    b = _add_sponsor(db, name="sup-b", slot=AdSlot.SUPPORTER.value, weight=1)
    sponsor_store.supporters(db)
    impressions = _events(db, event_name="home.supporter.impression")
    assert {ev.sponsor_id for ev in impressions} == {a.id, b.id}
    by_id = {ev.sponsor_id: ev for ev in impressions}
    assert by_id[a.id].ranking_score == 9
    assert by_id[b.id].ranking_score == 1
    assert all(ev.slot == AdSlot.SUPPORTER.value for ev in impressions)


# 4. /sponsor/click spotlight emits home.spotlight.click ----------------------


def test_sponsor_click_emits_spotlight_click_event(client: TestClient, db: Session) -> None:
    sp = _add_sponsor(db, name="click-me", slot=AdSlot.SPOTLIGHT.value, weight=8)
    r = client.get(
        "/sponsor/click",
        params={"id": sp.id, "slot": AdSlot.SPOTLIGHT.value},
    )
    assert r.status_code == 302
    spotlight_clicks = _events(db, event_name="home.spotlight.click")
    assert len(spotlight_clicks) == 1
    ev = spotlight_clicks[0]
    assert ev.sponsor_id == sp.id
    assert ev.slot == AdSlot.SPOTLIGHT.value
    assert ev.ranking_score == 8
    # Generic home.sponsor.click also fires for cross-tier roll-ups.
    generic_clicks = _events(db, event_name="home.sponsor.click")
    assert len(generic_clicks) == 1
    assert generic_clicks[0].sponsor_id == sp.id


def test_sponsor_click_non_spotlight_skips_spotlight_event(client: TestClient, db: Session) -> None:
    """A marquee click should NOT emit home.spotlight.click — only the generic event."""
    sp = _add_sponsor(db, name="marq", slot=AdSlot.MARQUEE.value, weight=2)
    r = client.get(
        "/sponsor/click",
        params={"id": sp.id, "slot": AdSlot.MARQUEE.value},
    )
    assert r.status_code == 302
    assert _events(db, event_name="home.spotlight.click") == []
    generic = _events(db, event_name="home.sponsor.click")
    assert len(generic) == 1
    assert generic[0].slot == AdSlot.MARQUEE.value


# 5. build_card_row emits chat.card_row.impression ---------------------------


def test_card_row_emit_fires_with_provider_count(db: Session) -> None:
    filters = Tier2Filters(parser_confidence=0.9)
    rows = [
        {"type": "provider", "name": "Alpha", "slug": "alpha"},
        {"type": "provider", "name": "Beta", "slug": "beta"},
    ]
    build_card_row(filters, rows)
    events = _events(db, event_name="chat.card_row.impression")
    assert len(events) == 1
    ev = events[0]
    assert ev.slot_origin == SLOT_ORIGIN_TIER2_CARD_ROW
    assert ev.payload_json == {"provider_count": 2}


def test_card_row_skips_emit_for_empty_rows(db: Session) -> None:
    """No rows → no items → no analytics event (the empty render is a no-op)."""
    filters = Tier2Filters(parser_confidence=0.9)
    build_card_row(filters, [])
    assert _events(db, event_name="chat.card_row.impression") == []


# 6. build_single_business_card emits chat.single_card.open ------------------


def test_single_card_open_fires_with_provider_id(db: Session) -> None:
    intent = IntentResult(
        mode="ask",
        sub_intent=None,
        confidence=0.9,
        entity="Acme Plumbing",
        raw_query="tell me about acme plumbing",
        normalized_query="tell me about acme plumbing",
    )
    row = {
        "id": "provider-acme-1",
        "name": "Acme Plumbing",
        "type": "provider",
        "slug": "acme-plumbing",
        "category": "plumber",
    }
    build_single_business_card(intent, row)
    events = _events(db, event_name="chat.single_card.open")
    assert len(events) == 1
    ev = events[0]
    assert ev.slot_origin == SLOT_ORIGIN_TIER2_SINGLE_CARD
    assert ev.provider_id == "provider-acme-1"


# 7. end-to-end ranking_score == Sponsor.weight ------------------------------


def test_ranking_score_in_payload_matches_sponsor_weight(client: TestClient, db: Session) -> None:
    """Defends against a refactor that drops the row.weight read at the source."""
    sp = _add_sponsor(db, name="rank-check", slot=AdSlot.SPOTLIGHT.value, weight=42)
    # Impression path
    sponsor_store.active_spotlights(db)
    imp = _events(db, event_name="home.spotlight.impression")
    assert len(imp) == 1
    assert imp[0].ranking_score == sp.weight == 42
    # Click path
    r = client.get(
        "/sponsor/click",
        params={"id": sp.id, "slot": AdSlot.SPOTLIGHT.value},
    )
    assert r.status_code == 302
    clk = _events(db, event_name="home.spotlight.click")
    assert len(clk) == 1
    assert clk[0].ranking_score == sp.weight == 42

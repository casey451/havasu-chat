"""Integration tests for the liveness rank dampener.

Covers the two wiring points from LIVENESS_RANKING_HANDOFF_2026-06-03.md:
  1. Category-page ranking (``rank_inputs_for_category`` → ``compute_card_rank``):
     a stale-heavy listing sinks below an otherwise-equal fresh peer.
  2. ``GET /api/search`` SQLite fallback: the dampener scales the stored
     ``Entity.liveness_score`` so a stale listing ranks below a fresh one even
     when it would otherwise win the alphabetical tiebreak.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.category_pages import rank_inputs_for_category
from app.core.ranking import compute_card_rank
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import Entity, Provider
from app.main import app

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


# --- 1. category-page ranking path ---


def _bare_entity(name: str, liveness: float | None) -> Entity:
    return Entity(
        id=str(uuid.uuid4()),
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=f"ent-{uuid.uuid4().hex[:12]}",
        name=name,
        liveness_score=liveness,
    )


def _bare_provider(ent: Entity, liveness: float | None) -> Provider:
    return Provider(
        provider_name=ent.name,
        category="food_drink",
        verified=False,
        liveness_score=liveness,
        entity_id=ent.id,
    )


def test_category_rank_buries_stale_below_fresh_peer() -> None:
    # Same name/distance/boosts; only liveness differs. The fresh peer wins.
    fresh = _bare_entity("Peer Diner", 0.9)
    stale = _bare_entity("Peer Diner", 0.1)
    entities = [fresh, stale]
    prov_by_eid = {
        fresh.id: _bare_provider(fresh, 0.9),
        stale.id: _bare_provider(stale, 0.1),
    }
    rank_inp = rank_inputs_for_category(
        entities,
        category_slug="eat-drink",
        ref_lat=34.48,
        ref_lng=-114.32,
        prov_by_eid=prov_by_eid,
        now=NOW,
    )
    fresh_score = compute_card_rank(rank_inp[fresh.id], now=NOW, temperature_f=95.0)
    stale_score = compute_card_rank(rank_inp[stale.id], now=NOW, temperature_f=95.0)
    assert fresh_score > stale_score


def test_category_rank_null_liveness_no_dampening() -> None:
    ent = _bare_entity("Solo Diner", None)
    prov_by_eid = {ent.id: _bare_provider(ent, None)}
    rank_inp = rank_inputs_for_category(
        [ent],
        category_slug="eat-drink",
        ref_lat=34.48,
        ref_lng=-114.32,
        prov_by_eid=prov_by_eid,
        now=NOW,
    )
    assert rank_inp[ent.id].liveness_score is None


# --- 2. search route SQLite fallback ---


@pytest.fixture
def db() -> Session:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _search_entity(*, name: str, token: str, liveness: float) -> tuple[Entity, Provider]:
    eid = str(uuid.uuid4())
    ent = Entity(
        id=eid,
        entity_type=ENTITY_TYPE_COMMERCIAL,
        slug=f"ent-{uuid.uuid4().hex[:12]}",
        name=name,
        description=f"{token} bistro",
        source="test-search-route",
        liveness_score=liveness,
    )
    p = Provider(
        provider_name=name,
        slug=f"prov-{uuid.uuid4().hex[:10]}",
        category="food_drink",
        source="test-search-route",
        draft=False,
        is_active=True,
        featured=True,  # gives both a non-zero base so the dampener can reorder
        liveness_score=liveness,
        entity_id=eid,
    )
    return ent, p


def test_search_sqlite_fallback_dampener_buries_stale(db: Session) -> None:
    token = f"Zorptastic{_suffix()}"
    # "AAA" sorts first alphabetically but is stale → dampened below the fresh peer.
    stale_ent, stale_p = _search_entity(name=f"AAA {token} Diner", token=token, liveness=0.1)
    fresh_ent, fresh_p = _search_entity(name=f"ZZZ {token} Diner", token=token, liveness=0.95)
    db.add_all([stale_ent, stale_p, fresh_ent, fresh_p])
    db.commit()

    try:
        with TestClient(app) as client:
            r = client.get("/api/search", params={"q": token, "limit": 20})
        assert r.status_code == 200
        names = [row["name"] for row in r.json()["results"]]
        fresh_name = f"ZZZ {token} Diner"
        stale_name = f"AAA {token} Diner"
        assert fresh_name in names and stale_name in names, names
        # Fresh listing outranks the stale one despite the worse alphabetical key.
        assert names.index(fresh_name) < names.index(stale_name), names
    finally:
        for obj in (stale_p, fresh_p, stale_ent, fresh_ent):
            db.delete(db.get(type(obj), obj.id) or obj)
        db.commit()


# --- 3. top_rated category sort path ---


def test_top_rated_sort_buries_stale_high_rating(db: Session) -> None:
    """A stale 4.9 sinks below a fresh 4.5 once the dampener applies."""
    from app.api.routes.category_pages import _sort_entity_ids

    stale = _bare_entity(f"Stale Grill {_suffix()}", 0.1)
    fresh = _bare_entity(f"Fresh Grill {_suffix()}", 0.9)
    sp = _bare_provider(stale, 0.1)
    sp.google_rating = 4.9
    fp = _bare_provider(fresh, 0.9)
    fp.google_rating = 4.5
    db.add_all([stale, fresh, sp, fp])
    db.commit()

    ordered = _sort_entity_ids(
        [stale, fresh],
        sort_key="top_rated",
        ref_lat=34.48,
        ref_lng=-114.32,
        db=db,
        category_slug="restaurants",
        now=NOW,
    )
    assert [e.id for e in ordered] == [fresh.id, stale.id]


def test_top_rated_sort_null_liveness_keeps_rating_order(db: Session) -> None:
    """NULL liveness is a no-op: the higher raw rating still wins."""
    from app.api.routes.category_pages import _sort_entity_ids

    hi = _bare_entity(f"Hi Grill {_suffix()}", None)
    lo = _bare_entity(f"Lo Grill {_suffix()}", None)
    hp = _bare_provider(hi, None)
    hp.google_rating = 4.9
    lp = _bare_provider(lo, None)
    lp.google_rating = 4.5
    db.add_all([hi, lo, hp, lp])
    db.commit()

    ordered = _sort_entity_ids(
        [lo, hi],
        sort_key="top_rated",
        ref_lat=34.48,
        ref_lng=-114.32,
        db=db,
        category_slug="restaurants",
        now=NOW,
    )
    assert [e.id for e in ordered] == [hi.id, lo.id]

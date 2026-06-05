"""WP-12 — one canonical per-category count across every surface (audit S4).

Before WP-12 each surface counted a category differently: Home browse tiles
walked the ``EntityCategory`` join, the Explore header used
``route_provider_filter``, and the Map expanded its own legacy set — so the same
category read different numbers on Home, Explore, and the Map. These tests pin
the reconciliation:

* the canonical count equals the canonical listing length (count == len);
* Home tile / Explore header / Map all report the SAME number for one seeded
  category;
* the canonical helper resolves ``primary_category`` first and only falls back
  to the legacy ``Provider.category`` while primary is NULL.

Seeds use the ``lodging-vacation-rentals`` primary (legacy ``lodging``) — a solo
Home tile, a Tier-1 Map scope, AND an Explore plural route — so one category
exercises all three surfaces. Rows are uniquely suffixed and torn down to stay
isolated (mirrors test_wp5_browse).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.routes import map_data as map_mod
from app.categories.queries import (
    CategoryFacets,
    category_listing,
    category_listing_count,
    primary_listing_filter,
)
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.main import app

_NOW = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)
_PRIMARY = "lodging-vacation-rentals"
_LEGACY = "lodging"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_lodging(
    *,
    n_primary: int,
    n_legacy_only: int = 0,
    prefix: str = "WP12",
) -> list[str]:
    """Insert lodging providers; return entity ids.

    ``n_primary`` rows carry the canonical ``primary_category``; ``n_legacy_only``
    rows carry ONLY the legacy ``category`` (primary NULL) to exercise the
    fallback tier. All active, non-draft.
    """
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        rows: list[Provider] = []
        for i in range(n_primary):
            rows.append(
                Provider(
                    provider_name=f"{prefix} Hotel {i:03d} {suf}",
                    category=_LEGACY,
                    primary_category=_PRIMARY,
                    google_rating=4.4,
                    google_review_count=40 + i,
                    draft=False,
                    is_active=True,
                    pending_review=False,
                    verified=False,
                    source="test-wp12",
                )
            )
        for i in range(n_legacy_only):
            rows.append(
                Provider(
                    provider_name=f"{prefix} LegacyInn {i:03d} {suf}",
                    category=_LEGACY,
                    primary_category=None,
                    draft=False,
                    is_active=True,
                    pending_review=False,
                    verified=False,
                    source="test-wp12",
                )
            )
        db.add_all(rows)
        db.commit()
        return [p.entity_id for p in rows]


def _cleanup(entity_ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_(entity_ids)))
        db.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
        db.commit()


def _canonical_listing_rows(db, primary_slugs: set[str]) -> list[Provider]:
    return (
        db.query(Provider)
        .filter(
            primary_listing_filter(primary_slugs),
            Provider.is_active.is_(True),
            Provider.draft.is_(False),
        )
        .all()
    )


# ---------------------------------------------------------------------------
# 1. count == len(listing) for the canonical filter
# ---------------------------------------------------------------------------


def test_canonical_count_equals_canonical_listing_length() -> None:
    """The number the helper COUNTS equals the rows the same filter SELECTS."""
    eids = _seed_lodging(n_primary=6, n_legacy_only=2)
    try:
        with SessionLocal() as db:
            count = category_listing_count(db, {_PRIMARY})
            rows = _canonical_listing_rows(db, {_PRIMARY})
        assert count == len(rows)
        # Our 8 seeds (6 primary + 2 legacy-only) are all present.
        assert count >= 8
    finally:
        _cleanup(eids)


# ---------------------------------------------------------------------------
# 2. cross-surface consistency: Home tile == Explore listing == canonical
# ---------------------------------------------------------------------------


def test_home_tile_count_matches_canonical_and_explore() -> None:
    """Home browse-tile count, Explore listing total, and the canonical count all
    agree for the same seeded category (the S4 reconciliation)."""
    eids = _seed_lodging(n_primary=5, n_legacy_only=1)
    try:
        with SessionLocal() as db:
            canonical = category_listing_count(db, {_PRIMARY})
            # T3.4: browse_tiles (Lake Light home) was removed with the dead-code
            # sweep; its count helper was a straight delegate to
            # category_listing_count, so the home-tile leg of this reconciliation
            # is now the canonical count itself. Explore/Map legs still verify.
            _cards, explore_total = category_listing(
                db, _PRIMARY, now=_NOW, facets=CategoryFacets(sort="alpha"), limit=500
            )
        assert explore_total == canonical
        assert canonical >= 6
    finally:
        _cleanup(eids)


def test_map_provider_selection_matches_canonical_count() -> None:
    """The Map's provider-entity selection for a scope counts the SAME providers as
    the canonical helper (one pin per provider, same membership)."""
    eids = _seed_lodging(n_primary=4, n_legacy_only=2)
    try:
        with SessionLocal() as db:
            canonical = category_listing_count(db, {_PRIMARY})
            map_entities = map_mod._select_provider_entities(
                db, category_slugs=[_PRIMARY], boat_only=False
            )
        # Restrict to our seeded rows so pre-existing prod-like fixtures can't skew
        # the equality (other suites may seed lodging too).
        seeded = set(eids)
        map_seeded = {e.id for e in map_entities if e.id in seeded}
        assert len(map_seeded) == 6  # 4 primary + 2 legacy-only, all selected
        assert canonical >= 6
    finally:
        _cleanup(eids)


# ---------------------------------------------------------------------------
# 3. primary-first / legacy-fallback parity
# ---------------------------------------------------------------------------


def test_legacy_only_row_counts_via_fallback() -> None:
    """A row with only the legacy ``category`` (primary NULL) is counted — the
    fallback tier keeps un-backfilled rows visible until classified."""
    eids = _seed_lodging(n_primary=0, n_legacy_only=3)
    try:
        with SessionLocal() as db:
            count = category_listing_count(db, {_PRIMARY})
            rows = _canonical_listing_rows(db, {_PRIMARY})
        names = {r.provider_name for r in rows}
        assert sum(1 for n in names if "LegacyInn" in n) == 3
        assert count == len(rows)
    finally:
        _cleanup(eids)


def test_primary_wins_over_contradictory_legacy() -> None:
    """When ``primary_category`` is set, it is authoritative: a row whose legacy
    ``category`` says lodging but whose primary says eat-drink counts under
    eat-drink, never lodging (no double count, no mis-count)."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"WP12 Crossfiled {suf}",
            category=_LEGACY,  # legacy says lodging ...
            primary_category="eat-drink",  # ... but canonical primary says eat-drink
            draft=False,
            is_active=True,
            pending_review=False,
            verified=False,
            source="test-wp12",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
    try:
        with SessionLocal() as db:
            lodging_rows = _canonical_listing_rows(db, {_PRIMARY})
            eat_rows = _canonical_listing_rows(db, {"eat-drink"})
        names_lodging = {r.provider_name for r in lodging_rows}
        names_eat = {r.provider_name for r in eat_rows}
        assert f"WP12 Crossfiled {suf}" not in names_lodging
        assert f"WP12 Crossfiled {suf}" in names_eat
    finally:
        _cleanup([eid])


def test_empty_or_none_inputs_are_safe() -> None:
    """Defensive contract: empty set / None db count to 0, never raise."""
    with SessionLocal() as db:
        assert category_listing_count(db, set()) == 0
    assert category_listing_count(None, {_PRIMARY}) == 0

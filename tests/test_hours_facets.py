"""Hours facets on Direction-C category pages (wf-feat-hours-facets).

Two layers of coverage:

1. Pure helpers ``_has_late_hours`` / ``_has_weekend_hours`` in
   ``app.categories.queries`` -- they parse the weekday-keyed
   ``hours_structured`` shape (``{"saturday": [{"open","close"}], ...}``)
   that ``app/providers/queries.py`` uses, and never raise on junk.

2. Integration: ``category_listing`` narrows a real category page by the
   ``open_late`` / ``open_weekends`` facets and combines them with
   ``open_now`` (all combinable per the feature brief).

Providers auto-create their Entity on insert; the test DB is a fresh
temp SQLite (conftest). Each integration case inserts uniquely-suffixed
rows and tears them down to stay isolated.

(Price facets are intentionally absent: there is no price data in the
catalog, so that facet is BLOCKED -- see the PR notes.)
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import delete

from app.categories.queries import (
    CategoryFacets,
    _has_late_hours,
    _has_weekend_hours,
    category_listing,
)
from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Entity, Provider

# 2026-01-05 is a Monday; 14:00 lands inside a 09:00-22:00 span (open now)
# and outside a 17:00-20:00 span (closed now) -- mirrors the existing
# open-now fixture in test_phase6_category_landing.
FIXED_NOW = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)


# ---------------------------------------------------------------------------
# _has_late_hours
# ---------------------------------------------------------------------------


def test_has_late_hours_close_2100_is_true() -> None:
    """A 21:00 close is past the default 20:00 threshold -> late."""
    hours = {"monday": [{"open": "11:00", "close": "21:00"}]}
    assert _has_late_hours(hours) is True


def test_has_late_hours_close_1700_is_false() -> None:
    """A 17:00 close is well before 20:00 -> not late."""
    hours = {"monday": [{"open": "08:00", "close": "17:00"}]}
    assert _has_late_hours(hours) is False


def test_has_late_hours_respects_custom_threshold() -> None:
    """A 17:00 close counts as late when the threshold is lowered to 16:00."""
    hours = {"monday": [{"open": "08:00", "close": "17:00"}]}
    assert _has_late_hours(hours, threshold_hour=16) is True


def test_has_late_hours_past_midnight_span_is_true() -> None:
    """A span that wraps past midnight (close <= open) counts as late."""
    hours = {"friday": [{"open": "20:00", "close": "02:00"}]}
    assert _has_late_hours(hours) is True


def test_has_late_hours_none_and_junk_are_false() -> None:
    """None / non-dict / malformed spans never raise and read False."""
    assert _has_late_hours(None) is False
    assert _has_late_hours({}) is False
    assert _has_late_hours("nope") is False  # type: ignore[arg-type]
    assert _has_late_hours({"monday": "junk"}) is False
    assert _has_late_hours({"monday": [{"open": "x", "close": "y"}]}) is False


# ---------------------------------------------------------------------------
# _has_weekend_hours
# ---------------------------------------------------------------------------


def test_has_weekend_hours_saturday_span_is_true() -> None:
    """A non-empty Saturday span -> open on weekends."""
    hours = {"saturday": [{"open": "10:00", "close": "16:00"}]}
    assert _has_weekend_hours(hours) is True


def test_has_weekend_hours_sunday_span_is_true() -> None:
    hours = {"sunday": [{"open": "11:00", "close": "15:00"}]}
    assert _has_weekend_hours(hours) is True


def test_has_weekend_hours_empty_weekend_is_false() -> None:
    """Explicit empty weekend lists (closed) read False."""
    hours = {
        "monday": [{"open": "08:00", "close": "17:00"}],
        "saturday": [],
        "sunday": [],
    }
    assert _has_weekend_hours(hours) is False


def test_has_weekend_hours_none_and_junk_are_false() -> None:
    assert _has_weekend_hours(None) is False
    assert _has_weekend_hours({}) is False
    assert _has_weekend_hours("nope") is False  # type: ignore[arg-type]
    assert _has_weekend_hours({"saturday": "junk"}) is False


# ---------------------------------------------------------------------------
# CategoryFacets shape
# ---------------------------------------------------------------------------


def test_category_facets_defaults_all_off() -> None:
    f = CategoryFacets()
    assert (f.open_now, f.top_rated, f.open_late, f.open_weekends) == (
        False,
        False,
        False,
        False,
    )
    assert f.any_active is False
    assert f.needs_materialize is False


def test_category_facets_top_rated_alone_skips_materialize() -> None:
    """top_rated is a pure sort -- it does not force a hours materialize."""
    f = CategoryFacets(top_rated=True)
    assert f.any_active is True
    assert f.needs_materialize is False


def test_category_facets_hours_facets_need_materialize() -> None:
    assert CategoryFacets(open_late=True).needs_materialize is True
    assert CategoryFacets(open_weekends=True).needs_materialize is True
    assert CategoryFacets(open_now=True).needs_materialize is True


# ---------------------------------------------------------------------------
# Integration: category_listing filters + combines facets
# ---------------------------------------------------------------------------


def _make_restaurant(name: str, hours: dict) -> Provider:
    return Provider(
        provider_name=name,
        category="restaurant",  # in CATEGORY_FILTERS["eat-drink"]
        google_primary_category="restaurant",
        verified=False,
        draft=False,
        is_active=True,
        pending_review=False,
        source="test-hours-facets",
        hours_structured=hours,
    )


def test_category_listing_open_late_filters() -> None:
    suf = uuid.uuid4().hex[:8]
    late_name = f"Late Night Grill {suf}"
    early_name = f"Early Bird Diner {suf}"
    with SessionLocal() as db:
        late_p = _make_restaurant(
            late_name, {"monday": [{"open": "11:00", "close": "23:00"}]}
        )
        early_p = _make_restaurant(
            early_name, {"monday": [{"open": "08:00", "close": "17:00"}]}
        )
        db.add(late_p)
        db.add(early_p)
        db.commit()
        eids = [late_p.entity_id, early_p.entity_id]

    try:
        cards, _total = category_listing(
            db_session_factory(),
            "eat-drink",
            now=FIXED_NOW,
            facets=CategoryFacets(open_late=True),
        )
        names = {c["name"] for c in cards}
        assert late_name in names
        assert early_name not in names
    finally:
        _cleanup(eids)


def test_category_listing_open_weekends_filters() -> None:
    suf = uuid.uuid4().hex[:8]
    weekend_name = f"Weekend Brunch {suf}"
    weekday_name = f"Weekday Only Cafe {suf}"
    with SessionLocal() as db:
        weekend_p = _make_restaurant(
            weekend_name,
            {
                "monday": [{"open": "09:00", "close": "17:00"}],
                "saturday": [{"open": "10:00", "close": "14:00"}],
                "sunday": [],
            },
        )
        weekday_p = _make_restaurant(
            weekday_name,
            {
                "monday": [{"open": "09:00", "close": "17:00"}],
                "saturday": [],
                "sunday": [],
            },
        )
        db.add(weekend_p)
        db.add(weekday_p)
        db.commit()
        eids = [weekend_p.entity_id, weekday_p.entity_id]

    try:
        cards, _total = category_listing(
            db_session_factory(),
            "eat-drink",
            now=FIXED_NOW,
            facets=CategoryFacets(open_weekends=True),
        )
        names = {c["name"] for c in cards}
        assert weekend_name in names
        assert weekday_name not in names
    finally:
        _cleanup(eids)


def test_category_listing_open_late_combines_with_open_now() -> None:
    """open_late AND open_now must both pass -- only the late venue that is
    also open at FIXED_NOW survives the combined facet."""
    suf = uuid.uuid4().hex[:8]
    # Late + currently open (09:00-23:00 covers Mon 14:00).
    late_open_name = f"Late And Open {suf}"
    # Late but currently closed (opens 18:00, after FIXED_NOW 14:00).
    late_closed_name = f"Late But Closed {suf}"
    # Open now but not late (closes 17:00).
    open_not_late_name = f"Open Not Late {suf}"
    with SessionLocal() as db:
        late_open = _make_restaurant(
            late_open_name, {"monday": [{"open": "09:00", "close": "23:00"}]}
        )
        late_closed = _make_restaurant(
            late_closed_name, {"monday": [{"open": "18:00", "close": "23:00"}]}
        )
        open_not_late = _make_restaurant(
            open_not_late_name, {"monday": [{"open": "09:00", "close": "17:00"}]}
        )
        db.add_all([late_open, late_closed, open_not_late])
        db.commit()
        eids = [
            late_open.entity_id,
            late_closed.entity_id,
            open_not_late.entity_id,
        ]

    try:
        cards, _total = category_listing(
            db_session_factory(),
            "eat-drink",
            now=FIXED_NOW,
            facets=CategoryFacets(open_late=True, open_now=True),
        )
        names = {c["name"] for c in cards}
        assert late_open_name in names
        assert late_closed_name not in names
        assert open_not_late_name not in names
    finally:
        _cleanup(eids)


def test_category_listing_no_facets_is_passthrough() -> None:
    """With no facets, a freshly-inserted active restaurant appears."""
    suf = uuid.uuid4().hex[:8]
    name = f"Plain Restaurant {suf}"
    with SessionLocal() as db:
        p = _make_restaurant(name, {"monday": [{"open": "09:00", "close": "17:00"}]})
        db.add(p)
        db.commit()
        eid = p.entity_id

    try:
        cards, _total = category_listing(db_session_factory(), "eat-drink", now=FIXED_NOW)
        assert name in {c["name"] for c in cards}
    finally:
        _cleanup([eid])


def test_category_listing_none_db_returns_empty() -> None:
    assert category_listing(None, "eat-drink", now=FIXED_NOW) == ([], 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def db_session_factory():
    """Return a fresh session for a listing call (closed by the caller's GC).

    category_listing only reads, so leaking the session to GC is fine in
    tests; we keep teardown explicit via _cleanup.
    """
    return SessionLocal()


def _cleanup(entity_ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_(entity_ids)))
        db.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
        db.commit()


@pytest.fixture(autouse=True)
def _no_op() -> None:
    """Placeholder autouse fixture; keeps the module importable as a suite."""
    yield

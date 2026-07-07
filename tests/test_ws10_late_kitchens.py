"""WS10 — the /night "Late-night kitchens" list (server-rendered from hours).

``redesign.late_night_kitchens`` draws from the SAME pool + hours primitive the
real Eat & Drink page's ``?late=1`` facet uses (``route_provider_filter`` +
``_has_late_hours`` over ``effective_hours_structured``), only with the threshold
raised from 8 PM to 10 PM. So this covers the delta that matters:

* a 10 PM+ close is IN, a 9 PM close is OUT (the 8 PM facet would keep it),
* past-midnight wraps count, draft/inactive rows never do,
* the shape is ``{"name", "url"}`` with a real ``/provider/<slug>`` link,
* honest-omit: non-late venues never appear (the card is hidden, not faked),
* and on the page, /night renders the card (no chat deep-link) while /family
  never shows it.

Providers auto-create their Entity on insert; the test DB is a fresh temp
SQLite (conftest). Rows are uniquely suffixed and torn down, and assertions key
on membership (never global counts) so they stay isolated from other suites.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.home import redesign
from app.main import app


def _mk(name: str, hours: dict, *, slug: str, draft: bool = False, is_active: bool = True) -> Provider:
    return Provider(
        provider_name=name,
        slug=slug,
        category="restaurant",  # in CATEGORY_FILTERS["eat-drink"]
        google_primary_category="restaurant",
        verified=False,
        draft=draft,
        is_active=is_active,
        pending_review=False,
        source="test-ws10-late-kitchens",
        hours_structured=hours,
    )


def _cleanup(entity_ids: list[str]) -> None:
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id.in_(entity_ids)))
        db.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
        db.commit()


def _names(rows: list[dict[str, str]]) -> set[str]:
    return {r["name"] for r in rows}


def test_ten_pm_close_in_nine_pm_close_out() -> None:
    """The 10 PM threshold is the whole point: a 23:00 close is IN, a 21:00 close
    (which the 8 PM ``open_late`` facet would keep) is OUT, a 17:00 close is OUT."""
    suf = uuid.uuid4().hex[:8]
    late = f"WS10 Late Grill {suf}"
    nine = f"WS10 Nine PM Diner {suf}"
    early = f"WS10 Early Bird {suf}"
    with SessionLocal() as db:
        rows = [
            _mk(late, {"monday": [{"open": "11:00", "close": "23:00"}]}, slug=f"ws10-late-{suf}"),
            _mk(nine, {"monday": [{"open": "11:00", "close": "21:00"}]}, slug=f"ws10-nine-{suf}"),
            _mk(early, {"monday": [{"open": "08:00", "close": "17:00"}]}, slug=f"ws10-early-{suf}"),
        ]
        db.add_all(rows)
        db.commit()
        eids = [r.entity_id for r in rows]

    try:
        with SessionLocal() as db:
            got = _names(redesign.late_night_kitchens(db))
        assert late in got
        assert nine not in got
        assert early not in got
    finally:
        _cleanup(eids)


def test_overnight_split_hours_count_as_late() -> None:
    """Real overnight venues arrive pre-split across midnight (Google periods:
    ``Fri …-23:59`` + ``Sat 00:00-02:00``), so the pre-midnight tail (>= 22:00)
    marks them late. (A raw ``close < open`` wrap is normalised away by
    ``_coalesce_structured`` here just as it is for the site-wide ``?late=1``
    facet — both consume ``effective_hours_structured`` — so we assert the shape
    prod actually stores.)"""
    suf = uuid.uuid4().hex[:8]
    name = f"WS10 After Hours {suf}"
    hours = {
        "friday": [{"open": "20:00", "close": "23:59"}],
        "saturday": [{"open": "00:00", "close": "02:00"}],
    }
    with SessionLocal() as db:
        p = _mk(name, hours, slug=f"ws10-overnight-{suf}")
        db.add(p)
        db.commit()
        eid = p.entity_id

    try:
        with SessionLocal() as db:
            assert name in _names(redesign.late_night_kitchens(db))
    finally:
        _cleanup([eid])


def test_shape_is_name_and_provider_url() -> None:
    suf = uuid.uuid4().hex[:8]
    name = f"WS10 Slug Check {suf}"
    slug = f"ws10-slug-{suf}"
    with SessionLocal() as db:
        p = _mk(name, {"monday": [{"open": "17:00", "close": "23:30"}]}, slug=slug)
        db.add(p)
        db.commit()
        eid = p.entity_id

    try:
        with SessionLocal() as db:
            row = next(r for r in redesign.late_night_kitchens(db) if r["name"] == name)
        assert row["url"] == f"/provider/{slug}"
    finally:
        _cleanup([eid])


def test_non_late_venues_are_omitted_not_faked() -> None:
    """Honest-omit (§4.10): an only-early venue never appears — no fabricated row."""
    suf = uuid.uuid4().hex[:8]
    early = f"WS10 Only Early {suf}"
    with SessionLocal() as db:
        p = _mk(early, {"monday": [{"open": "07:00", "close": "15:00"}]}, slug=f"ws10-omit-{suf}")
        db.add(p)
        db.commit()
        eid = p.entity_id

    try:
        with SessionLocal() as db:
            assert early not in _names(redesign.late_night_kitchens(db))
    finally:
        _cleanup([eid])


def test_draft_and_inactive_excluded() -> None:
    suf = uuid.uuid4().hex[:8]
    draft_name = f"WS10 Draft Late {suf}"
    inactive_name = f"WS10 Inactive Late {suf}"
    late_hours = {"monday": [{"open": "18:00", "close": "23:00"}]}
    with SessionLocal() as db:
        rows = [
            _mk(draft_name, late_hours, slug=f"ws10-draft-{suf}", draft=True),
            _mk(inactive_name, late_hours, slug=f"ws10-inact-{suf}", is_active=False),
        ]
        db.add_all(rows)
        db.commit()
        eids = [r.entity_id for r in rows]

    try:
        with SessionLocal() as db:
            got = _names(redesign.late_night_kitchens(db))
        assert draft_name not in got
        assert inactive_name not in got
    finally:
        _cleanup(eids)


def test_limit_caps_and_result_is_alpha_sorted() -> None:
    suf = uuid.uuid4().hex[:8]
    names = [f"WS10 Sort {c} {suf}" for c in ("C", "A", "B")]
    late = {"monday": [{"open": "18:00", "close": "23:00"}]}
    with SessionLocal() as db:
        rows = [_mk(n, late, slug=f"ws10-sort-{i}-{suf}") for i, n in enumerate(names)]
        db.add_all(rows)
        db.commit()
        eids = [r.entity_id for r in rows]

    try:
        with SessionLocal() as db:
            capped = redesign.late_night_kitchens(db, limit=2)
            full = redesign.late_night_kitchens(db, limit=50)
        # limit caps the length (>=3 late venues exist, so exactly 2 come back).
        assert len(capped) == 2
        # The full result is globally case-insensitive alphabetical.
        got = [r["name"] for r in full]
        assert got == sorted(got, key=str.casefold)
    finally:
        _cleanup(eids)


def test_night_page_renders_card_without_chat_deeplink() -> None:
    suf = uuid.uuid4().hex[:8]
    name = f"WS10 Page Venue {suf}"
    slug = f"ws10-page-{suf}"
    with SessionLocal() as db:
        p = _mk(name, {"monday": [{"open": "17:00", "close": "23:00"}]}, slug=slug)
        db.add(p)
        db.commit()
        eid = p.entity_id

    try:
        with TestClient(app) as client:
            body = client.get("/night").text
        assert "Late-night kitchens" in body
        assert name in body
        assert f"/provider/{slug}" in body
        # The old chat deep-link tile ("late night food" -> /chat) is gone.
        assert "late+night+food" not in body
    finally:
        _cleanup([eid])


def test_family_page_has_no_late_kitchens_card() -> None:
    with TestClient(app) as client:
        body = client.get("/family").text
    assert "Late-night kitchens" not in body

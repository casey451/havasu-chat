"""Phase 4 — seniors front door + chat intent, listings on category landings.

FIX_SPEC_2026-06-23 §4 / UX review §P1–P2. Much of the seniors P1 work (the
positive ``is_senior_event`` filter and the calendar ``?seniors=1`` narrow) and
the homepage P2 tightening (one merged category block + one calendar) already
landed on ``main`` for the LAKE templates — the UX review observed the older
desert layout. This phase adds the two genuinely-missing pieces: the seniors nav
front door, and real listings on the department landings.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.categories import router as cat_router
from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory, Provider
from app.home.calendar_view import parse_calendar_query
from app.main import app

_SOURCE = "test-phase4-landings"


def _nav_block(html: str, cls: str) -> str:
    m = re.search(rf'<nav class="{cls}\b[^>]*>(.*?)</nav>', html, re.DOTALL)
    assert m, f"no <nav class=\"{cls}\">"
    return m.group(1)


# ── 4 / P1: seniors chat intent ────────────────────────────────────────────────

def test_senior_intent_narrows_to_seniors() -> None:
    """The UX review's headline bug: a seniors ask must set the audience filter,
    not dump the whole week."""
    assert parse_calendar_query("what is there for seniors this week")["aud"] == "seniors"
    assert parse_calendar_query("activities for older adults")["aud"] == "seniors"
    assert parse_calendar_query("retirees meetup")["aud"] == "seniors"


def test_kids_intent_still_recognized() -> None:
    assert parse_calendar_query("what is there for kids this weekend")["aud"] == "kids"


# ── 4 / P1: seniors front door on both nav surfaces ─────────────────────────────

def test_for_seniors_front_door_on_both_nav_surfaces() -> None:
    html = TestClient(app).get("/home?theme=lake").text
    for cls in ("nav", "drawer"):
        block = _nav_block(html, cls)
        assert "/seniors" in block, f"For Seniors (/seniors) missing from .{cls}"
        assert "/family" in block, f"For Kids (/family) missing from .{cls}"


# ── 4 / P2: real listings on category landings (open-now first) ─────────────────

def _seed_pets_dept_with_providers(specs: list[dict]) -> tuple[str, list[str], bool]:
    """Seed the 'pets' department + one leaf + a provider per spec. Returns
    (leaf_slug, [provider_names], created_dept) for assertions/cleanup. Each spec:
    {name, rating, hours} where hours is a hours_structured dict or None."""
    suf = uuid4().hex[:6]
    leaf_slug = f"pets-leaf-{suf}"
    created_dept = False
    names: list[str] = []
    with SessionLocal() as db:
        dept = db.scalars(
            select(Category).where(Category.slug == "pets", Category.level == 0)
        ).first()
        if dept is None:
            dept = Category(slug="pets", name="Pets", sort_order=7, level=0)
            db.add(dept)
            db.flush()
            created_dept = True
        leaf = Category(
            slug=leaf_slug, name="Groomers", sort_order=0, level=1, parent_id=dept.id
        )
        db.add(leaf)
        db.flush()
        for spec in specs:
            ent = Entity(
                entity_type="commercial", slug=f"p4-ent-{uuid4().hex[:10]}",
                name=spec["name"], source=_SOURCE,
            )
            db.add(ent)
            db.flush()
            db.add(
                Provider(
                    provider_name=spec["name"], category="x",
                    slug=f"p4-prov-{uuid4().hex[:10]}", is_active=True, draft=False,
                    source=_SOURCE, entity_id=ent.id,
                    google_rating=spec.get("rating"),
                    google_review_count=spec.get("reviews", 50),
                    hours_structured=spec.get("hours"),
                )
            )
            db.add(EntityCategory(entity_id=ent.id, category_id=leaf.id, is_primary=True))
            names.append(spec["name"])
        db.commit()
    return leaf_slug, names, created_dept


def _cleanup(leaf_slug: str, created_dept: bool) -> None:
    with SessionLocal() as db:
        for prov in db.scalars(select(Provider).where(Provider.source == _SOURCE)).all():
            db.delete(prov)
        for ent in db.scalars(select(Entity).where(Entity.source == _SOURCE)).all():
            for ec in db.scalars(
                select(EntityCategory).where(EntityCategory.entity_id == ent.id)
            ).all():
                db.delete(ec)
            db.delete(ent)
        slugs = [leaf_slug] + (["pets"] if created_dept else [])
        for cat in db.scalars(select(Category).where(Category.slug.in_(slugs))).all():
            db.delete(cat)
        db.commit()


def test_department_landing_shows_listings_above_subtiles() -> None:
    leaf_slug, names, created = _seed_pets_dept_with_providers(
        [{"name": f"Paws Grooming {uuid4().hex[:5]}", "rating": 4.8, "reviews": 120}]
    )
    try:
        r = TestClient(app, follow_redirects=False).get("/categories/pets?theme=lake")
        assert r.status_code == 200
        body = r.text
        # The "open now first" listing section renders a real business card …
        assert "dir-listings" in body
        assert names[0] in body
        # … and it sits ABOVE the sub-tile leaf grid (honoring "open-now first").
        assert body.index("dir-listings") < body.index("leafgrid")
    finally:
        _cleanup(leaf_slug, created)


def test_landing_cards_float_open_now_first() -> None:
    """A lower-rated business that is OPEN now outranks a higher-rated one that is
    CLOSED in the landing strip (the 'open-now first' promise)."""
    monday_noon = datetime(2026, 6, 8, 12, 0)  # a Monday
    leaf_slug, names, created = _seed_pets_dept_with_providers(
        [
            # Higher rating but CLOSED today (empty span list).
            {"name": "Closed Highrated", "rating": 5.0, "hours": {"monday": []}},
            # Lower rating but OPEN now.
            {"name": "Open Lowrated", "rating": 3.5,
             "hours": {"monday": [{"open": "00:00", "close": "23:59"}]}},
        ]
    )
    try:
        with SessionLocal() as db:
            dept = db.scalars(
                select(Category).where(Category.slug == "pets", Category.level == 0)
            ).first()
            cards = cat_router._dept_landing_cards(db, dept, now=monday_noon)
        order = [c["name"] for c in cards]
        assert order.index("Open Lowrated") < order.index("Closed Highrated"), order
    finally:
        _cleanup(leaf_slug, created)


def test_landing_cards_empty_when_department_has_no_providers() -> None:
    """No providers → [] (the template gate then shows only sub-tiles, no shell)."""
    with SessionLocal() as db:
        # A throwaway empty department.
        dept = Category(slug=f"empty-dept-{uuid4().hex[:6]}", name="Empty", level=0)
        db.add(dept)
        db.flush()
        cards = cat_router._dept_landing_cards(db, dept, now=datetime(2026, 6, 8, 12, 0))
        db.rollback()
    assert cards == []

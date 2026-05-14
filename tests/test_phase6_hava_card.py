"""Phase 6.1 — unified Hava card view-model, query builder, template + CSS."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import delete, select

from app.core.timezone import LAKE_HAVASU_TZ
from app.db.database import SessionLocal
from app.db.models import Category, Entity, Event, Photo, Provider, User
from app.providers import queries, view_models


def _templates_env() -> Environment:
    root = Path(__file__).resolve().parents[1] / "app" / "templates"
    return Environment(loader=FileSystemLoader(str(root)), autoescape=True)


def test_hava_card_view_model_dataclass_fields() -> None:
    vm = view_models.HavaCardViewModel(
        entity_id="e1",
        entity_type="commercial",
        name="Test",
        profile_url="/provider/test",
        hero_photo_url="https://ex.test/h.jpg",
        category_slug="eat-drink",
        category_label="Eat & Drink",
        district_slug="downtown",
        district_name="Downtown",
        status_line_text="Open until 9 PM",
        status_line_color="green",
        freshness_band="green",
        is_sponsored=False,
        boat_access_badge=False,
        heat_exposure_pill=None,
    )
    assert vm.entity_id == "e1"
    assert vm.heat_exposure_pill is None


def test_derive_freshness_band_from_updated_at() -> None:
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    assert queries.derive_freshness_band_from_updated_at(now - timedelta(days=10), now=now) == "green"
    assert queries.derive_freshness_band_from_updated_at(now - timedelta(days=45), now=now) == "amber"
    assert queries.derive_freshness_band_from_updated_at(now - timedelta(days=100), now=now) == "red"


def test_build_card_view_model_commercial_with_photo() -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)  # Monday 2pm
    with SessionLocal() as db:
        cat = db.scalars(select(Category).limit(1)).first()
        assert cat is not None
        p = Provider(
            provider_name=f"Card Test Plumbing {suf}",
            category="home_services",
            category_id=cat.id,
            verified=True,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase6",
            hours_structured={
                "monday": [{"open": "09:00", "close": "22:00"}],
            },
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        ent = db.get(Entity, eid)
        assert ent is not None
        ent.updated_at = (now - timedelta(days=5)).replace(tzinfo=None)
        u = User(email=f"photo-{suf}@example.com", display_name="P")
        db.add(u)
        db.commit()
        db.refresh(u)
        db.add(
            Photo(
                entity_id=eid,
                uploaded_by_user_id=u.id,
                mime_type="image/jpeg",
                storage_key=f"k/{suf}/",
                status="live",
                is_hero=True,
                hero_url="https://cdn.example/hero.jpg",
                display_order=0,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        db.commit()

        vm = queries.build_card_view_model(db, eid, now=now)
        assert vm is not None
        assert vm.hero_photo_url == "https://cdn.example/hero.jpg"
        assert vm.freshness_band == "green"
        assert vm.status_line_color == "green"
        assert "Open until" in vm.status_line_text
        assert vm.profile_url.startswith("/provider/")
        assert vm.boat_access_badge is False

        db.execute(delete(Photo).where(Photo.entity_id == eid))
        db.execute(delete(Provider).where(Provider.id == p.id))
        db.execute(delete(User).where(User.id == u.id))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_commercial_closed_amber_and_stale_red() -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 23, 0, 0, tzinfo=LAKE_HAVASU_TZ)  # Monday 11pm — outside 9–22
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Closed Test {suf}",
            category="home_services",
            verified=True,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase6",
            hours_structured={
                "monday": [{"open": "09:00", "close": "22:00"}],
            },
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        vm = queries.build_card_view_model(db, eid, now=now)
        assert vm is not None
        assert vm.status_line_color == "amber"

        ent = db.get(Entity, eid)
        assert ent is not None
        ent.updated_at = (now - timedelta(days=120)).replace(tzinfo=None)
        db.commit()
        vm2 = queries.build_card_view_model(db, eid, now=now)
        assert vm2 is not None
        assert vm2.freshness_band == "red"
        assert vm2.status_line_color == "red"

        db.execute(delete(Provider).where(Provider.id == p.id))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_commercial_hours_unknown() -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"No Hours {suf}",
            category="home_services",
            verified=True,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase6",
            hours_structured=None,
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        vm = queries.build_card_view_model(db, eid, now=now)
        assert vm is not None
        assert vm.status_line_text == "Hours unknown"
        assert vm.status_line_color == "amber"
        db.execute(delete(Provider).where(Provider.id == p.id))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_is_sponsored_pill_data() -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Sponsored {suf}",
            category="home_services",
            verified=True,
            tier="sponsored",
            sponsored_until=(now + timedelta(days=7)).replace(tzinfo=None),
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase6",
            hours_structured={"monday": [{"open": "09:00", "close": "17:00"}]},
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        vm = queries.build_card_view_model(db, eid, now=now)
        assert vm is not None
        assert vm.is_sponsored is True
        db.execute(delete(Provider).where(Provider.id == p.id))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_heat_exposure_pill_and_boat_badge() -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Heat Boat {suf}",
            category="home_services",
            verified=True,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-phase6",
            hours_structured={"monday": [{"open": "09:00", "close": "17:00"}]},
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        ent = db.get(Entity, eid)
        assert ent is not None
        ent.heat_exposure = "indoor"
        ent.boat_access = {"dock": True}
        db.commit()
        vm = queries.build_card_view_model(db, eid, now=now)
        assert vm is not None
        assert vm.heat_exposure_pill is None
        assert vm.boat_access_badge is True

        ent.heat_exposure = "shaded"
        ent.boat_access = None
        db.commit()
        vm2 = queries.build_card_view_model(db, eid, now=now)
        assert vm2 is not None
        assert vm2.heat_exposure_pill == "Shaded"
        assert vm2.boat_access_badge is False

        db.execute(delete(Provider).where(Provider.id == p.id))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_event_card_status_lines() -> None:
    suf = uuid.uuid4().hex[:8]
    today = date(2026, 7, 4)
    now = datetime(2026, 7, 4, 10, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    with SessionLocal() as db:
        ev = Event(
            title=f"Concert {suf}",
            normalized_title=f"concert {suf}",
            date=today,
            start_time=time(18, 0),
            end_time=None,
            location_name="Park",
            location_normalized="park",
            description="Music.",
            event_url="https://example.com/e",
            status="live",
            source="admin",
        )
        db.add(ev)
        db.commit()
        eid = ev.entity_id
        vm = queries.build_card_view_model(db, eid, now=now)
        assert vm is not None
        assert vm.entity_type == "event"
        assert "tonight" in vm.status_line_text.lower()
        assert vm.status_line_color == "lake-blue"
        assert vm.profile_url == f"/events/{ev.id}"

        ev2 = Event(
            title=f"Future Sat {suf}",
            normalized_title=f"future sat {suf}",
            date=date(2026, 7, 11),
            start_time=time(10, 0),
            end_time=None,
            location_name="Park",
            location_normalized="park",
            description="Sat event.",
            event_url="https://example.com/e2",
            status="live",
            source="admin",
        )
        db.add(ev2)
        db.commit()
        eid2 = ev2.entity_id
        vm2 = queries.build_card_view_model(
            db, eid2, now=datetime(2026, 7, 6, 10, 0, 0, tzinfo=LAKE_HAVASU_TZ)
        )
        assert vm2 is not None
        assert "weekend" in vm2.status_line_text.lower()

        ev3 = Event(
            title=f"Old {suf}",
            normalized_title=f"old {suf}",
            date=date(2026, 5, 1),
            start_time=time(10, 0),
            end_time=None,
            location_name="Park",
            location_normalized="park",
            description="Old.",
            event_url="https://example.com/e3",
            status="live",
            source="admin",
        )
        db.add(ev3)
        db.commit()
        eid3 = ev3.entity_id
        vm3 = queries.build_card_view_model(
            db, eid3, now=datetime(2026, 7, 15, 10, 0, 0, tzinfo=LAKE_HAVASU_TZ)
        )
        assert vm3 is not None
        assert "last week" in vm3.status_line_text.lower()
        assert vm3.status_line_color == "red"

        for e in (ev, ev2, ev3):
            eid_e = e.entity_id
            db.execute(delete(Event).where(Event.id == e.id))
            db.execute(delete(Entity).where(Entity.id == eid_e))
        db.commit()


def test_place_seasonal_status() -> None:
    suf = uuid.uuid4().hex[:8]
    now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    with SessionLocal() as db:
        ent = Entity(
            entity_type="place",
            slug=f"place-{suf}",
            name=f"Test Park {suf}",
            source="test-phase6",
            seasonal_hours={"default": "summer-only"},
        )
        db.add(ent)
        db.commit()
        vm = queries.build_card_view_model(db, ent.id, now=now)
        assert vm is not None
        assert vm.status_line_text == "Seasonal"
        assert vm.status_line_color == "amber"
        db.execute(delete(Entity).where(Entity.id == ent.id))
        db.commit()


@pytest.mark.parametrize(
    "ctx",
    ("category_page", "search_results", "group_landing", "profile_reference"),
)
def test_hava_card_template_renders_four_contexts(ctx: str) -> None:
    env = _templates_env()
    tpl = env.get_template("components/hava_card.html")
    vm = view_models.HavaCardViewModel(
        entity_id="e-x",
        entity_type="commercial",
        name=f"Listing — {ctx}",
        profile_url="/provider/demo",
        hero_photo_url=None,
        category_slug="eat-drink",
        category_label="Eat & Drink",
        district_slug="english-village",
        district_name="English Village",
        status_line_text="Open until 8 PM",
        status_line_color="green",
        freshness_band="green",
        is_sponsored=ctx == "search_results",
        boat_access_badge=False,
        heat_exposure_pill="Shaded",
    )
    html = tpl.render(hava_card=vm)
    assert "Listing —" in html
    assert "eat-drink" in html
    assert "hava-card__status--green" in html
    if ctx == "search_results":
        assert "hava-card__sponsor" in html
    else:
        assert "Sponsored" not in html


def test_hava_card_template_empty_hero_and_district() -> None:
    env = _templates_env()
    tpl = env.get_template("components/hava_card.html")
    vm = view_models.HavaCardViewModel(
        entity_id="e-y",
        entity_type="place",
        name="No Hero Marina",
        profile_url="/home",
        hero_photo_url=None,
        category_slug="on-the-water",
        category_label="On the Water",
        district_slug="",
        district_name="",
        status_line_text="Seasonal",
        status_line_color="amber",
        freshness_band="amber",
        is_sponsored=False,
        boat_access_badge=False,
        heat_exposure_pill=None,
    )
    html = tpl.render(hava_card=vm)
    assert "hava-card__hero-img" not in html
    assert "hava-card__hero--on-the-water" in html
    assert "English Village" not in html


def test_hava_card_css_responsive_rules() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "styles"
        / "components"
        / "hava_card.css"
    )
    text = path.read_text(encoding="utf-8")
    assert "grid-template-columns: 1fr" in text
    assert "@media (min-width: 768px)" in text
    assert "grid-template-columns: minmax(160px, 38%) 1fr" in text


def test_home_css_imports_hava_card() -> None:
    home = (
        Path(__file__).resolve().parents[1] / "app" / "static" / "styles" / "home.css"
    )
    assert '@import url("components/hava_card.css");' in home.read_text(encoding="utf-8")


def test_is_open_status_from_structured_hours_matches_provider_path() -> None:
    """Regression: shared hours helper matches prior Provider-only behavior."""
    hs = {"monday": [{"open": "09:00", "close": "17:00"}]}
    now = datetime(2026, 1, 5, 14, 0, 0, tzinfo=LAKE_HAVASU_TZ)
    o, raw = queries.is_open_status_from_structured_hours(hs, now=now)
    assert o is True
    assert raw and "Closes at" in raw

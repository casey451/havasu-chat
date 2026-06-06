"""Provider profile surfaces a venue's recurring classes (Schedule + Offering).

The schedule-hunt findings publish onto the venue Entity as Schedule + Offering
rows; this is the page where they must show up for readers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Offering, Provider, Schedule
from app.main import app
from app.providers import view_models


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_gym_with_class() -> tuple[str, str]:
    """Create a provider (+ entity) with one paired Offering/Schedule. Returns (slug, entity_id)."""
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Bridge City Combat {suf}",
            category="fitness_sports",
            verified=True,
            draft=False,
            is_active=True,
            pending_review=False,
            source="test-provider-classes",
        )
        db.add(p)
        db.commit()
        eid = p.entity_id
        db.add(
            Offering(
                entity_id=eid, name="Kids BJJ", description="Ages 6-12 fundamentals.",
                price_text="$80/mo", display_order=0, created_at=_now(), updated_at=_now(),
            )
        )
        db.add(
            Schedule(
                entity_id=eid, schedule_type="recurring",
                days_of_week=["monday", "wednesday"], start_time=time(17, 0), end_time=time(18, 0),
                notes="Kids BJJ", created_at=_now(), updated_at=_now(),
            )
        )
        db.commit()
        return p.slug, eid


# --- pure formatters / builder ---------------------------------------------


def test_format_class_days_canonical_order() -> None:
    assert view_models._format_class_days(["wednesday", "monday"]) == "Mon, Wed"
    assert view_models._format_class_days([]) == ""
    assert view_models._format_class_days(None) == ""


def test_format_class_time_range_and_partial() -> None:
    assert view_models._format_class_time(time(17, 0), time(18, 30)) == "5:00 PM – 6:30 PM"
    assert view_models._format_class_time(time(9, 5), None) == "9:05 AM"
    assert view_models._format_class_time(None, None) == ""


def test_build_class_schedule_pairs_offering_and_schedule() -> None:
    slug, eid = _make_gym_with_class()
    with SessionLocal() as db:
        prov = db.query(Provider).filter(Provider.slug == slug).one()
        vm = view_models.build(prov, db=db)
    assert len(vm.class_schedule) == 1
    row = vm.class_schedule[0]
    assert row["title"] == "Kids BJJ"
    assert row["days"] == "Mon, Wed"
    assert row["time"] == "5:00 PM – 6:00 PM"
    assert row["cost"] == "$80/mo"
    assert "fundamentals" in (row["description"] or "").lower()


def test_no_classes_means_empty_schedule() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"No Class Gym {suf}", category="fitness_sports",
            verified=True, draft=False, is_active=True, pending_review=False,
            source="test-provider-classes",
        )
        db.add(p)
        db.commit()
        vm = view_models.build(p, db=db)
    assert vm.class_schedule == []


# --- end-to-end render ------------------------------------------------------


def test_profile_page_renders_class_schedule_section() -> None:
    slug, _ = _make_gym_with_class()
    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    body = r.text
    assert "Classes &amp; schedule" in body
    assert "Kids BJJ" in body
    assert "Mon, Wed" in body
    assert "5:00 PM – 6:00 PM" in body


def test_build_class_schedule_filters_non_recurring_and_untitled_rows() -> None:
    """One-off schedule rows and untitled rows with no offering must not leak
    into the classes section (they render as bare "Class" junk)."""
    slug, eid = _make_gym_with_class()
    with SessionLocal() as db:
        db.add(
            Schedule(
                entity_id=eid, schedule_type="one_off",
                days_of_week=["friday"], start_time=time(9, 0), end_time=time(10, 0),
                notes="Pop-up seminar", created_at=_now(), updated_at=_now(),
            )
        )
        db.add(
            Schedule(
                entity_id=eid, schedule_type="recurring",
                days_of_week=["monday", "friday"], start_time=time(8, 15), end_time=time(9, 15),
                notes=None,  # untitled, no paired offering -> junk row
                created_at=_now(), updated_at=_now(),
            )
        )
        db.commit()
        prov = db.query(Provider).filter(Provider.slug == slug).one()
        vm = view_models.build(prov, db=db)
    assert [r["title"] for r in vm.class_schedule] == ["Kids BJJ"]


def test_class_schedule_as_of_stamp() -> None:
    """The classes section carries a 'Times as of <Month Year>' honesty stamp
    derived from the newest recurring schedule row's capture date."""
    slug, eid = _make_gym_with_class()
    with SessionLocal() as db:
        prov = db.query(Provider).filter(Provider.slug == slug).one()
        vm = view_models.build(prov, db=db)
    assert vm.class_schedule_as_of == _now().strftime("%B %Y")

    client = TestClient(app)
    r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    assert f"Times as of {vm.class_schedule_as_of}" in r.text

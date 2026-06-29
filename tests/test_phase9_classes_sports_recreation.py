"""Phase 9b — classes-sports-recreation chip filters."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.routes.category_pages import (
    _apply_classes_sports_filters,
    _program_matches_age_band,
    category_page_config,
)
from app.db.database import SessionLocal
from app.db.models import Entity, Program
from app.main import app


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


def test_category_config_has_age_and_drop_in_chips() -> None:
    cfg = category_page_config("classes-sports-recreation")
    params = {c["param"] for c in cfg.operational_chips}
    assert "drop_in" in params
    assert "registration" in params
    # Age buckets collapsed to Youth (under 18) / Adult (2026-06-29).
    assert "youth" in params
    assert "adults" in params


def test_program_age_band_kids() -> None:
    prog = Program(
        title="Kids swim",
        description="d",
        activity_category="swim",
        age_min=5,
        age_max=10,
        schedule_days=["tue"],
        schedule_start_time=__import__("datetime").time(10, 0),
        schedule_end_time=__import__("datetime").time(11, 0),
        location_name="Pool",
        provider_name="City",
    )
    assert _program_matches_age_band(prog, "kids")
    assert not _program_matches_age_band(prog, "teens")
    # The collapsed "youth" band folds in kids (anyone under 18).
    assert _program_matches_age_band(prog, "youth")


def test_program_age_band_youth_includes_teens() -> None:
    prog = Program(
        title="Teen art",
        description="d",
        activity_category="art",
        age_min=13,
        age_max=17,
        schedule_days=["wed"],
        schedule_start_time=__import__("datetime").time(16, 0),
        schedule_end_time=__import__("datetime").time(17, 0),
        location_name="Center",
        provider_name="City",
    )
    assert _program_matches_age_band(prog, "youth")
    assert not _program_matches_age_band(prog, "adults")


def test_drop_in_filter(db) -> None:
    slug = f"gym-{uuid.uuid4().hex[:8]}"
    ent = Entity(
        name=f"Gym {uuid.uuid4().hex[:6]}",
        slug=slug,
        entity_type="commercial",
        is_active=True,
        crowd_notes={"drop_in_friendly": True},
    )
    db.add(ent)
    db.flush()
    out = _apply_classes_sports_filters(
        [ent],
        db=db,
        drop_in=True,
        registration=False,
        kids=False,
        teens=False,
        adults=False,
        senior_55=False,
    )
    assert ent in out


def test_classes_sports_page_301s_to_department() -> None:
    # A.3 nav rewire: the retired singular route 301s straight to the
    # fitness-and-wellness department landing.
    client = TestClient(app)
    r = client.get("/category/classes-sports-recreation", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/categories/fitness-and-wellness"

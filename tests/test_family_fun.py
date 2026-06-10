"""Family/kids venue browse — detection, venue set, and component contract."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.chat.family_fun import (
    family_fun_rows,
    is_family_browse_query,
    try_family_fun,
)
from app.db.database import Base
from app.db.models import Provider


@pytest.fixture
def mem_db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _provider(name: str, *, gcat: str | None = None, cat: str = "x", rating: float = 4.5,
              draft: bool = False, active: bool = True) -> Provider:
    return Provider(
        provider_name=name,
        category=cat,
        google_primary_category=gcat,
        google_rating=rating,
        slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:6]}",
        is_active=active,
        draft=draft,
    )


def _seed_family_venues(db: Session) -> None:
    db.add_all(
        [
            _provider("The Spot - Pizza, Arcade & More", gcat="entertainment_attractions"),
            _provider("Havasu Lanes & Keglers Pub", gcat="bowling_alley"),
            _provider("Altitude Trampoline Park", gcat="amusement_park"),
            _provider("Aquatic Center", cat="recreation"),
            _provider("Desert Hawks RC Club", gcat="entertainment_attractions"),
            _provider("Havasu Skates (SARA Park Roller Rink)", gcat="entertainment_attractions"),
            # Must be excluded: bar with "arcade" in the name.
            _provider("Glitch Barcadium", gcat="bar"),
            # Hidden rows never surface.
            _provider("Draft Arcade", gcat="arcade", draft=True),
            _provider("Closed Bowling", gcat="bowling_alley", active=False),
        ]
    )
    db.commit()


# --- detection ----------------------------------------------------------------


def test_family_browse_queries_detected() -> None:
    for q in (
        "what is there for kids to do",
        "things to do with kids",
        "fun stuff to do for children",
        "activities for my toddler",
        "what can the kids do around here",
        "where can we take the kids",
        "family friendly things to do",
    ):
        assert is_family_browse_query(q), q


def test_non_family_or_non_browse_queries_not_detected() -> None:
    for q in (
        "things to do this weekend",  # no kid token
        "aquatic center hours",  # factual, no browse shape
        "kids haircut",  # kid token, no browse shape
        "",
    ):
        assert not is_family_browse_query(q), q


# --- venue set ----------------------------------------------------------------


def test_family_rows_include_staples_and_exclude_bars(mem_db: Session) -> None:
    _seed_family_venues(mem_db)
    names = " | ".join(r["name"] for r in family_fun_rows(mem_db))
    assert "The Spot" in names
    assert "Havasu Lanes" in names
    assert "Trampoline" in names
    assert "Aquatic Center" in names
    assert "Desert Hawks RC Club" in names
    assert "Roller Rink" in names
    assert "Glitch Barcadium" not in names  # bar exclusion
    assert "Draft Arcade" not in names  # draft never surfaces
    assert "Closed Bowling" not in names  # inactive never surfaces


# --- component contract --------------------------------------------------------


def test_try_family_fun_emits_business_list_component(mem_db: Session) -> None:
    _seed_family_venues(mem_db)
    component_meta: dict = {}
    voice = try_family_fun("what is there for kids to do", mem_db, component_meta)
    assert voice is not None
    assert component_meta["type"] == "business_list"
    data = component_meta["data"]
    assert data["foot_link"] == "/categories/things-to-do-and-attractions"
    assert len(data["items"]) >= 5  # more than the old 5-cap when venues exist


def test_try_family_fun_passes_on_non_family_query(mem_db: Session) -> None:
    _seed_family_venues(mem_db)
    component_meta: dict = {}
    assert try_family_fun("best tacos in town", mem_db, component_meta) is None
    assert component_meta == {}

"""Wedding/event-venue browse — detection, venue set, and component contract."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.chat.wedding_venues import (
    is_wedding_venue_query,
    try_wedding_venues,
    wedding_venue_rows,
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


def _provider(
    name: str, *, cat: str = "hotel", rating: float = 4.4, draft: bool = False, active: bool = True
) -> Provider:
    return Provider(
        provider_name=name,
        category=cat,
        google_rating=rating,
        slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:6]}",
        is_active=active,
        draft=draft,
    )


def _seed_venues(db: Session) -> None:
    db.add_all(
        [
            _provider("London Bridge Resort", rating=4.4),
            _provider("The Nautical Beachfront Resort", cat="resort_hotel", rating=4.1),
            _provider("Iron Wolf Golf & Country Club", cat="golf", rating=4.5),
            # A sub-venue that must NOT ride along on the resort match:
            _provider("Turtle Grille at The Nautical Beachfront Resort", cat="restaurant"),
            # An inactive venue must not render (honest omission):
            _provider("Havasu Springs Resort", cat="lodging", active=False),
            # Unrelated business:
            _provider("All Seasons Plumbing", cat="plumber"),
        ]
    )
    db.commit()


# ── detection (pure) ─────────────────────────────────────────────────────────


def test_detects_venue_asks() -> None:
    for q in (
        "wedding venues",
        "wedding venue",
        "event venue",
        "banquet hall",
        "reception hall",
        "where can i get married",
        "venue for a wedding",
        "wedding reception venue",
    ):
        assert is_wedding_venue_query(q), q


def test_excludes_service_and_unrelated_asks() -> None:
    # Wedding *service* asks belong to the directory's service path, not here.
    for q in (
        "wedding planner",
        "wedding photographer",
        "wedding cake",
        "wedding dj",
        "wedding dress shop",
        "hotels",
        "best plumber",
    ):
        assert not is_wedding_venue_query(q), q


# ── venue set + component contract (DB-backed) ───────────────────────────────


def test_rows_match_venues_exclude_subvenues_and_inactive(mem_db: Session) -> None:
    _seed_venues(mem_db)
    rows = wedding_venue_rows(mem_db)
    names = {r.get("name") for r in rows}
    assert "London Bridge Resort" in names
    assert "The Nautical Beachfront Resort" in names
    assert "Iron Wolf Golf & Country Club" in names
    # A sub-venue of a resort must not ride along on the name match.
    assert "Turtle Grille at The Nautical Beachfront Resort" not in names
    # An inactive venue renders honestly as absent.
    assert "Havasu Springs Resort" not in names
    # Best-rated first.
    assert rows[0]["name"] == "Iron Wolf Golf & Country Club"


def test_try_wedding_venues_builds_business_list(mem_db: Session) -> None:
    _seed_venues(mem_db)
    meta: dict = {}
    text = try_wedding_venues("wedding venues", mem_db, meta)
    assert text is not None
    assert meta["type"] == "business_list"
    names = [it.get("name") for it in meta["data"].get("items", [])]
    assert "London Bridge Resort" in names


def test_try_wedding_venues_yields_for_service_query(mem_db: Session) -> None:
    _seed_venues(mem_db)
    assert try_wedding_venues("wedding planner", mem_db, {}) is None


def test_try_wedding_venues_none_when_no_live_venue(mem_db: Session) -> None:
    # No venues seeded -> nothing fabricated, caller falls through.
    assert try_wedding_venues("wedding venues", mem_db, {}) is None

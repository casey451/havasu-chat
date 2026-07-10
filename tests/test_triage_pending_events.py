"""Selection-logic tests for scripts/triage_pending_events.py.

Uses a self-contained in-memory SQLite so it never touches the shared session DB
(these are destructive-tooling guards; select_rows must pick exactly the right
rows). select_rows takes a Session directly, so no SessionLocal patching needed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

import scripts.triage_pending_events as t
from app.db.models import Base, Contribution


def _seed(db: Session) -> None:
    def mk(name: str, source: str, d: date, status: str = "pending", et: str = "event") -> Contribution:
        return Contribution(
            entity_type=et,
            submission_name=name,
            source=source,
            status=status,
            event_date=d,
            submission_url=f"https://x/{name}",
        )

    db.add_all(
        [
            mk("2027 A", "parks_rec_calendar", date(2027, 6, 1)),
            mk("2026 future", "parks_rec_calendar", date(2026, 8, 1)),
            mk("2026 past", "parks_rec_calendar", date(2026, 6, 1)),
            mk("allevents past", "allevents", date(2026, 6, 1)),
            mk("already rejected", "parks_rec_calendar", date(2027, 6, 1), status="rejected"),
            mk("a provider row", "parks_rec_calendar", date(2027, 6, 1), et="provider"),
        ]
    )
    db.commit()


@pytest.fixture
def db() -> Iterator[Session]:
    eng = sa.create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        _seed(s)
        yield s


def _names(rows: list[Contribution]) -> set[str]:
    return {r.submission_name for r in rows}


def test_year_filter_pending_only(db: Session) -> None:
    rows = t.select_rows(
        db, sources=["parks_rec_calendar"], ids=[], before=None, year=2027, from_status="pending"
    )
    # 2027 pending event only — not the rejected 2027 nor the provider row.
    assert _names(rows) == {"2027 A"}


def test_before_filter(db: Session) -> None:
    rows = t.select_rows(
        db, sources=["allevents"], ids=[], before=date(2026, 7, 9), year=None, from_status="pending"
    )
    assert _names(rows) == {"allevents past"}


def test_parks_before_filter_scoped_to_source(db: Session) -> None:
    rows = t.select_rows(
        db,
        sources=["parks_rec_calendar"],
        ids=[],
        before=date(2026, 7, 9),
        year=None,
        from_status="pending",
    )
    assert _names(rows) == {"2026 past"}


def test_undo_selects_rejected(db: Session) -> None:
    rows = t.select_rows(
        db, sources=["parks_rec_calendar"], ids=[], before=None, year=2027, from_status="rejected"
    )
    assert _names(rows) == {"already rejected"}


def test_ids_selector(db: Session) -> None:
    target = db.scalars(
        sa.select(Contribution).where(Contribution.submission_name == "2026 future")
    ).one()
    rows = t.select_rows(
        db, sources=None, ids=[target.id], before=None, year=None, from_status="pending"
    )
    assert _names(rows) == {"2026 future"}


def test_parse_ids() -> None:
    assert t._parse_ids("1 2,3  4") == [1, 2, 3, 4]
    assert t._parse_ids(None) == []


def test_main_requires_a_selector() -> None:
    with pytest.raises(SystemExit):
        t.main(["--reason", "unverifiable"])  # no --source and no --ids

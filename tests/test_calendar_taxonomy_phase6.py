"""Calendar taxonomy rebuild — Phase 6 (2026-06-25): historical activity-tag
backfill.

The backfill re-derives the canonical ``activity:*`` / facet / audience tags via
the single ingest classifier and adds only the MISSING ones to legacy Event
rows — never removing or rewriting an existing tag. ``--dry-run`` writes nothing;
a real run is reversible via an undo snapshot CSV.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event
from scripts.backfill_event_activity_tags_2026_06_25 import added_activity_tags, run


# ── pure tag-merge function ───────────────────────────────────────────────────
def test_added_activity_tags_adds_only_missing() -> None:
    # A legacy craft row with no namespaced tags gets activity:arts.
    added = added_activity_tags("Stained Glass Painting", "Art Guild", ["community"])
    assert "activity:arts" in added

    # A cosmic row gets activity:bowling + facet:special.
    added = added_activity_tags("Cosmic Bowling", "Havasu Lanes", [])
    assert "activity:bowling" in added and "facet:special" in added

    # Idempotent: a row that already carries the canonical tag gets nothing new.
    assert added_activity_tags(
        "Stained Glass Painting", "Art Guild", ["activity:arts"]
    ) == []

    # A non-activity row (plain market) gets no activity tag.
    assert added_activity_tags("Farmers Market", None, ["community"]) == []


def test_added_activity_tags_preserves_existing_tags() -> None:
    # The function returns ONLY additions; the caller keeps existing tags. A
    # senior-tagged row picks up audience:senior without losing "senior".
    added = added_activity_tags("Pinochle", "Senior Center", ["senior"])
    assert "audience:senior" in added
    assert "senior" not in added  # never re-lists an existing tag


# ── runner: dry-run writes nothing; apply adds + is idempotent ────────────────
def _add(db, *, title, tags) -> str:
    ev = Event(
        title=title, normalized_title=title.lower(), date=date(2099, 7, 13),
        start_time=time(10, 0), end_time=None, location_name="Test Venue",
        location_normalized="test venue", description="x",
        event_url=f"https://example.com/{uuid.uuid4().hex[:8]}", tags=tags,
        status="live", source="test-taxo-p6", verified=True, is_recurring=False,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def test_backfill_dry_run_then_apply(tmp_path) -> None:
    s = uuid.uuid4().hex[:6]
    title = f"ZZ Taco Cooking Class {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add(db, title=title, tags=["community"]))
        db.commit()
    snapshot = str(tmp_path / "snap.csv")
    try:
        # Dry-run: reports a change but writes nothing.
        res = run(dry_run=True, snapshot_path=snapshot, source="test-taxo-p6")
        assert res["changed"] >= 1
        with SessionLocal() as db:
            row = db.query(Event).filter(Event.entity_id == eids[0]).one()
            assert "activity:cooking" not in (row.tags or [])

        # Apply: adds the canonical tag, keeps the existing one, writes a snapshot.
        run(dry_run=False, snapshot_path=snapshot, source="test-taxo-p6")
        with SessionLocal() as db:
            row = db.query(Event).filter(Event.entity_id == eids[0]).one()
            assert "activity:cooking" in row.tags
            assert "community" in row.tags  # existing tag preserved
        import os
        assert os.path.exists(snapshot)

        # Idempotent: a second apply finds this row unchanged.
        with SessionLocal() as db:
            before = list(
                db.query(Event).filter(Event.entity_id == eids[0]).one().tags
            )
        run(dry_run=False, snapshot_path=snapshot, source="test-taxo-p6")
        with SessionLocal() as db:
            after = list(
                db.query(Event).filter(Event.entity_id == eids[0]).one().tags
            )
        assert before == after
    finally:
        with SessionLocal() as db:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
            db.commit()

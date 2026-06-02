"""places_load funnel-adoption behavior: ambiguous reconcile holds for review.

Before funnel adoption the places insert branch DROPPED an ambiguous reconcile
(counts["reconcile_skipped_ambiguous"] += 1; continue). After adoption it routes
through app.contrib.scraper_ingest.decide_ingest and honours ``should_hide`` --
landing the row HELD (draft=True + pending_review=True) so an uncertain Google
row is captured for the admin review queue, hidden from users, never lost.

Run: python -m pytest tests/test_places_load_funnel.py -q

The upsert path commits; this test deletes the row + entity it creates.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import select

from app.contrib.ingest_reconciler import ReconcileResult
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from scripts.places_load import upsert


@patch("app.contrib.scraper_ingest.reconcile_hit")
def test_places_ambiguous_holds_for_review(mock_rec) -> None:
    uid = uuid.uuid4().hex[:10]
    name = f"Places Ambiguous {uid}"
    pid = f"ChIJfunnel_{uid}"
    mock_rec.return_value = ReconcileResult(
        action="ambiguous",
        existing_id="some-other-entity",
        reason="name match only (no geo)",
    )
    row = {
        "display_name": name,
        "place_id": pid,
        "formatted_address": "123 Funnel St",
        "lat": 34.47,
        "lng": -114.34,
        "_first_seen_domain": "food_drink",
    }
    counts = upsert([row])
    assert counts["inserted_pending"] == 1
    assert counts["inserted"] == 0
    assert counts["reconcile_skipped_ambiguous"] == 0

    with SessionLocal() as db:
        prov = db.scalars(select(Provider).where(Provider.provider_name == name)).one()
        try:
            assert prov.draft is True
            assert prov.pending_review is True
            assert prov.source == "google_places"
        finally:
            eid = prov.entity_id
            db.delete(prov)
            if eid:
                ent = db.get(Entity, eid)
                if ent is not None:
                    db.delete(ent)
            db.commit()

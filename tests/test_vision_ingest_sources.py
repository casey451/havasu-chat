"""Regression: the vision scrapers' source values are first-class.

Bug #4 (VPS, 2026-06-24): the scrapers emit source="parks_rec_calendar" /
"parks_rec_flyers" / "senior_center_flyers", but those were never added to the
``ContributionCreate`` source Literal, so every --apply ingest raised a validation
error and inserted 0. These guards keep that from regressing.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.contrib.event_reconciler import EVENT_SOURCE_PRIORITY
from app.schemas.contribution import ContributionCreate

VISION_SOURCES = ("parks_rec_calendar", "parks_rec_flyers", "senior_center_flyers")


@pytest.mark.parametrize("source", VISION_SOURCES)
def test_contribution_create_accepts_vision_source(source: str) -> None:
    c = ContributionCreate(
        entity_type="event",
        submission_name="Tiny Tots Move & Groove",
        event_date=date(2026, 7, 8),
        source=source,  # type: ignore[arg-type]
    )
    assert c.source == source


@pytest.mark.parametrize("source", VISION_SOURCES)
def test_vision_source_has_merge_priority(source: str) -> None:
    # Residue sources -> they lose to richer feeds, but must be enumerated.
    assert source in EVENT_SOURCE_PRIORITY
    assert EVENT_SOURCE_PRIORITY[source] >= EVENT_SOURCE_PRIORITY["go_lake_havasu"]

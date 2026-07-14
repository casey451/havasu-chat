"""Title-contamination guard: an OCR merge of two adjacent P&R calendar cells
("Kids & Clay Kids - Pickleball") mixes two disjoint activity types and must be
HELD (never publishable), while single-activity titles pass unflagged."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.contrib.lhc_parks_rec_calendar import (
    GalleryImage,
    row_to_event_record,
    title_looks_merged,
)
from app.contrib.vision_calendar import VisionEventRow

_MERGED = [
    "Kids & Clay Kids - Pickleball",
    "Clay Class & Pickleball Open Play",
    "Acrylic Painting / Dodgeball",
    "Line Dancing & Kids Kickball",
]
_CLEAN = [
    "Adult Intro to Watersports Camp - Kayak Day",
    "Mac & Cheese Classes",
    "Glow in the Dark Pickleball",
    "Line Dancing",
    "Kids Clay Series",
    "Back to School - Kids Craft Fair",
    "E-Sports",
    "Science in the Park - Ice Cream in a Bag",
    "Adult Intro to Acrylic Painting",
    "Red, White, & Blue Splash Pad Party",
]


@pytest.mark.parametrize("title", _MERGED)
def test_merged_titles_flagged(title: str) -> None:
    assert title_looks_merged(title) is True


@pytest.mark.parametrize("title", _CLEAN)
def test_clean_titles_not_flagged(title: str) -> None:
    assert title_looks_merged(title) is False


def _row(title: str) -> VisionEventRow:
    return VisionEventRow(
        title=title, event_date=date(2026, 7, 23), start_time=time(12, 30),
        end_time=time(14, 0), location=None, cost=None, audience=None, notes=None,
        confidence=0.95, source_cell="c1", should_hide=False,
    )


_REF = GalleryImage(url="https://x/img.png", title="July-2026-Calendar",
                    document_id="11284", is_calendar=True, month=7, year=2026)


def test_row_with_merged_title_is_held() -> None:
    # confidence high, venue fine — the ONLY reason to hold is the merged title.
    rec = row_to_event_record(_row("Kids & Clay Kids - Pickleball"), _REF,
                              source="parks_rec_calendar", kind="calendar")
    assert rec.raw["should_hide"] is True


def test_row_with_clean_title_not_held() -> None:
    rec = row_to_event_record(_row("Kids Clay Series"), _REF,
                              source="parks_rec_calendar", kind="calendar")
    assert rec.raw["should_hide"] is False

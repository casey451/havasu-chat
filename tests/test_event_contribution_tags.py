"""event_payload_to_contribution carries payload.tags through the review queue.

Regression for the split_finger tags=[] bug (2026-07-14): a review-gated scraper's
payload.tags were dropped when the payload became a pending contribution, so manual
approval published the event with no tags / no derived category. The fix emits a
``Categories:`` notes line that the approver recovers and the description cleaner
strips back out.
"""

from __future__ import annotations

import importlib.util
from datetime import date, time
from pathlib import Path

from app.events.description_clean import clean_event_description
from app.events.scrapers.base import EventPayload, event_payload_to_contribution

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "approve_pending_events", _ROOT / "scripts" / "approve_pending_events.py"
)
assert _SPEC and _SPEC.loader
_APPROVE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_APPROVE)


def _payload(**kw) -> EventPayload:
    base = dict(
        name="Stength/Conditioning/Agility",
        entity_type="event",
        source="split_finger",
        start_date=date(2026, 7, 20),
        start_time=time(15, 30),
        venue_name="Split Finger Athletics",
        description="A recurring strength class.",
        event_url="https://book.runswiftapp.com/x",
        tags=["sports", "fitness"],
    )
    base.update(kw)
    return EventPayload(**base)


def test_tags_emitted_as_categories_notes_line() -> None:
    c = event_payload_to_contribution(_payload(), scrape_source="split_finger")
    assert "Venue: Split Finger Athletics" in (c.submission_notes or "")
    assert "Categories: sports, fitness" in (c.submission_notes or "")


def test_approver_recovers_the_tags() -> None:
    c = event_payload_to_contribution(_payload(), scrape_source="split_finger")
    assert _APPROVE._tags_from_notes(c.submission_notes) == ["sports", "fitness"]


def test_categories_line_is_stripped_from_public_description() -> None:
    c = event_payload_to_contribution(_payload(), scrape_source="split_finger")
    cleaned = clean_event_description(c.submission_notes)
    assert "Categories:" not in cleaned
    assert "Venue:" not in cleaned
    assert "recurring strength class" in cleaned.lower()


def test_no_tags_leaves_notes_unchanged() -> None:
    # Backward-compatible: without tags, only the Venue header is present (the
    # prior behaviour), so existing rows/tests are unaffected.
    c = event_payload_to_contribution(_payload(tags=[]), scrape_source="split_finger")
    notes = c.submission_notes or ""
    assert "Categories:" not in notes
    assert notes.startswith("Venue: Split Finger Athletics")

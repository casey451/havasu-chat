"""Tag hygiene + keyword class-tagging on event ingest (no DB, no HTTP)."""

from __future__ import annotations

from datetime import date, time

from app.contrib.event_ingest import _keyword_tags, _normalize_tags, _tags
from app.contrib.event_record import EventRecord


def _rec(title: str, tags: list[str] | None = None) -> EventRecord:
    return EventRecord(source="allevents", title=title, start_date=date(2026, 7, 1), tags=tags or [])


def test_normalize_drops_placeholders_and_dedupes_case() -> None:
    out = _normalize_tags(["Events", "events", "Select Category", "  ", "Yoga", "yoga"])
    assert out == ["events", "yoga"]  # case-folded, deduped, junk dropped


def test_keyword_tags_route_martial_arts_to_classes() -> None:
    tags = _keyword_tags("Kids BJJ / Jiu-Jitsu Fundamentals at Bridge City Combat")
    assert "martial-arts" in tags
    assert "classes-sports-recreation" in tags
    assert "family" in tags  # "kids"


def test_keyword_tags_fitness_and_music() -> None:
    assert "fitness" in _keyword_tags("Sunrise Yoga Flow")
    assert "classes-sports-recreation" in _keyword_tags("Sunrise Yoga Flow")
    music = _keyword_tags("Live Music at the Nautical")
    assert "music" in music
    assert "classes-sports-recreation" not in music  # a concert is not a class


def test_tags_merges_clean_base_with_derived() -> None:
    rec = _rec("Pickleball Open Play", tags=["Events", "Select Category"])
    out = _tags(rec)
    assert "events" in out and "select category" not in out
    assert "sports" in out and "classes-sports-recreation" in out


def test_tags_falls_back_to_events_when_nothing_signals() -> None:
    assert _tags(_rec("Community Potluck Gathering")) == ["events"]


def test_tags_preserves_explicit_civic_tags() -> None:
    rec = EventRecord(
        source="legistar",
        title="City Council Meeting",
        start_date=date(2026, 7, 1),
        tags=["civic", "government", "meeting"],
    )
    out = _tags(rec)
    assert {"civic", "government", "meeting"}.issubset(set(out))


# ----- ingest guards: blocked organizers + pending-dedup (2026-06-06 queue) ---


def test_blocked_organizer_is_skipped() -> None:
    """Broadcast-bot organizers must never reach the review queue."""
    from app.contrib.event_ingest import ingest_event_records

    rec = EventRecord(
        source="allevents",
        title="UFC 999: Someone vs. Someone Else",
        start_date=date(2026, 12, 1),
        start_time=time(19, 0),
        venue_name="Buffalo Wild Wings",
        url="https://allevents.in/lake-havasu-city/ufc-999/1",
        description="Watch the fights live on every screen." * 2,
        raw={"organizer": "One Stop Entertainment"},
    )
    counts = ingest_event_records([rec], source="allevents", dry_run=False)
    assert counts.skipped_blocked == 1
    assert counts.inserted_pending == 0
    assert counts.errors == 0


def test_rerun_does_not_duplicate_pending_rows() -> None:
    """Consecutive scrape runs must not re-insert the same pending contribution
    (the 2026-06-06 review queue held 41 duplicates from exactly this)."""
    import uuid as _uuid

    from app.contrib.event_ingest import ingest_event_records

    suf = _uuid.uuid4().hex[:8]
    rec = EventRecord(
        source="allevents",
        title=f"Test Pending Dedup Concert {suf}",
        start_date=date(2026, 12, 2),
        start_time=time(20, 0),
        venue_name="Test Venue Lounge",
        url=f"https://allevents.in/lake-havasu-city/test-{suf}/1",
        description="A very testable evening of regression music." * 2,
    )
    first = ingest_event_records([rec], source="allevents", dry_run=False)
    second = ingest_event_records([rec], source="allevents", dry_run=False)
    assert first.inserted_pending == 1
    # The re-run lands as either a pending-dedup skip or a reconciler merge —
    # what matters is that no second pending row is created.
    assert second.inserted_pending == 0
    assert second.skipped_existing_pending + second.merged_duplicate == 1


def test_jsonld_unescapes_entities_and_captures_organizer() -> None:
    from app.contrib.event_record import parse_jsonld_events

    html_page = """
    <html><head><script type="application/ld+json">
    {"@type": "Event", "name": "Jonny &amp; The Be Goods",
     "startDate": "2026-12-03T19:00:00",
     "organizer": {"@type": "Organization", "name": "One Stop Entertainment"},
     "location": {"@type": "Place", "name": "Lighthouse Lounge"},
     "description": "Rock &amp; roll all night."}
    </script></head><body></body></html>
    """
    recs = parse_jsonld_events(html_page, source="allevents")
    assert len(recs) == 1
    assert recs[0].title == "Jonny & The Be Goods"
    assert recs[0].description == "Rock & roll all night."
    assert recs[0].raw.get("organizer") == "One Stop Entertainment"

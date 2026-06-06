"""Tag hygiene + keyword class-tagging on event ingest (no DB, no HTTP)."""

from __future__ import annotations

from datetime import date

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

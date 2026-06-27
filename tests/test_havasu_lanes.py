"""Havasu Lanes scraper — parser + spec generation (no network).

The HTML fixture is a saved snapshot of havasulanesaz.com/SPECIALS; a site
redesign that drops the Rock & Bowl line fails these loudly instead of silently
shipping a stale (or empty) calendar.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.contrib.havasu_lanes import (
    EVENT_TITLE,
    cosmic_bowling_specs,
    parse_rock_and_bowl,
    visible_text,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "havasu_lanes" / "specials.html"


def _specials_text() -> str:
    return visible_text(_FIXTURE.read_text(encoding="utf-8"))


def test_visible_text_strips_script_and_style() -> None:
    txt = _specials_text()
    assert "tracking" not in txt  # <script> dropped
    assert "color: #fff" not in txt  # <style> dropped
    assert "ROCK & BOWL" in txt


def test_parse_rock_and_bowl_from_fixture() -> None:
    rb = parse_rock_and_bowl(_specials_text())
    assert rb is not None
    assert rb.weekdays == (4, 5)  # Friday, Saturday
    assert rb.start == "18:00"
    assert rb.end == "23:00"  # "to close" -> Fri/Sat 11 PM close
    assert rb.pricing and "$18" in rb.pricing and "$26" in rb.pricing


def test_parse_rock_and_bowl_miss_returns_none() -> None:
    assert parse_rock_and_bowl("Open daily noon to nine. Leagues forming now.") is None
    # Rock & Bowl named but no day/time -> still a miss (don't invent a schedule).
    assert parse_rock_and_bowl("Ask about our Rock & Bowl nights!") is None


def test_specs_cover_only_matching_weekdays() -> None:
    rb = parse_rock_and_bowl(_specials_text())
    # Two weeks from a Friday (2026-06-26): Fri 26, Sat 27, Fri 7-3, Sat 7-4.
    specs = cosmic_bowling_specs(rb, today=date(2026, 6, 26), window_days=14)
    assert [s.date for s in specs] == [
        date(2026, 6, 26), date(2026, 6, 27), date(2026, 7, 3), date(2026, 7, 4)
    ]
    for s in specs:
        assert s.date.weekday() in (4, 5)
        assert s.title == EVENT_TITLE
        assert s.start_time == "18:00" and s.end_time == "23:00"
        assert not s.all_day


def test_specs_source_url_matches_existing_catalog_scheme() -> None:
    # Idempotency hinges on this exact scheme (matches the rows already loaded),
    # so a re-run dedupes instead of creating a twin per date.
    specs = cosmic_bowling_specs(
        parse_rock_and_bowl(_specials_text()), today=date(2026, 6, 26), window_days=3
    )
    assert specs[0].event_url == (
        "https://www.havasulanesaz.com/specials?occ=rock-and-bowl-2026-06-26"
    )


def test_specs_tags_are_all_ages_not_youth() -> None:
    # Casey 2026-06-26: glow bowling is an all-ages venue event, NOT youth — so
    # the scraper stamps "all ages"/"family", never "kids"/"audience:youth"
    # (which would peel it into a "Youth Bowling" sub-section). See
    # app.events.family_filter.is_youth_event.
    spec = cosmic_bowling_specs(
        parse_rock_and_bowl(_specials_text()), today=date(2026, 6, 26), window_days=2
    )[0]
    assert "all ages" in spec.tags and "family" in spec.tags
    assert "kids" not in spec.tags and "audience:youth" not in spec.tags


def test_parse_miss_yields_no_specs() -> None:
    assert cosmic_bowling_specs(None, today=date(2026, 6, 26)) == []

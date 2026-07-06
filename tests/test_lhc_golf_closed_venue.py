"""S4 liveness guard for curated golf venues (2026-07-06).

A curated venue set can silently keep listing a course that permanently closed
(Havasu Island Golf Course shut down in 2018 but was still emitted as "Open
daily"). :data:`CLOSED_VENUES` + :func:`is_closed_venue` fence closed venues out
of every emit path — the facility set, the hours-event specs, and the curated
"today hours" calendar rows — so a closed business is never shown as open.
"""

from __future__ import annotations

from datetime import date

from app.contrib.lhc_golf import (
    CLOSED_VENUES,
    DEFAULT_CATEGORY_SLUG,
    GOLF_LEAF_URL,
    golf_facilities,
    golf_hours_event_specs,
    golf_hours_rows,
    is_closed_venue,
)

_MONDAY = date(2099, 7, 13)


# --- T1.2: curated golf targets the SERVED leaf, not the legacy department ---


def test_default_category_slug_targets_served_golf_leaf() -> None:
    # The loader resolves this to Provider.category_id. It must be the served
    # ``golf-courses`` leaf, not the empty legacy ``outdoors-parks-trails`` dept.
    assert DEFAULT_CATEGORY_SLUG == "golf-courses"


def test_curated_golf_links_target_served_leaf_not_stale_slug() -> None:
    # The fallback link (no venue website) must point at the canonical golf leaf,
    # never the 404ing ``/categories/outdoors-parks-trails/golf`` slug.
    assert GOLF_LEAF_URL.endswith("/categories/things-to-do-and-attractions/golf-courses")
    assert "outdoors-parks-trails/golf" not in GOLF_LEAF_URL

    # No emitted row/spec may carry the stale slug as its link.
    for r in golf_hours_rows(_MONDAY):
        assert "outdoors-parks-trails/golf" not in r["url"]
    for s in golf_hours_event_specs(today=_MONDAY):
        assert "outdoors-parks-trails/golf" not in s.event_url


def test_closed_venue_match_is_name_normalized() -> None:
    assert is_closed_venue("Havasu Island Golf Course")
    # case / trailing punctuation / spacing fold to the same key
    assert is_closed_venue("havasu island golf course.")
    assert is_closed_venue("  Havasu   Island  Golf Course ")
    # a live venue is not flagged
    assert not is_closed_venue("Lake Havasu Golf Club")
    assert not is_closed_venue("")


def test_havasu_island_is_registered_closed() -> None:
    assert any(is_closed_venue(n) for n in CLOSED_VENUES)
    assert is_closed_venue("Havasu Island Golf Course")


def test_golf_facilities_excludes_closed_venues() -> None:
    names = {v.name for v in golf_facilities()}
    assert "Havasu Island Golf Course" not in names
    # the live venues are still present
    assert "Lake Havasu Golf Club" in names
    assert "Golf n' Brews" in names
    assert "Back Nine Golf" in names


def test_hours_event_specs_never_emit_a_closed_venue() -> None:
    specs = golf_hours_event_specs(today=_MONDAY)
    assert specs, "expected curated golf hours event specs"
    assert all(not is_closed_venue(s.location_name) for s in specs)
    assert all("Havasu Island" not in s.title for s in specs)


def test_curated_hours_rows_never_render_a_closed_venue() -> None:
    rows = golf_hours_rows(_MONDAY)
    assert rows, "expected curated golf hours rows"
    assert all(not is_closed_venue(r["venue"]) for r in rows)
    assert all("Havasu Island" not in r["title"] for r in rows)

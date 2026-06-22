"""Pure-logic tests for the P1 gated-cleanup dry-runs (no DB, no network).

Covers the decision cores that drive what would be written under ``--apply``:
the River Scene noon classifier and the event-dup pairing/keeper choice.
"""

from __future__ import annotations

from datetime import date, time

from scripts.dryrun_event_dups_2026_06 import EventLite, _order_keep_dup, _richness, find_pairs
from scripts.dryrun_river_scene_noon_2026_06 import classify_noon


def test_classify_noon_buckets() -> None:
    assert classify_noon(False, None) == "unverified"
    assert classify_noon(True, None) == "fabricated"
    assert classify_noon(True, time(12, 0)) == "legit_noon"
    assert classify_noon(True, time(9, 0)) == "stale_noon"


def _ev(**kw) -> EventLite:
    base = dict(
        id="x",
        title="T",
        source="admin",
        date=date(2026, 6, 23),
        start_time=time(16, 30),
        end_time=None,
        location_name="V",
        source_url=None,
        has_image=False,
        desc_len=0,
    )
    base.update(kw)
    return EventLite(**base)  # type: ignore[arg-type]


def test_richer_record_is_kept() -> None:
    rich = _ev(id="rich", end_time=time(18, 30), has_image=True, desc_len=295)
    thin = _ev(id="thin", end_time=None, has_image=False, desc_len=0)
    keep, dup = _order_keep_dup(rich, thin)
    assert (keep.id, dup.id) == ("rich", "thin")
    # order-independent
    keep2, dup2 = _order_keep_dup(thin, rich)
    assert (keep2.id, dup2.id) == ("rich", "thin")
    assert _richness(rich) > _richness(thin)


def test_game_night_pair_collapses_keeping_rich_twin() -> None:
    rich = _ev(
        id="1d3f3cbf",
        title="Hav-A-Sis Game Night",
        source="go_lake_havasu",
        end_time=time(18, 30),
        has_image=True,
        location_name="Grapes N Grains",
        source_url="https://www.golakehavasu.com/events/hav-a-sis-game-night",
        desc_len=295,
    )
    thin = _ev(
        id="3bb7d75b",
        title="HAVASIS GAME NIGHT",
        source="river_scene_import",
        end_time=None,
        has_image=False,
        location_name="Grapes N Grains 2187 McCulloch Blvd",
        source_url="https://riverscenemagazine.com/events/havasis-game-night-2",
        desc_len=0,
    )
    pairs = find_pairs([rich, thin])
    assert len(pairs) == 1
    assert pairs[0].keep.id == "1d3f3cbf"
    assert pairs[0].dup.id == "3bb7d75b"


def test_same_venue_different_time_not_merged() -> None:
    """Matinee vs evening of the same title at the same venue stay distinct."""
    matinee = _ev(id="m", title="Clifford Movie", start_time=time(9, 0), location_name="Star Cinemas")
    evening = _ev(id="e", title="Clifford Movie", start_time=time(19, 0), location_name="Star Cinemas")
    assert find_pairs([matinee, evening]) == []


def test_tbd_time_rows_are_not_same_time_matches() -> None:
    a = _ev(id="a", start_time=time(0, 0))
    b = _ev(id="b", start_time=time(0, 0))
    assert find_pairs([a, b]) == []


def test_different_titles_same_slot_not_merged() -> None:
    a = _ev(id="a", title="Yoga Flow", location_name="The Studio")
    b = _ev(id="b", title="Powerlifting Meet", location_name="The Studio")
    assert find_pairs([a, b]) == []

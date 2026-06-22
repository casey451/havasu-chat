"""P2: first-class event-TYPE classification (live_music / comedy / car_show)."""

from __future__ import annotations

from app.contrib.event_ingest import _tags
from app.contrib.event_record import EventRecord
from app.events.event_type_tags import (
    classify_event_type,
    event_type_label,
    is_strong_live_music,
)


def _t(title, **kw):
    return classify_event_type(title=title, **kw)


def test_confirmed_live_targets_read_as_their_type():
    # Bare band names (no music word) — the confirmed-live targets.
    for name in ("Sacred Stone", "Sparks After Midnight", "The Brew Band", "Retro Riot"):
        assert "live_music" in _t(name), name
        assert event_type_label(name) == "Live Music", name
    # Comedy reads as comedy.
    assert _t("Top Goons: A First Class Night of Comedy") == {"comedy"}
    assert event_type_label("Top Goons: A First Class Night of Comedy") == "Comedy"


def test_venue_and_keyword_paths():
    assert "live_music" in _t("A-Z", venue="Lighthouse Lounge")  # music venue
    assert "live_music" in _t("Tribute Night", description="live band concert")
    assert _t("Open Mic Comedy Night") == {"comedy"}
    assert "comedy" in _t("Hamlet", description="a play at the theater")  # theater
    assert _t("Motor Madness Car Show", tags=["automotive"]) == {"car_show"}


def test_guards_block_false_positives():
    # Civic agenda mentioning a keyword is never music/comedy.
    assert _t("City Council Meeting", tags=["civic", "government"]) == set()
    assert _t("Board of Adjustment", description="DJ adjustment item") == set()
    # Kids/all-ages DJ dance party is not a Music & nightlife listing.
    assert _t("Glow in the Park - All Ages", description="kids DJ dance") == set()
    # A car show with a DJ stays a car show (no live_music).
    assert _t("Cruise-in Car Show", description="DJ spinning all day") == {"car_show"}
    # Plain lake paddle: nothing.
    assert _t("Sunset Paddle", venue="Lake") == set()


def test_strong_live_music_excludes_dj_and_venue_only():
    assert is_strong_live_music("The Brew Band")  # curated + "band"
    assert is_strong_live_music("Acoustic Evening")  # strong keyword
    assert not is_strong_live_music("DJ Spinz Late Night", venue="Lighthouse Lounge")
    assert not is_strong_live_music("Karaoke Night", venue="Lighthouse Lounge")


def test_label_prefers_live_music_then_comedy_then_none():
    assert event_type_label("Yoga in the Park") is None
    assert event_type_label("Sacred Stone", ["live_music"]) == "Live Music"
    assert event_type_label("Top Goons Comedy") == "Comedy"


def test_ingest_stamps_type_tags_additively():
    rec = EventRecord(
        source="allevents",
        title="Sacred Stone",
        start_date=None,
        venue_name="Lighthouse Lounge",
        description="",
    )
    tags = _tags(rec)
    assert "live_music" in tags
    assert "music" in tags  # the coarse tag stays (tier routing still keys on it)

    civic = EventRecord(
        source="legistar", title="City Council Meeting", start_date=None, tags=["civic"]
    )
    assert "live_music" not in _tags(civic)
    assert "comedy" not in _tags(civic)

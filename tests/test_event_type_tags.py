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


def test_sports_play_never_reads_as_comedy():
    # Post-deploy crawl FP: "Pickleball Open Play" (a daily sports row) was labeled
    # Comedy off the word "Play". No sports "play" may trigger comedy.
    for title in (
        "Pickleball Open Play",
        "Open Play",
        "Volleyball Open Play",
        "Open Gym",
        "Player Showcase",
        "Playground Fun Day",
        "Toddler Play Group",
    ):
        assert "comedy" not in _t(title), title
        assert event_type_label(title) is None, title
    # Real comedy/theater still reads as comedy.
    assert event_type_label("Top Goons: A Night of Comedy") == "Comedy"
    assert event_type_label("Hamlet at the Playhouse") == "Comedy"
    assert event_type_label("Stage Play: Our Town") == "Comedy"


def test_theatre_in_a_band_name_is_music_not_comedy():
    # Audit FP: "Elective Theatre Acoustic Duo" (a music act) was tagged Comedy off
    # "Theatre". A theater word with a live-music signal stays music.
    types = _t("Elective Theatre Acoustic Duo", venue="Lighthouse Lounge")
    assert "comedy" not in types and "live_music" in types
    assert event_type_label("Elective Theatre Acoustic Duo", venue="Lighthouse Lounge") == "Live Music"


def test_live_music_badge_needs_a_performance_signal_not_just_a_venue():
    # Audit FP: a Paint & Sip / Bingo / food night AT a music venue was badged
    # "Live Music" off the venue alone. The badge needs a real performance signal.
    for title in ("Paint & Sip at Mudshark Brewery", "Bingo", "Troy's Alligator Feed"):
        assert event_type_label(title, ["music"], "Lighthouse Lounge") is None, title
    # Real performances (keyword / curated act) still badge.
    assert event_type_label("Crosscutt Live at the Naked Turtle") == "Live Music"
    assert event_type_label("FOREIGNER & STYX TRIBUTE NIGHT") == "Live Music"
    assert event_type_label("Sacred Stone", venue="Lighthouse Lounge") == "Live Music"


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


def test_activity_tag_suppresses_weak_venue_only_music_signal():
    # 2026-07-01 search N3: a billiards row (activity:billiards) whose blurb only
    # MENTIONS the venue's other nights ("...also hosts a Monday-night dance
    # party") was retyped Live Music off that stray weak signal, and leaked into
    # a "live music tonight" search. The structured activity tag must win.
    assert (
        event_type_label(
            "Billiards - Lady Lee's Billiards Hall",
            ["activity:billiards", "facet:hours"],
            "Lady Lee's Billiards Hall",
            "Billiards hall (also hosts a Monday-night dance party). Call for hours.",
        )
        is None
    )
    # A golf clinic is not live music off a weak venue-night mention ("DJ after").
    assert event_type_label("Junior Golf Clinic", ["activity:golf"], "", "stay for the DJ after") is None


def test_activity_tag_yields_to_authoritative_music_signal():
    # The guard only suppresses a WEAK/venue-only signal. An authoritative signal
    # (durable music tag, a real band/concert, or a curated act) still types
    # Live Music even when a structured activity tag is present.
    assert (
        event_type_label(
            "Lady Lee's Monday Night Dance Party",
            ["events", "music", "activity:dance"],
            "Lady Lee's",
        )
        == "Live Music"
    )
    assert event_type_label("Live Band Night", ["activity:arts"], "The Tavern", "live band") == "Live Music"


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

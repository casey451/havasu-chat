"""Family-mode event filter — positive kid/family match with adult veto."""

from __future__ import annotations

from app.events.family_filter import is_family_event, is_youth_event


def test_kid_titles_match() -> None:
    for title in (
        "Open Swim",
        "Free Family Swim Sponsored by: Abundant Grace Church",
        "Baby Sitting Class June 6",
        "Story Time at the Library",
        "Summer Kids Camp",
        "Grace Arts Live Presents The SpongeBob Musical Youth Edition",
        "Tacos - A family Cooking Party",
        "Teen Game Night",
        "Skate Night at SARA Park",
    ):
        assert is_family_event(title), title


def test_youth_class_titles_match() -> None:
    # Gym / dance / dojo class names with no explicit "kids" word — these used
    # to file under Fitness & classes instead of Kids & Family.
    for title in (
        "Tiny Tumblers",
        "Tumbling",
        "Lil Firecrackers",
        "Littles Gi",
        "Little Ninjas",
        "Little Dragons",
        "Gymtots",
        "Pee Wee Soccer",
        "Preschool Storytime",
        "Pre-K Dance",
        "Mommy & Me Yoga",
        "Creative Movement",
    ):
        assert is_family_event(title), title


def test_ambiguous_adult_titles_still_excluded() -> None:
    # High-precision: a bare "little"/"mini" adult row must NOT read as family.
    for title in (
        "A Little Lunch Music",
        "Mini Cooper Car Show",
        "Little Italy Wine Dinner",  # has "little" + adult "wine" veto
    ):
        assert not is_family_event(title), title


def test_adult_titles_do_not_match() -> None:
    for title in (
        "Polymer Clay Adults",
        "Sippin' with the Somm",
        "Aqua Challenge Margie",
        "Tai Chi Vince",
        "Motion & Mobility Margie",
        "Wine Wednesday",
        "Beer Fest 21+",
        "World Elder Abuse Awareness Day",
        "Board of Adjustment Meeting",
    ):
        assert not is_family_event(title), title


def test_adult_marker_vetoes_positive_match() -> None:
    # "family" + adult marker → vetoed.
    assert not is_family_event("Family Brewery Tour 21+")
    assert not is_family_event("Kids' Wine & Paint")


def test_audience_tags_match_without_title_signal() -> None:
    assert is_family_event("Tumbling Session", tags=["youth"])
    assert is_family_event("Craft Hour", tags=["Family"])
    assert not is_family_event("Craft Hour", tags=["adult"])
    assert not is_family_event("Craft Hour", tags=None)
    assert not is_family_event(None)


# ── is_youth_event: stricter than is_family_event (Casey 2026-06-26) ──────────
def test_youth_excludes_all_ages_venue_events() -> None:
    # All-ages venue events: family-friendly (is_family_event True) but NOT youth
    # — they must not peel into a "Youth <activity>" sub-section.
    for title, tags in (
        ("Cosmic Bowling", ["family", "kids", "all ages", "activity:bowling"]),
        ("Glow in the Park - All Ages", ["family", "kids", "all ages"]),
        ("Toptracer Range - Family Night Golf", ["family", "kids", "all ages"]),
        ("Line Dancing", ["family"]),
    ):
        assert is_family_event(title, tags=tags), title
        assert not is_youth_event(title, tags=tags), title


def test_youth_keeps_genuinely_kid_events() -> None:
    assert is_youth_event("Junior Jump Time (Ages 6 & Under)", tags=["kids", "family"])
    assert is_youth_event("BMX Local Race", tags=["youth", "kids", "family"])
    assert is_youth_event("Kids Intro to Pickleball - ages 8-12", tags=["youth"])
    assert is_youth_event("Tiny Tot Fridays - Story Time", tags=["family"])
    # A neutrally-titled row a loader tagged youth still counts.
    assert is_youth_event("Wrestling", tags=["youth"])


def test_youth_all_ages_tag_vetoes_kids_tag() -> None:
    # An explicit "all ages" tag wins over a stray "kids" tag (no kid title).
    assert not is_youth_event("Glow Night", tags=["kids", "all ages"])
    # Adult titles never youth, and a kid title still wins outright.
    assert not is_youth_event("Adult Watercolors", tags=["kids"])
    assert is_youth_event("Kids Camp All Ages Welcome", tags=["all ages"])

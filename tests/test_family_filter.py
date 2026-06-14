"""Family-mode event filter — positive kid/family match with adult veto."""

from __future__ import annotations

from app.events.family_filter import is_family_event


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

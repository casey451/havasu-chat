"""Calendar taxonomy rebuild — Phase 1 (2026-06-25): one classifier, stamped at
ingest.

``classify_activity`` is now THE single classifier across every calendar
activity (fitness + the new non-fitness arts/cooking/maker/learning/games/
theater/bowling/billiards/trampoline/family-fun). Ingest stamps exactly one
namespaced ``activity:<slug>`` tag (plus facet/audience tags) so every surface
is a pure read in Phase 2. These tags are namespaced, hence inert to the
bare-word tier classifier — Phase 1 changes no surface.
"""

from __future__ import annotations

from datetime import date

from app.contrib.event_ingest import _KEYWORD_TAGS, _tags
from app.contrib.event_record import EventRecord
from app.events.activity_taxonomy import (
    ACTIVITY_BUCKET,
    CLASS_SUBGROUPS,
    NONFITNESS_SUBGROUPS,
    SUBGROUP_SLUGS,
    activity_bucket,
    classify_activity,
    event_activity_tags,
)

_CLASS_LABELS = {label for label, _hints in CLASS_SUBGROUPS}


# ── classify_activity: the new non-fitness activities ─────────────────────────
def test_nonfitness_activities_classify_to_their_slug() -> None:
    cases = {
        "Stained Glass Summer Painting": "arts",
        "Polymer Clay Jewelry": "arts",
        "Mason Jar Terrarium": "arts",
        "Open Arts & Crafts": "arts",
        "Windchimes": "arts",
        "Paint & Sip": "arts",
        "Taco Cooking Class (Carne Asada)": "cooking",
        "Mini Maker Cake Pop": "maker",
        "Party Bridge": "games",
        "Pinochle": "games",
        "Mexican Train Dominoes": "games",
        "Rowdy Bingo": "games",
        "Ping Pong": "games",
        "Open Billiards": "billiards",
        "Cosmic Bowling": "bowling",
        "Family Glow Bowling": "bowling",
        "Glow in the Park": "trampoline",
        "SpongeBob Musical": "theater",
        "Genealogy Workshop": "learning",
    }
    for title, slug in cases.items():
        assert classify_activity(title) == slug, title


# ── disambiguation guards (from the layout doc) ───────────────────────────────
def test_disambiguation_guards() -> None:
    # Movement, not instruction-craft.
    assert classify_activity("Line Dancing") == "dance"
    # A fitness class with a generic-learning word stays fitness.
    assert classify_activity("Yoga Workshop") == "yoga"
    # Paint & Sip is arts, never a workout.
    assert classify_activity("Paint & Sip Night") == "arts"
    # Trampoline moved to family-fun cluster; the specific keyword wins over the
    # fitness Gymnastics keyword that used to capture it.
    assert classify_activity("Open Trampoline Jump Time") == "trampoline"
    # Pickleball keeps its fitness slug.
    assert classify_activity("Pickleball Round Robin") == "pickleball"
    # disc golf must NOT be ball-golf; stays a fitness team/field sport.
    assert classify_activity("Disc Golf League") == "sports-racing"
    # Non-activity rows carry no activity tag.
    assert classify_activity("Lake Havasu Farmers Market") is None


# ── bucket mapping ────────────────────────────────────────────────────────────
def test_activity_bucket_mapping() -> None:
    assert activity_bucket("arts") == "learn"
    assert activity_bucket("cooking") == "learn"
    assert activity_bucket("learning") == "learn"
    assert activity_bucket("theater") == "music"
    assert activity_bucket("games") == "events"
    assert activity_bucket("bowling") == "events"
    assert activity_bucket("trampoline") == "events"
    assert activity_bucket("yoga") == "classes"
    assert activity_bucket("pickleball") == "classes"
    assert activity_bucket(None) is None


# ── facets + audience ─────────────────────────────────────────────────────────
def test_special_facet_for_themed_sessions() -> None:
    tags = event_activity_tags("Cosmic Bowling")
    assert "activity:bowling" in tags
    assert "facet:special" in tags
    glow = event_activity_tags("Glow in the Park")
    assert "activity:trampoline" in glow and "facet:special" in glow


def test_competition_facet() -> None:
    tags = event_activity_tags("Pickleball Round Robin")
    assert "activity:pickleball" in tags
    assert "facet:competition" in tags
    assert "facet:competition" in event_activity_tags("Summer Pickleball League")


def test_audience_facets() -> None:
    assert "audience:senior" in event_activity_tags("Pinochle", tags=["senior"])
    assert "audience:youth" in event_activity_tags("Youth Dodgeball")
    # A senior-tagged craft carries both the activity and the senior gate signal.
    sr = event_activity_tags("Open Arts & Crafts", tags=["senior"])
    assert "activity:arts" in sr and "audience:senior" in sr


def test_one_activity_tag_per_row() -> None:
    tags = event_activity_tags("Stained Glass Painting Workshop")
    activities = [t for t in tags if t.startswith("activity:")]
    assert activities == ["activity:arts"]


# ── ingest stamps the tag ─────────────────────────────────────────────────────
def _rec(title: str, tags: list[str] | None = None) -> EventRecord:
    return EventRecord(
        source="test",
        title=title,
        start_date=date(2026, 7, 1),
        venue_name="Lake Havasu Senior Center",
        url="https://example.com/e",
        description="A test event.",
        tags=tags or [],
    )


def test_ingest_tags_stamps_activity() -> None:
    assert "activity:arts" in _tags(_rec("Stained Glass Summer Painting"))
    assert "activity:games" in _tags(_rec("Mexican Train Dominoes"))
    bowling = _tags(_rec("Cosmic Bowling"))
    assert "activity:bowling" in bowling and "facet:special" in bowling
    # A plain market gets no activity tag (falls through to the coarse tags).
    assert not [t for t in _tags(_rec("Farmers Market")) if t.startswith("activity:")]


# ── invariants: no drift ──────────────────────────────────────────────────────
def test_every_fitness_slug_has_label_and_bucket() -> None:
    # SUBGROUP_SLUGS maps label -> slug; every label is a real CLASS_SUBGROUPS
    # label and every slug has a top-level bucket.
    for label, slug in SUBGROUP_SLUGS.items():
        assert label in _CLASS_LABELS, label
        assert slug in ACTIVITY_BUCKET, slug
        assert ACTIVITY_BUCKET[slug] == "classes"


def test_every_activity_slug_has_a_bucket() -> None:
    for slug, _hints in NONFITNESS_SUBGROUPS:
        assert slug in ACTIVITY_BUCKET, slug
    # learning is the generic fallback slug.
    assert ACTIVITY_BUCKET["learning"] == "learn"


def test_keyword_tags_never_disagree_with_classifier() -> None:
    # No DRIFT (directional): the classifier must never put a coarse fitness/sport
    # keyword into a non-"classes" bucket, nor a coarse "arts" keyword into a
    # non-"learn" bucket. The classifier MAY decline (None) on a coarse substring
    # like "paint " / "craft" — those are routing substrings, not full activity
    # phrases (bare "craft" would wrongly catch "craft beer") — so None is allowed;
    # only an actual disagreement fails.
    for needles, tags in _KEYWORD_TAGS:
        if "classes-sports-recreation" in tags:
            for kw in needles:
                slug = classify_activity(kw)
                # The generic instruction words (workshop/seminar/lecture) carry
                # the LEGACY coarse classes tag but correctly classify as
                # "learning" (→ learn) under the new taxonomy; the legacy tag stays
                # for now (Phase 1 = no surface change) and Phase 2 routes by the
                # activity:learning tag. That overlap is expected, not drift.
                if slug is not None and slug != "learning":
                    assert ACTIVITY_BUCKET[slug] == "classes", (kw, slug)
        if tags == ("arts",):
            for kw in needles:
                slug = classify_activity(kw)
                if slug is not None:
                    assert ACTIVITY_BUCKET[slug] == "learn", (kw, slug)


def test_representative_fitness_keywords_route_to_classes() -> None:
    for kw in ("yoga", "pilates", "pickleball", "zumba", "crossfit", "tai chi",
               "bmx", "karate", "ballet", "gymnastics"):
        slug = classify_activity(kw)
        assert slug is not None and ACTIVITY_BUCKET[slug] == "classes", kw

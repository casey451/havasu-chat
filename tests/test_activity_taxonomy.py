"""P1: the shared activity-type taxonomy (retired from the render layer)."""

from app.events.activity_taxonomy import (
    FALLBACK_LABEL,
    activity_slug,
    classify_class_subgroup,
    split_class_subgroups,
)


def test_classify_known_types():
    assert classify_class_subgroup("Amalaya Hot Yoga") == "Yoga"
    assert classify_class_subgroup("Beginner Reformer Pilates") == "Pilates"
    assert classify_class_subgroup("Adult No-Gi") == "Martial Arts"
    assert classify_class_subgroup("Aqua Zumba") == "Aquatic fitness"
    assert classify_class_subgroup("Rec Tumbling L1-3") == "Gymnastics"
    assert classify_class_subgroup("Spin") == "Strength & Cardio"
    assert classify_class_subgroup("Pickleball Clinic") == "Pickleball"


def test_mind_body_captures_gentle_classes():
    # P1: tai chi / arthritis / low-impact are now typed, not "Other classes".
    assert classify_class_subgroup("Tai Chi for Beginners") == "Mind & Body"
    assert classify_class_subgroup("Arthritis Foundation Exercise") == "Mind & Body"
    assert classify_class_subgroup("Gentle Stretch & Mobility") == "Mind & Body"


def test_venue_wins_for_martial_arts():
    assert classify_class_subgroup("Adult Program", "Bridge City BJJ") == "Martial Arts"


def test_residue_is_named_not_silent():
    assert classify_class_subgroup("Riding Lessons") == FALLBACK_LABEL


def test_carried_forward_residual_class_routing():
    """Carried-forward finding: the three edge items the 'Other classes' drain
    left behind. Pickleball Round Robin types correctly (stays in Fitness &
    classes); Star Search and Stitchers hit the FALLBACK, so the day-view
    re-route sends them to 'Happening today' — never a stranded 'Other classes'."""
    assert classify_class_subgroup("Pickleball Round Robin") == "Pickleball"
    assert classify_class_subgroup("Havasu Star Search") == FALLBACK_LABEL
    assert classify_class_subgroup("Havasu Stitchers") == FALLBACK_LABEL


def test_activity_slug_for_tags():
    assert activity_slug("Vinyasa Yoga") == "yoga"
    assert activity_slug("Adult MMA") == "martial-arts"
    assert activity_slug("Tai Chi") == "mind-body"
    # residue has no stable activity slug
    assert activity_slug("Riding Lessons") is None


def test_split_orders_and_omits_empty():
    rows = [
        {"title": "Yoga", "venue": None},
        {"title": "Spin", "venue": None},
        {"title": "Riding Lessons", "venue": None},
    ]
    subs = split_class_subgroups(rows)
    labels = [s["label"] for s in subs]
    assert labels == ["Yoga", "Strength & Cardio", "Other classes"]
    assert all(s["count"] == len(s["rows"]) for s in subs)

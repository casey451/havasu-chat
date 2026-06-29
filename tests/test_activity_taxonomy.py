"""P1: the shared activity-type taxonomy (retired from the render layer)."""

from app.events.activity_taxonomy import (
    FALLBACK_LABEL,
    activity_bucket,
    activity_slug,
    classify_activity,
    classify_class_subgroup,
    event_activity_tags,
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


def test_sports_and_racing_subgroup():
    # Sports (BMX racing, ball/court sports) type under "Sports & Racing" instead
    # of the "Other classes" residue (Casey 2026-06-24: most "classes" are sports).
    assert classify_class_subgroup("BMX Local Race") == "Sports & Racing"
    assert classify_class_subgroup("BMX Clinic") == "Sports & Racing"
    assert classify_class_subgroup("Pump Track Open Ride") == "Sports & Racing"
    assert classify_class_subgroup("Youth Basketball League") == "Sports & Racing"
    # Pickleball keeps its own dedicated subgroup (checked before this one).
    assert classify_class_subgroup("Pickleball Round Robin") == "Pickleball"


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


def test_competition_with_stray_arts_tag_is_not_a_class():
    # Bug 1 (2026-06-26): "Yard Games & Cornhole Tournament" carries a bare `arts`
    # source tag, which used to win the arts fallback → Classes & workshops. A
    # competition is never a class/workshop or a craft → no activity slug (→ the
    # Around Town residual). Its July-4 sibling reads the same.
    assert classify_activity(
        "Yard Games & Cornhole Tournament", tags=["arts", "facet:competition"]
    ) is None
    assert classify_activity(
        "Red, White & Blue Rec Roadshow – Yard Games & Cornhole Tournament",
        tags=["arts"],
    ) is None
    # The stamped tags must NOT include an activity slug for these either.
    tags = event_activity_tags("Yard Games & Cornhole Tournament", tags=["arts"])
    assert not any(t.startswith("activity:") for t in tags)
    assert "facet:competition" in tags


def test_real_sport_competitions_keep_their_slug():
    # The competition guard only suppresses the fallback tail — a genuine sport
    # competition matched its sport slug earlier and is unchanged.
    assert classify_activity("Pickleball Round Robin") == "pickleball"
    assert classify_activity("5th Annual Charity Bowling Tournament") == "bowling"
    assert classify_activity("Member-Guest Golf Tournament") == "golf"


def test_pet_training_routes_to_learn():
    # Bug 2: an 8-week dog-obedience course has no fitness keyword and "course" is
    # (deliberately) not a generic-learning word → it used to fall to Around Town.
    # It now routes to a learn slug → Classes & workshops.
    slug = classify_activity("Dog Obedience (8-wk course, Sat @ Jack Hardie Park)")
    assert slug == "learning"
    assert activity_bucket(slug) == "learn"
    assert classify_activity("Puppy Class") == "learning"


def test_enrichment_classes_route_to_learn():
    # Desert Bloom Learning Center's after-school enrichment publishes token-less
    # titles ("Movement Lab", "History Explorers") that carried no activity slug
    # and fell to Things to Do → Around Town. The "enrichment"/"homeschool" signal
    # (and the learning-center venue backstop) now route them to learn.
    venue = "Desert Bloom Learning Center"
    for title in (
        "Movement Lab (Afternoon Enrichment)",
        "Afternoon Enrichment: History Explorers",
        "Afternoon Enrichment Workshops",
        "Morning Homeschool Learning Support",
    ):
        slug = classify_activity(title, venue)
        assert slug == "learning", title
        assert activity_bucket(slug) == "learn", title
        assert "activity:learning" in event_activity_tags(title, venue)


def test_learning_center_venue_does_not_override_a_real_fitness_class():
    # The venue backstop is a fallback only: a real yoga class at a learning
    # center stays yoga (fitness keyword wins), and a token-less title with NO
    # learning-center venue is left unclassified (no over-reach).
    assert classify_activity("Vinyasa Yoga", "Desert Bloom Learning Center") == "yoga"
    assert classify_activity("History Explorers", venue=None) is None
    # Drop-in rec / sport controls stay out of learning.
    assert classify_activity("Open Swim") != "learning"
    assert classify_activity("Pickleball Round Robin") == "pickleball"


def test_spaced_watercolors_reads_as_arts():
    # Bug 3: "Water Colors" (spaced) didn't match the one-word "watercolor" hint.
    assert classify_activity("Adult Intro to Water Colors Series") == "arts"
    # The single-word spelling still works.
    assert classify_activity("Watercolor Basics") == "arts"


def test_bread_class_reads_as_cooking():
    # Bug 3 (optional): a "Banana Bread Class" now reads as cooking.
    assert classify_activity("Kids Banana Bread Class") == "cooking"
    # The genuine cooking class is unchanged.
    assert classify_activity("Taco Cooking Class") == "cooking"


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

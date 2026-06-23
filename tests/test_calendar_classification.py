"""Calendar-classification fix-up (2026-06-23) — logic-level guards so the whole
current catalog AND future scrapes classify correctly.

Three lanes, matching the fix:
  * provider-aware class subgroup (title keyword → provider activity → residue);
  * event-vs-class routing (recurring venue social/music events leave Fitness);
  * dedup (the pre-dawn AM/PM placeholder twin collapses onto its real sibling).
"""

from __future__ import annotations

from datetime import date, time

from app.events.activity_taxonomy import (
    FALLBACK_LABEL,
    classify_class_subgroup,
    provider_activity_label,
)
from app.events.family_filter import is_family_event
from app.home.events_views import _family_subgroup, _group_for

# --------------------------------------------------------------------------- #
# 2A — provider-aware class classification
# --------------------------------------------------------------------------- #


def test_provider_activity_from_name():
    assert provider_activity_label("Amalaya Yoga", []) == "Yoga"
    assert provider_activity_label("Ballet Havasu", []) == "Dance"
    assert (
        provider_activity_label("Universal Sonics Gymnastics & All Star Cheer", [])
        == "Gymnastics"
    )
    assert provider_activity_label("Swivel & Sway Ballroom Dance", []) == "Dance"


def test_provider_activity_from_category_slug():
    # Token-less provider name ("Arizona Coast Performing Arts") → use EntityCategory.
    assert provider_activity_label("Arizona Coast Performing Arts", ["dance-studios"]) == "Dance"
    assert provider_activity_label("The Study", ["yoga-and-pilates"]) == "Yoga"
    # A non-activity provider yields no activity (stays "Other classes").
    assert provider_activity_label("For Dog's Sake! Training", ["training", "pets"]) is None


def test_class_title_keyword_wins_over_provider():
    # A Pilates class at a yoga studio is Pilates (title specificity beats provider).
    assert classify_class_subgroup("Reformer Pilates", "The Study Yoga", "Yoga") == "Pilates"


def test_class_inherits_provider_when_title_generic():
    # The real drains: generic titles inherit the studio's discipline.
    assert classify_class_subgroup("Inferno (4 PM)", "Amalaya Yoga", "Yoga") == "Yoga"
    assert classify_class_subgroup("Elementary B", "Ballet Havasu", "Dance") == "Dance"
    assert classify_class_subgroup("Boys Athletics (Older)", "Universal Sonics", "Gymnastics") == "Gymnastics"
    assert classify_class_subgroup("Morning Flow", "The Study", "Yoga") == "Yoga"


def test_genuinely_misc_stays_other():
    # Dog obedience has a non-activity provider → honest residue.
    assert classify_class_subgroup("Dog Obedience (8-wk course)", "For Dog's Sake", None) == FALLBACK_LABEL
    assert classify_class_subgroup("Arts & Crafts", "Senior Center", None) == FALLBACK_LABEL


def test_new_title_keywords():
    # Line Dancing (regex used to miss "dancing"); Fit & Flex; aquatic lessons.
    assert classify_class_subgroup("Line Dancing", "Iron Wolf Golf", None) == "Dance"
    assert classify_class_subgroup("Fit & Flex", "Aquatic Center", None) == "Strength & Cardio"
    assert classify_class_subgroup("Swim Lessons (Station-Based)", "Aquatic Center", None) == "Aquatic fitness"


# --------------------------------------------------------------------------- #
# 2B — event-vs-class routing (recurring social/music events leave Fitness)
# --------------------------------------------------------------------------- #


def test_recurring_social_events_leave_classes():
    assert _group_for(title="Open Mic Night", tags=None, featured=False, recurring=True) == "music"
    assert _group_for(title="Karaoke Night", tags=None, featured=False, recurring=True) == "music"
    assert _group_for(title="Live Music: Sacred Stone", tags=None, featured=False, recurring=True) == "music"
    assert _group_for(title="Bingo", tags=["events"], featured=False, recurring=True) == "events"
    assert _group_for(title="Trivia Night", tags=None, featured=False, recurring=True) == "events"


def test_comedy_with_incidental_class_keyword_routes_music():
    # "A First CLASS Night of Comedy" used to match the class keyword → Fitness.
    assert _group_for(
        title="Top Goons: A First Class Night of Comedy",
        tags=["events"], featured=False, recurring=False,
    ) == "music"


def test_genuine_classes_stay_in_classes():
    for title in ("Morning Flow", "Beginner Pilates", "Lap Swim", "Zumba", "Boys Athletics (Older)"):
        assert _group_for(title=title, tags=None, featured=False, recurring=True) == "classes", title


def test_dropin_and_civic_unaffected():
    assert _group_for(title="Pickleball Open Play", tags=None, featured=False, recurring=True) == "events"
    assert _group_for(title="City Council Meeting", tags=["civic"], featured=False, recurring=True) == "civic"


# --------------------------------------------------------------------------- #
# 2D — youth routing (provider-known youth classes reach Kids & Family)
# --------------------------------------------------------------------------- #


def test_youth_titles_route_to_family():
    assert is_family_event("Boys Athletics (Older)") is True
    assert is_family_event("Rec Gym (Mon 4 PM)") is True
    assert is_family_event("Kids Ballet") is True
    # Adult ballroom at the same kids-lessons provider must NOT be youth.
    assert is_family_event("Intro to Salsa") is False
    assert is_family_event("Intro to Ballroom") is False


def test_youth_subgroup_uses_provider_activity():
    # A generically-named youth gymnastics class types as Youth Gymnastics via the
    # provider activity (no "gymnastics" token in "Boys Athletics").
    assert _family_subgroup("Boys Athletics", "Gymnastics") == "Youth Gymnastics"
    assert _family_subgroup("Elementary B", "Dance") == "Youth Dance"
    # Title keyword still wins.
    assert _family_subgroup("Tiny Tumblers", None) == "Youth Gymnastics"


# --------------------------------------------------------------------------- #
# 2C — dedup: the pre-dawn AM/PM placeholder twin collapses
# --------------------------------------------------------------------------- #


def test_predawn_placeholder_is_tbd_for_dedup():
    from app.events.dedup import _start_is_tbd_for_dedup

    # 3 AM with no end = parse-error placeholder (the alligator-feed case).
    assert _start_is_tbd_for_dedup(time(3, 0), None) is True
    # 5 AM is a real early class (Lap Swim) — NOT a placeholder.
    assert _start_is_tbd_for_dedup(time(5, 0), None) is False
    # A genuine timed pre-dawn block (has an end time) is untouched.
    assert _start_is_tbd_for_dedup(time(4, 0), time(5, 0)) is False
    # Bare noon with no end is still suspect.
    assert _start_is_tbd_for_dedup(time(12, 0), None) is True


def test_predawn_twin_loses_to_daytime_sibling():
    from app.events.dedup import _group_survivor_positions

    class _Ev:
        def __init__(self, st, src, idx):
            self.start_time = st
            self.end_time = None
            self.location_name = "Lazy 5 Ranch"
            self.description = "x"
            self.source = src
            self.id = f"e{idx}"

    members = [(0, _Ev(time(3, 0), "river_scene_import", 0)),
               (1, _Ev(time(15, 0), "go_lake_havasu", 1))]
    survivors = _group_survivor_positions(members)
    # Only the 3 PM (position 1) survives; the 3 AM placeholder is dropped.
    assert survivors == {1}


# --------------------------------------------------------------------------- #
# Ingest parity: provider activity flows through the occurrence builder, so a
# future-scraped generically-named class classifies right with no extra step.
# --------------------------------------------------------------------------- #


def test_class_occurrence_carries_provider_activity():
    import uuid
    from datetime import UTC, datetime

    from app.db.database import SessionLocal
    from app.db.models import Provider, Schedule
    from app.events.class_occurrences import class_occurrences_in_window

    suf = uuid.uuid4().hex[:8]
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        prov = Provider(
            provider_name=f"Amalaya Yoga {suf}", category="fitness_sports",
            verified=True, draft=False, is_active=True, pending_review=False,
            source="test-calendar-classification",
        )
        db.add(prov)
        db.commit()
        eid, pid = prov.entity_id, prov.id
        sched = Schedule(
            entity_id=eid, schedule_type="recurring",
            days_of_week=["monday", "tuesday", "wednesday", "thursday",
                          "friday", "saturday", "sunday"],
            start_time=time(9, 0), end_time=time(10, 0),
            notes="Morning Flow",  # no activity keyword in the title
            created_at=now, updated_at=now,
        )
        db.add(sched)
        db.commit()
        sid = sched.id
        try:
            today = date.today()
            occs = class_occurrences_in_window(db, window_start=today, window_end=today)
            mine = [o for o in occs if o.title == "Morning Flow" and o.provider_slug == prov.slug]
            assert mine, "seeded class occurrence not found"
            assert mine[0].provider_activity == "Yoga"
            assert classify_class_subgroup(
                mine[0].title, mine[0].venue, mine[0].provider_activity
            ) == "Yoga"
        finally:
            db.query(Schedule).filter(Schedule.id == sid).delete()
            db.query(Provider).filter(Provider.id == pid).delete()
            from app.db.models import Entity

            db.query(Entity).filter(Entity.id == eid).delete()
            db.commit()

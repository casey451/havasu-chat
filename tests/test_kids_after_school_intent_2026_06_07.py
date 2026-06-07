"""Kids after-school browse must not classify as an entity-factual hours lookup.

After USE_INTENT_LAYER went live (2026-06-07), "what activities can my 8 year old
do after school hours" died in the gap template: the incidental "hours" token in
"after school hours" matched the HOURS_LOOKUP regex, and HOURS_LOOKUP is in the
intent layer's entity-factual deferral set, so the turn never reached
``kids_lessons``. See docs/cowork/HANDOFF_INTENT_FLAG.md ("Remaining caveat") and
docs/cowork/GAP_INVESTIGATION_2026-06-07.md (Bucket A3).

Fix lives in the classification path: a kids/age-band activity browse with no
resolved entity must not claim HOURS_LOOKUP. Real hours asks ("is mudshark open
on sundays") carry no kids/activity framing and keep routing factual -- the #203
entity-matcher guard is untouched.
"""

from __future__ import annotations

import uuid
from datetime import time as time_of_day

import pytest

from app.chat.intent_classifier import classify
from app.chat.intents.runtime import _ENTITY_FACTUAL_SUBINTENTS, try_intent_layer
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Program, Provider
from app.db.seed_helpers import derive_provider_slug

_LAT, _LNG = 34.4839, -114.3225

_GAP_QUERY = "what activities can my 8 year old do after school hours"


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _seed_provider(session, name, *, category, subcategory=None):
    prov = Provider(
        provider_name=name,
        category=category,
        subcategory=subcategory,
        slug=derive_provider_slug(session, name),
        source="test",
        lat=_LAT,
        lng=_LNG,
        draft=False,
        is_active=True,
    )
    session.add(prov)
    create_provider_and_entity(session, prov)
    session.commit()
    return prov


def _seed_kids_program(session, provider, *, title):
    prog = Program(
        title=title,
        description="After-school enrichment program for elementary kids.",
        activity_category="kids",
        age_min=5,
        age_max=13,
        schedule_days=["Monday", "Wednesday"],
        schedule_start_time=time_of_day(15, 30),
        schedule_end_time=time_of_day(17, 0),
        location_name="Lake Havasu City",
        provider_name=provider.provider_name,
        provider_id=provider.id,
        source="test",
        is_active=True,
    )
    session.add(prog)
    session.commit()
    return prog


def _cleanup(db, *provs):
    from sqlalchemy import delete

    from app.db.models import Entity, EntityCategory, Location

    for p in provs:
        eid = p.entity_id
        db.execute(delete(Program).where(Program.provider_id == p.id))
        db.execute(delete(Provider).where(Provider.id == p.id))
        if eid:
            db.execute(delete(Location).where(Location.entity_id == eid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
    db.commit()


def test_kids_after_school_browse_not_entity_factual():
    """The gap query must not land on an entity-factual sub_intent.

    HOURS_LOOKUP (matched on "after school hours") would defer the turn in the
    intent layer; the kids activity browse must classify to a non-factual,
    listing-shaped sub_intent instead.
    """
    result = classify(_GAP_QUERY)
    assert result.sub_intent not in _ENTITY_FACTUAL_SUBINTENTS, (
        f"{_GAP_QUERY!r} classified as {result.sub_intent!r}, which the intent "
        "layer defers as an entity-factual lookup"
    )


def test_real_hours_ask_still_routes_factual():
    """#203 regression guard: a genuine hours ask keeps HOURS_LOOKUP.

    None of these carry a kids/age-band activity-browse shape, so the fix must
    leave them routing factual (the intent layer keeps deferring to the
    entity-aware path).
    """
    assert classify("what are the hours for the library").sub_intent == "HOURS_LOOKUP"
    assert classify("is mudshark open on sundays").sub_intent == "HOURS_LOOKUP"
    assert classify("what are mudshark hours").sub_intent == "HOURS_LOOKUP"


def test_kids_after_school_gap_resolves_to_kids_lessons(db, monkeypatch):
    """End-to-end: the exact gap query resolves to kids_lessons with results.

    Mirrors prod: a weak entity match ("New Day School") plus the classifier's
    sub_intent are passed to the intent layer. Before the fix the HOURS_LOOKUP
    classification made the layer defer (return None); after the fix it claims
    the turn with a kids_lessons listing.
    """
    monkeypatch.setenv("USE_INTENT_LAYER", "1")
    suf = uuid.uuid4().hex[:8]
    host = _seed_provider(
        db, f"Havasu Kids Co {suf}", category="programs", subcategory="classes"
    )
    _seed_kids_program(db, host, title=f"After School Adventures {suf}")
    try:
        sub = classify(_GAP_QUERY).sub_intent
        ans = try_intent_layer(_GAP_QUERY, db, entity="New Day School", sub_intent=sub)
        assert ans is not None, "kids after-school browse still defers to the gap path"
        assert ans.intent_key == "kids_lessons"
        assert ans.result_count >= 1
    finally:
        _cleanup(db, host)

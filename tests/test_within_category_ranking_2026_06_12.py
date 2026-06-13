"""P1-1: within-category relevance ranking.

The Tier-2 listing path used to return the same per-category top-N for every
query in a bucket (ordered purely by rating), so "which launch ramp", "fish
from shore", and "sunset cruise" all got the same on-water list -- and the
storage/auto grab-bag, being highly rated, led it. P1-1 re-orders a bucket by
how many of the query's *distinctive* terms appear in each row's searchable
text, breaking ties with the existing rating sort.

Two halves:

* Pure unit tests for ``_derive_rank_terms`` (tokenize + drop stop/locality/
  bucket/number/short tokens) and ``relevance`` (substring term count).
* A seeded-DB test that exercises the part needing live-DB verification: the
  ``EntityCategory -> Category`` leaf-slug join on the hot path. The
  "launch"/"ramp" signal lives ONLY in the curated leaf slug
  ``marinas-and-launch-ramps`` -- nowhere on the Provider row -- so a marina
  with that leaf must outrank a higher-rated on-water row that lacks it for a
  "launch ramp" query, while a generic (all-stopword) query preserves the
  legacy rating-only order.
"""

from __future__ import annotations

import uuid

import pytest

from app.chat.intents.queries import _derive_rank_terms, relevance, run_query
from app.chat.intents.resolver import ResolvedIntent
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, EntityCategory, Provider
from app.db.seed_helpers import derive_provider_slug

_LAT, _LNG = 34.4839, -114.3225


# ---------------------------------------------------------------------------
# Pure unit tests (no DB)
# ---------------------------------------------------------------------------


def test_derive_rank_terms_keeps_only_distinctive_words():
    terms = _derive_rank_terms(
        "Which launch ramp is best for a 28-foot boat near the Channel?"
    )
    assert terms == frozenset({"launch", "ramp", "foot", "channel"})


def test_derive_rank_terms_drops_stop_locality_bucket_and_numbers():
    terms = _derive_rank_terms(
        "Which launch ramp is best for a 28-foot boat near the Channel?"
    )
    for banned in ("which", "best", "boat", "the", "near", "lake", "havasu", "28", "is"):
        assert banned not in terms


def test_derive_rank_terms_empty_for_blank_or_all_generic():
    assert _derive_rank_terms("") == frozenset()
    assert _derive_rank_terms(None) == frozenset()
    # Every token is stop/locality/bucket -> no distinctive terms -> no-op.
    assert _derive_rank_terms("where can i find a good boat in lake havasu") == frozenset()


def test_relevance_counts_substring_term_hits():
    # 'ramp' matches the 'ramps' in the leaf slug (substring).
    assert relevance("marinas-and-launch-ramps", frozenset({"ramp"})) == 1
    assert relevance("marinas-and-launch-ramps", frozenset({"launch", "ramp"})) == 2
    assert relevance("sunset cruise tours", frozenset({"sunset", "cruise", "fishing"})) == 2
    # Non-matching row scores zero; empty rank_terms is always zero (no-op).
    assert relevance("928 desert detailing auto-marine-detailing", frozenset({"launch", "ramp"})) == 0
    assert relevance("anything at all", frozenset()) == 0


# ---------------------------------------------------------------------------
# Seeded-DB test: the leaf-slug join on the hot path
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _seed_provider(session, name, *, subcategory, google_rating):
    prov = Provider(
        provider_name=name,
        category="lake_recreation",
        subcategory=subcategory,
        google_rating=google_rating,
        google_review_count=10,
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


def _attach_leaf(session, prov, slug):
    """Link the provider's entity to a leaf Category by slug; create the leaf if
    the test DB doesn't already seed it. Returns the category id and whether this
    call created it (so the test only cleans up what it made)."""
    cat = session.query(Category).filter(Category.slug == slug).first()
    created = cat is None
    if cat is None:
        cat = Category(slug=slug, name="Marinas & Launch Ramps", level=1)
        session.add(cat)
        session.flush()
    session.add(
        EntityCategory(entity_id=prov.entity_id, category_id=cat.id, is_primary=False)
    )
    session.commit()
    return cat.id, created


def _cleanup(db, provs, leaf_cat_id=None):
    from sqlalchemy import delete

    from app.db.models import Entity, Location

    for p in provs:
        eid = p.entity_id
        db.execute(delete(Provider).where(Provider.id == p.id))
        if eid:
            db.execute(delete(Location).where(Location.entity_id == eid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
    if leaf_cat_id is not None:
        db.execute(delete(Category).where(Category.id == leaf_cat_id))
    db.commit()


def test_leaf_match_outranks_higher_rated_nonmatch(db):
    """A marina (lower rating, leaf carries the 'launch'/'ramp' signal) must
    outrank a higher-rated on-water row that lacks the leaf -- and only because
    ``_query_providers`` loads the leaf slug into the searchable string."""
    suf = uuid.uuid4().hex[:8]
    marina_name = f"Stonebridge Pier {suf}"  # no 'launch'/'ramp' in the NAME
    other_name = f"Havasu Watersports Rentals {suf}"

    marina = _seed_provider(db, marina_name, subcategory="on-the-water", google_rating=4.0)
    other = _seed_provider(db, other_name, subcategory="on-the-water", google_rating=4.9)
    leaf_id, created = _attach_leaf(db, marina, "marinas-and-launch-ramps")

    try:
        resolved = ResolvedIntent("on_the_water", {}, "L1")

        # Relevant query: the leaf signal makes the lower-rated marina win.
        ranked = run_query(resolved, db, raw_query="which launch ramp can i use for my boat")
        names = [r["name"] for r in ranked.rows]
        assert marina_name in names and other_name in names
        assert names.index(marina_name) < names.index(other_name), names

        # Backward-compatible: an all-generic query derives no rank terms, so the
        # legacy rating-only sort stands and the 4.9 row leads the 4.0 one.
        legacy = run_query(resolved, db, raw_query="show me places on the water")
        lnames = [r["name"] for r in legacy.rows]
        assert lnames.index(other_name) < lnames.index(marina_name), lnames
    finally:
        _cleanup(db, [marina, other], leaf_cat_id=leaf_id if created else None)

"""Tests for the provider merge primitive (Item C).

Run from the owner's terminal: python -m pytest tests/test_provider_merge.py -q
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest
from sqlalchemy import select

from app.contrib.provider_merge import merge_providers
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import (
    Claim,
    Entity,
    Event,
    Provider,
    User,
    UserFavorite,
)
from app.db.seed_helpers import derive_provider_slug

_LAT = 34.4839
_LNG = -114.3225


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session
        session.rollback()


def _provider(session, name, *, source="go_lake_havasu", **kw) -> Provider:
    prov = Provider(
        provider_name=name,
        category=kw.pop("category", "eat-drink"),
        slug=derive_provider_slug(session, name),
        source=source,
        lat=kw.pop("lat", _LAT),
        lng=kw.pop("lng", _LNG),
        draft=kw.pop("draft", False),
        is_active=kw.pop("is_active", True),
        **kw,
    )
    session.add(prov)
    create_provider_and_entity(session, prov)
    session.flush()
    return prov


def _user(session) -> User:
    u = User(email=f"{uuid.uuid4().hex}@example.test")
    session.add(u)
    session.flush()
    return u


def test_gap_fill_and_soft_retire(db_session):
    keep = _provider(db_session, "Joes Bar", website=None, phone=None)
    dup = _provider(db_session, "Joes Bar", website="http://joes.com", phone="928-555-0101")
    res = merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)
    db_session.flush()

    assert keep.website == "http://joes.com"
    assert keep.phone == "928-555-0101"
    assert "website" in res.gap_filled and "phone" in res.gap_filled
    # loser retired and hidden from consumption (draft + inactive)
    assert dup.is_active is False
    assert dup.draft is True
    assert dup.pending_review is False
    dup_ent = db_session.get(Entity, dup.entity_id)
    assert dup_ent.is_active is False
    # provenance combined on keeper
    assert "go_lake_havasu" in (keep.source or "")


def test_does_not_clobber_existing_keeper_fields(db_session):
    keep = _provider(db_session, "Joes Bar", website="http://keep.com")
    dup = _provider(db_session, "Joes Bar", website="http://dup.com")
    res = merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)
    assert keep.website == "http://keep.com"
    assert "website" not in res.gap_filled


def test_gap_fills_curated_attributes_when_keeper_empty(db_session):
    # The Hangar 24 case (WS4 2026-07-08): the retired twin carried a client-assigned
    # cuisine; the surviving keeper (no cuisine of its own) must INHERIT it so curated
    # data survives the merge instead of dying with the twin.
    keep = _provider(db_session, "Hangar 24 Lake Havasu", attributes=None)
    dup = _provider(db_session, "Hangar 24 Taproom", attributes={"cuisine": "american"})
    res = merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)
    db_session.flush()
    assert (keep.attributes or {}).get("cuisine") == "american"
    assert "attributes" in res.gap_filled


def test_does_not_overwrite_existing_keeper_attribute(db_session):
    # Filiberto's shape: keeper already has a curated cuisine -> never clobbered.
    keep = _provider(db_session, "Filibertos", attributes={"cuisine": "mexican"})
    dup = _provider(db_session, "Filibertos Mexican Food", attributes={"cuisine": "american"})
    res = merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)
    assert (keep.attributes or {}).get("cuisine") == "mexican"
    assert "attributes" not in res.gap_filled


def test_operational_attributes_do_not_transfer(db_session):
    # Curated keys transfer; merge-internal/operational keys never do.
    keep = _provider(db_session, "Keeper Cafe", attributes=None)
    dup = _provider(
        db_session,
        "Keeper Cafe Twin",
        attributes={"merged_into_slug": "somewhere-else", "cuisine": "mexican"},
    )
    merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)
    db_session.flush()
    attrs = keep.attributes or {}
    assert attrs.get("cuisine") == "mexican"
    assert "merged_into_slug" not in attrs


def test_repoints_event_provider_and_entity(db_session):
    keep = _provider(db_session, "Marina")
    dup = _provider(db_session, "Marina")
    ev = Event(
        title="Boat Show",
        normalized_title="boat show",
        date=date(2026, 7, 1),
        start_time=time(10, 0),
        location_name="Marina",
        location_normalized="marina",
        description="d",
        provider_id=dup.id,
        entity_id=dup.entity_id,
        status="live",
    )
    db_session.add(ev)
    db_session.flush()

    merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)
    db_session.flush()
    db_session.refresh(ev)
    assert ev.provider_id == keep.id
    assert ev.entity_id == keep.entity_id


def test_userfavorite_moved_and_deduped(db_session):
    keep = _provider(db_session, "Cafe")
    dup = _provider(db_session, "Cafe")
    u_move = _user(db_session)
    u_collide = _user(db_session)

    # u_move only favorited the dup -> should be repointed to keep.
    db_session.add(UserFavorite(user_id=u_move.id, entity_id=dup.entity_id))
    # u_collide favorited BOTH -> the dup row must be deleted, not repointed
    # (would violate UNIQUE(user_id, entity_id)).
    db_session.add(UserFavorite(user_id=u_collide.id, entity_id=keep.entity_id))
    db_session.add(UserFavorite(user_id=u_collide.id, entity_id=dup.entity_id))
    db_session.flush()

    merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)
    db_session.flush()

    favs = db_session.scalars(
        select(UserFavorite).where(UserFavorite.entity_id == keep.entity_id)
    ).all()
    assert {f.user_id for f in favs} == {u_move.id, u_collide.id}
    # nothing left pointing at the loser entity
    assert (
        db_session.scalars(
            select(UserFavorite).where(UserFavorite.entity_id == dup.entity_id)
        ).all()
        == []
    )


def test_claim_dedupe(db_session):
    keep = _provider(db_session, "Shop")
    dup = _provider(db_session, "Shop")
    u = _user(db_session)
    db_session.add(Claim(user_id=u.id, entity_id=keep.entity_id, status="verified"))
    db_session.add(Claim(user_id=u.id, entity_id=dup.entity_id, status="pending"))
    db_session.flush()

    merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)
    db_session.flush()
    claims = db_session.scalars(select(Claim).where(Claim.entity_id == keep.entity_id)).all()
    assert len(claims) == 1  # collision deleted, original kept


def test_refuses_operator_dup(db_session):
    keep = _provider(db_session, "X", source="go_lake_havasu")
    dup = _provider(db_session, "X", source="operator")
    with pytest.raises(ValueError, match="operator"):
        merge_providers(db_session, keep_id=keep.id, dup_id=dup.id)


def test_refuses_same_id(db_session):
    keep = _provider(db_session, "Y")
    with pytest.raises(ValueError, match="same provider"):
        merge_providers(db_session, keep_id=keep.id, dup_id=keep.id)


def test_refuses_missing(db_session):
    keep = _provider(db_session, "Z")
    with pytest.raises(ValueError, match="dup provider not found"):
        merge_providers(db_session, keep_id=keep.id, dup_id="no-such-id")


def test_dry_run_makes_no_changes(db_session):
    keep = _provider(db_session, "Diner", website=None)
    dup = _provider(db_session, "Diner", website="http://dup.com")
    res = merge_providers(db_session, keep_id=keep.id, dup_id=dup.id, dry_run=True)
    db_session.flush()
    # plan reported, but nothing mutated
    assert "website" in res.gap_filled
    assert keep.website is None
    assert dup.is_active is True
    assert dup.draft is False

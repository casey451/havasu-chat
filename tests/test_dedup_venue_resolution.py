"""Characterization tests for venue->entity resolution and the reconciler's
contact-identity tier, written to pin behavior ahead of the O(N)-scan
optimization (docs/CLEANUP_AUDIT.md §4.1). Semantics under test:

- ``resolve_venue_entity_id``: exact/fuzzy (>=90 token_sort_ratio) name match
  against active entities; address fallback (>=85 partial_ratio) against
  active providers; inactive entities never match.
- ``_contact_match_entity_id``: returns an entity_id only when EXACTLY ONE
  distinct active entity shares the payload's website domain or phone.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.contrib.ingest_base import EntityPayload
from app.contrib.ingest_reconciler import _contact_match_entity_id
from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.events.dedup import resolve_venue_entity_id


def _mk_entity(db, name: str, *, active: bool = True) -> Entity:
    ent = Entity(
        entity_type="commercial",
        slug=f"dedup-test-{uuid.uuid4().hex[:10]}",
        name=name,
        source="test-dedup-venue",
    )
    if not active:
        ent.is_active = False
    db.add(ent)
    db.flush()
    return ent


def _mk_provider(db, name: str, **kw) -> Provider:
    p = Provider(
        provider_name=name,
        category="x",
        verified=True,
        draft=False,
        is_active=True,
        pending_review=False,
        source="test-dedup-venue",
        **kw,
    )
    db.add(p)
    db.flush()
    return p


def _cleanup(db, entity_ids: list[str], provider_ids: list[int]) -> None:
    if provider_ids:
        db.execute(delete(Provider).where(Provider.id.in_(provider_ids)))
    if entity_ids:
        db.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
    db.commit()


def test_exact_name_match_resolves() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        ent = _mk_entity(db, f"Zqalpha Venue Hall {suf}")
        db.commit()
        try:
            assert resolve_venue_entity_id(db, f"Zqalpha Venue Hall {suf}") == ent.id
            # Punctuation/case differences normalize away -> still exact.
            assert resolve_venue_entity_id(db, f"zqalpha VENUE hall, {suf}!") == ent.id
        finally:
            _cleanup(db, [ent.id], [])


def test_fuzzy_name_match_above_threshold_resolves() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        ent = _mk_entity(db, f"Zqalpha Community Venue Hall {suf}")
        db.commit()
        try:
            # One dropped word -> token_sort_ratio in the 90s, below 100.
            got = resolve_venue_entity_id(db, f"Zqalpha Community Venue {suf}")
            assert got == ent.id
        finally:
            _cleanup(db, [ent.id], [])


def test_unrelated_name_returns_none() -> None:
    with SessionLocal() as db:
        assert resolve_venue_entity_id(db, "Xv Qwerty Nonexistent Zzz Venue 77q") is None


def test_blank_name_returns_none() -> None:
    with SessionLocal() as db:
        assert resolve_venue_entity_id(db, None) is None
        assert resolve_venue_entity_id(db, "   ") is None


def test_inactive_entity_never_matches() -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        ent = _mk_entity(db, f"Zqalpha Shuttered Hall {suf}", active=False)
        db.commit()
        try:
            assert resolve_venue_entity_id(db, f"Zqalpha Shuttered Hall {suf}") is None
        finally:
            _cleanup(db, [ent.id], [])


def test_address_fallback_resolves_via_provider() -> None:
    suf = uuid.uuid4().hex[:8]
    addr = f"4242 Zqwhatever Blvd N Suite {suf} Lake Havasu City"
    with SessionLocal() as db:
        p = _mk_provider(db, f"Zqalpha Addressed Biz {suf}", address=addr)
        db.commit()
        eid = p.entity_id
        assert eid
        try:
            got = resolve_venue_entity_id(
                db, "Xv Qwerty Nonexistent Zzz Venue 77q", venue_address=addr
            )
            assert got == eid
        finally:
            _cleanup(db, [eid], [p.id])


def test_contact_match_unique_website_domain() -> None:
    suf = uuid.uuid4().hex[:8]
    domain = f"zq-{suf}-plumbing.com"
    with SessionLocal() as db:
        p = _mk_provider(db, f"Zq Contact Biz {suf}", website=f"https://www.{domain}/about")
        db.commit()
        eid = p.entity_id
        try:
            payload = EntityPayload(
                name="anything", entity_type="commercial", website=f"http://{domain}"
            )
            assert _contact_match_entity_id(db, payload) == eid
        finally:
            _cleanup(db, [eid], [p.id])


def test_contact_match_ambiguous_domain_returns_none() -> None:
    suf = uuid.uuid4().hex[:8]
    domain = f"zq-{suf}-franchise.com"
    with SessionLocal() as db:
        p1 = _mk_provider(db, f"Zq Franchise North {suf}", website=f"https://{domain}/n")
        p2 = _mk_provider(db, f"Zq Franchise South {suf}", website=f"https://{domain}/s")
        db.commit()
        try:
            payload = EntityPayload(
                name="anything", entity_type="commercial", website=f"https://{domain}"
            )
            assert _contact_match_entity_id(db, payload) is None
        finally:
            _cleanup(db, [p1.entity_id, p2.entity_id], [p1.id, p2.id])


def test_contact_match_phone_and_empty_payload() -> None:
    suf = uuid.uuid4().hex[:8]
    digits = str(int(uuid.uuid4().int % 10_000_000)).zfill(7)
    phone = f"928{digits}"
    with SessionLocal() as db:
        p = _mk_provider(db, f"Zq Phone Biz {suf}", phone=phone)
        db.commit()
        eid = p.entity_id
        try:
            hit = EntityPayload(name="x", entity_type="commercial", phone=phone)
            miss = EntityPayload(name="x", entity_type="commercial")
            assert _contact_match_entity_id(db, hit) == eid
            assert _contact_match_entity_id(db, miss) is None
        finally:
            _cleanup(db, [eid], [p.id])

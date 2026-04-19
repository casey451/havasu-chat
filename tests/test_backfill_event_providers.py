"""Phase 1.6 — backfill event.provider_id from providers."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, time
from uuid import uuid4

from app.db.backfill_event_providers import (
    SOURCE_ALLOWLIST,
    _pick_provider,
    backfill_event_providers,
)
from app.db.database import SessionLocal, init_db
from app.db.models import Event, Provider
from app.db.seed_providers import _norm_provider_name

_PREFIX = "TEST_BFE_"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _provider(**kwargs: object) -> Provider:
    now = _now()
    defaults: dict = {
        "id": str(uuid4()),
        "category": "sports",
        "tier": "free",
        "sponsored_until": None,
        "featured_description": None,
        "draft": False,
        "verified": False,
        "is_active": True,
        "pending_review": False,
        "admin_review_by": None,
        "source": "seed",
        "created_at": now,
        "updated_at": now,
        "address": None,
        "phone": None,
        "email": None,
        "website": None,
        "facebook": None,
        "hours": None,
        "description": None,
    }
    defaults.update(kwargs)
    return Provider(**defaults)


def _event(
    *,
    title: str,
    description: str = "D" * 25,
    location_name: str = "Lake Havasu City, AZ",
    contact_name: str | None = None,
    source: str = "admin",
    provider_id: str | None = None,
    event_url: str = "https://example.com/event",
    contact_phone: str | None = "9285550100",
) -> Event:
    now = _now()
    t = title.strip()
    loc = location_name.strip()
    return Event(
        id=str(uuid4()),
        title=t,
        normalized_title=t.lower(),
        date=date(2026, 6, 15),
        start_time=time(10, 0),
        end_time=time(11, 0),
        location_name=loc,
        location_normalized=loc.lower(),
        description=description,
        event_url=event_url,
        contact_name=contact_name,
        contact_phone=contact_phone,
        tags=[],
        embedding=None,
        status="live",
        source=source,
        verified=False,
        created_at=now,
        created_by="test",
        admin_review_by=None,
        provider_id=provider_id,
    )


def _clear_fixtures() -> None:
    with SessionLocal() as db:
        db.query(Event).filter(Event.title.startswith(_PREFIX)).delete(synchronize_session=False)
        db.query(Provider).filter(Provider.provider_name.startswith(_PREFIX)).delete(
            synchronize_session=False
        )
        db.commit()


class PickProviderMarginTests(unittest.TestCase):
    """Clarification C — margin of 5 vs threshold."""

    def test_accept_when_second_below_threshold(self) -> None:
        a = _provider(provider_name=f"{_PREFIX}A")
        b = _provider(provider_name=f"{_PREFIX}B")
        chosen, amb, _ = _pick_provider([(a, 96.0), (b, 88.0)], 90.0)
        self.assertFalse(amb)
        self.assertIs(chosen, a)

    def test_ambiguous_when_top_two_both_ge_threshold_within_five_points(self) -> None:
        a = _provider(provider_name=f"{_PREFIX}A")
        b = _provider(provider_name=f"{_PREFIX}B")
        chosen, amb, details = _pick_provider([(a, 93.0), (b, 90.0)], 90.0)
        self.assertTrue(amb)
        self.assertIsNone(chosen)
        self.assertGreaterEqual(len(details), 2)

    def test_accept_clear_gap_five_or_more(self) -> None:
        a = _provider(provider_name=f"{_PREFIX}A")
        b = _provider(provider_name=f"{_PREFIX}B")
        chosen, amb, _ = _pick_provider([(a, 96.0), (b, 91.0)], 90.0)
        self.assertFalse(amb)
        self.assertIs(chosen, a)

    def test_ambiguous_when_gap_strictly_less_than_five(self) -> None:
        a = _provider(provider_name=f"{_PREFIX}A")
        b = _provider(provider_name=f"{_PREFIX}B")
        chosen, amb, _ = _pick_provider([(a, 96.0), (b, 92.0)], 90.0)
        self.assertTrue(amb)
        self.assertIsNone(chosen)


class BackfillEventProvidersTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db()
        _clear_fixtures()

    def tearDown(self) -> None:
        _clear_fixtures()

    def test_contact_name_exact_match_links(self) -> None:
        name = f"{_PREFIX}Exact Event Org"
        prov = _provider(provider_name=name)
        ev = _event(title=f"{_PREFIX}race", contact_name=name)
        with SessionLocal() as db:
            db.add_all([prov, ev])
            db.commit()
            r = backfill_event_providers(db)
            self.assertEqual(r.linked_contact_exact, 1)
            self.assertEqual(r.events_updated, 1)
            db.refresh(ev)
            self.assertEqual(ev.provider_id, prov.id)

    def test_contact_name_shorter_form_matches_canonical_via_norm(self) -> None:
        """Instructions-style short contact vs master canonical (— Sonics) via _norm_provider_name tail fold."""
        canonical = "Universal Gymnastics and All Star Cheer — Sonics"
        prov = _provider(provider_name=canonical)
        ev = _event(
            title=f"{_PREFIX}cheer tryouts",
            contact_name="Universal Gymnastics and All Star Cheer",
            description="Team placement night for competitive cheer.",
        )
        with SessionLocal() as db:
            db.add_all([prov, ev])
            db.commit()
            r = backfill_event_providers(db)
            self.assertEqual(r.linked_contact_exact, 1)
            self.assertEqual(r.linked_contact_fuzzy, 0)
            self.assertEqual(r.events_updated, 1)
            db.refresh(ev)
            self.assertEqual(ev.provider_id, prov.id)

    def test_contact_name_fuzzy_when_norm_differs(self) -> None:
        """True fuzzy path: contact is a shorter phrase; norm keys differ; token_set_ratio links."""
        prov = _provider(provider_name=f"{_PREFIX}Metro Aquatic Programs Department")
        ev = _event(
            title=f"{_PREFIX}swim night",
            contact_name=f"{_PREFIX}Metro Aquatic Programs",
            description="Evening lap swim and family splash night.",
        )
        self.assertNotEqual(
            _norm_provider_name(prov.provider_name),
            _norm_provider_name(ev.contact_name or ""),
        )
        with SessionLocal() as db:
            db.add_all([prov, ev])
            db.commit()
            r = backfill_event_providers(db)
            self.assertEqual(r.linked_contact_fuzzy, 1)
            self.assertEqual(r.linked_contact_exact, 0)
            self.assertEqual(r.events_updated, 1)
            self.assertEqual(len(r.contact_fuzzy_details), 1)
            self.assertGreaterEqual(r.contact_fuzzy_details[0].score, 90.0)
            db.refresh(ev)
            self.assertEqual(ev.provider_id, prov.id)

    def test_blob_title_description_links_when_no_contact(self) -> None:
        pname = f"{_PREFIX}Blob Match Gymnasium Inc"
        prov = _provider(provider_name=pname)
        ev = _event(
            title=f"{_PREFIX}open house",
            contact_name=None,
            description=(
                f"Annual open house hosted by {pname} for parents and athletes. "
                "Free tours and registration information at the front desk."
            ),
            location_name="100 Main St, Lake Havasu City, AZ",
        )
        with SessionLocal() as db:
            db.add_all([prov, ev])
            db.commit()
            r = backfill_event_providers(db)
            self.assertEqual(r.linked_blob, 1)
            self.assertEqual(r.events_updated, 1)
            self.assertGreaterEqual(r.blob_details[0].score, 95.0)
            db.refresh(ev)
            self.assertEqual(ev.provider_id, prov.id)

    def test_no_signal_stays_null(self) -> None:
        prov = _provider(provider_name=f"{_PREFIX}Unrelated Org")
        ev = _event(
            title=f"{_PREFIX}generic fair",
            contact_name=None,
            description="Community fair with food trucks and local vendors. Family friendly evening.",
        )
        with SessionLocal() as db:
            db.add_all([prov, ev])
            db.commit()
            r = backfill_event_providers(db)
            self.assertEqual(r.events_updated, 0)
            db.refresh(ev)
            self.assertIsNone(ev.provider_id)

    def test_already_linked_skipped(self) -> None:
        p1 = _provider(provider_name=f"{_PREFIX}P1")
        p2 = _provider(provider_name=f"{_PREFIX}P2")
        ev = _event(title=f"{_PREFIX}linked", contact_name=p2.provider_name, provider_id=p1.id)
        with SessionLocal() as db:
            db.add_all([p1, p2, ev])
            db.commit()
            r = backfill_event_providers(db)
            self.assertEqual(r.skipped_already_linked, 1)
            self.assertEqual(r.events_updated, 0)
            db.refresh(ev)
            self.assertEqual(ev.provider_id, p1.id)

    def test_ambiguous_two_strong_fuzzy_contact(self) -> None:
        """Two distinct providers whose names both fuzzy-high against the same contact string."""
        a = _provider(provider_name=f"{_PREFIX}Northside Swim Academy LLC")
        b = _provider(provider_name=f"{_PREFIX}Northside Swim Club LLC")
        ev = _event(
            title=f"{_PREFIX}swim meet",
            contact_name=f"{_PREFIX}Northside Swim",
            description="Regional swim meet hosted by local clubs.",
        )
        with SessionLocal() as db:
            db.add_all([a, b, ev])
            db.commit()
            r = backfill_event_providers(db)
            self.assertEqual(r.events_updated, 0)
            self.assertGreaterEqual(len(r.ambiguous), 1)
            db.refresh(ev)
            self.assertIsNone(ev.provider_id)

    def test_non_allowlist_source_matches(self) -> None:
        pname = f"{_PREFIX}Source Match Org"
        prov = _provider(provider_name=pname)
        ev = _event(
            title=f"{_PREFIX}src event",
            contact_name=None,
            source=pname,
            description="Event with organizer stored only in source field for this test.",
        )
        self.assertNotIn(pname.lower(), SOURCE_ALLOWLIST)
        with SessionLocal() as db:
            db.add_all([prov, ev])
            db.commit()
            r = backfill_event_providers(db)
            self.assertEqual(r.linked_source_exact, 1)
            self.assertEqual(r.events_updated, 1)
            db.refresh(ev)
            self.assertEqual(ev.provider_id, prov.id)

    def test_idempotency_second_run_zero_updates(self) -> None:
        name = f"{_PREFIX}Idem Org"
        prov = _provider(provider_name=name)
        ev = _event(title=f"{_PREFIX}idem", contact_name=name)
        with SessionLocal() as db:
            db.add_all([prov, ev])
            db.commit()
            r1 = backfill_event_providers(db)
            self.assertEqual(r1.events_updated, 1)
            r2 = backfill_event_providers(db)
            self.assertEqual(r2.events_updated, 0)
            self.assertEqual(r2.skipped_already_linked, 1)


class BackfillEventProvidersExactNormTests(unittest.TestCase):
    """Exact path uses same normalization as provider seed."""

    def test_exact_uses_norm_provider_name(self) -> None:
        raw = f"{_PREFIX}Norm Co"
        prov = _provider(provider_name=raw)
        # different unicode spaces / dash still same norm bucket
        contact_variant = raw.replace(" ", "\u00a0") if " " in raw else raw + " "
        ev = _event(title=f"{_PREFIX}n1", contact_name=contact_variant.strip() + " ")
        with SessionLocal() as db:
            db.add_all([prov, ev])
            db.commit()
            self.assertEqual(
                _norm_provider_name(prov.provider_name),
                _norm_provider_name(ev.contact_name or ""),
            )
            r = backfill_event_providers(db)
            self.assertEqual(r.linked_contact_exact, 1)


if __name__ == "__main__":
    unittest.main()

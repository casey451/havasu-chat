"""Tests for the entity-matcher catalog cache (5-min TTL + batched refresh)."""

from __future__ import annotations

import unittest
from unittest import mock

from sqlalchemy.orm import Session

from app.chat import entity_matcher
from app.chat.entity_matcher import (
    _catalog_is_fresh,
    _category_blob_for_canonical,
    _EntityRow,
    ensure_entity_matcher,
    refresh_entity_matcher,
    reset_entity_matcher,
)
from app.db.database import SessionLocal
from app.db.models import Program, Provider
from app.schemas.program import ProgramCreate


def _insert_program(db: Session, provider_name: str, category: str = "sports") -> str:
    """Mirror ``tests/test_entity_matcher.py::_insert_program`` for a single program."""
    payload = ProgramCreate(
        title="Test activity for entity matcher caching",
        description="Twenty chars minimum here.",
        activity_category=category,
        schedule_start_time="09:00",
        schedule_end_time="10:00",
        location_name="Lake Havasu City",
        provider_name=provider_name,
        tags=["entity_matcher_cache_test"],
    )
    p = Program(
        title=payload.title,
        description=payload.description,
        activity_category=payload.activity_category,
        age_min=payload.age_min,
        age_max=payload.age_max,
        schedule_days=list(payload.schedule_days),
        schedule_start_time=payload.schedule_start_time,
        schedule_end_time=payload.schedule_end_time,
        location_name=payload.location_name,
        location_address=payload.location_address,
        cost=payload.cost,
        provider_name=payload.provider_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        contact_url=payload.contact_url,
        source=payload.source,
        is_active=payload.is_active,
        tags=list(payload.tags),
        embedding=payload.embedding,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


def _insert_provider(
    db: Session, name: str, category: str, google_cat: str | None = None
) -> str:
    row = Provider(
        provider_name=name,
        category=category,
        google_primary_category=google_cat,
        is_active=True,
        draft=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return str(row.id)


class EntityMatcherCachingTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_entity_matcher()
        self.db: Session = SessionLocal()

    def tearDown(self) -> None:
        try:
            self.db.rollback()
        finally:
            self.db.close()
        reset_entity_matcher()

    def test_ensure_entity_matcher_loads_on_cold_cache(self) -> None:
        """Cold cache -> ensure() triggers a real load and _rows is populated."""
        reset_entity_matcher()
        self.assertIsNone(entity_matcher._rows)
        ensure_entity_matcher(self.db)
        self.assertIsNotNone(entity_matcher._rows)
        self.assertIsNotNone(entity_matcher._rows_loaded_at)

    def test_ensure_entity_matcher_skips_rebuild_when_fresh(self) -> None:
        """Repeated ensure() calls within the TTL window must hit the cache."""
        ensure_entity_matcher(self.db)  # initial load
        with mock.patch.object(
            entity_matcher, "refresh_entity_matcher"
        ) as refresh_spy:
            for _ in range(5):
                ensure_entity_matcher(self.db)
            self.assertEqual(refresh_spy.call_count, 0)

    def test_ensure_entity_matcher_rebuilds_after_ttl_expiry(self) -> None:
        """A monkeypatched clock past _CATALOG_TTL_SECONDS triggers exactly one rebuild."""
        ensure_entity_matcher(self.db)
        loaded_at = entity_matcher._rows_loaded_at
        self.assertIsNotNone(loaded_at)
        future = loaded_at + entity_matcher._CATALOG_TTL_SECONDS + 1.0
        with mock.patch.object(entity_matcher.time, "monotonic", return_value=future):
            self.assertFalse(_catalog_is_fresh())
            with mock.patch.object(
                entity_matcher,
                "refresh_entity_matcher",
                wraps=entity_matcher.refresh_entity_matcher,
            ) as refresh_spy:
                ensure_entity_matcher(self.db)
                self.assertEqual(refresh_spy.call_count, 1)

    def test_reset_entity_matcher_clears_loaded_at(self) -> None:
        """reset() must clear both _rows and _rows_loaded_at so the next ensure() reloads."""
        ensure_entity_matcher(self.db)
        self.assertTrue(_catalog_is_fresh())
        reset_entity_matcher()
        self.assertIsNone(entity_matcher._rows)
        self.assertIsNone(entity_matcher._rows_loaded_at)
        self.assertFalse(_catalog_is_fresh())

    def test_force_flag_rebuilds_even_when_fresh(self) -> None:
        """force=True must always call refresh_entity_matcher, TTL be damned."""
        ensure_entity_matcher(self.db)
        self.assertTrue(_catalog_is_fresh())
        with mock.patch.object(
            entity_matcher,
            "refresh_entity_matcher",
            wraps=entity_matcher.refresh_entity_matcher,
        ) as refresh_spy:
            ensure_entity_matcher(self.db, force=True)
            self.assertEqual(refresh_spy.call_count, 1)

    def test_batched_category_blob_matches_per_row_version(self) -> None:
        """The batched blob loader must produce blobs equivalent to the per-row builder.

        Seeds three providers + a program apiece, runs the new batched refresh,
        and asserts every resulting ``_EntityRow.category_blob`` token set matches
        the legacy per-canonical builder. We compare token sets (not strings)
        because batched aggregation may interleave Provider rows vs Program
        rows from different canonicals; the per-canonical scoring path
        (:func:`_trade_cluster_tags`) only cares about token presence.
        """
        reset_entity_matcher()
        seeds = [
            (
                "Cache Test Plumbing Co",
                "plumbing",
                "Plumber",
                "home_services",
            ),
            (
                "Cache Test BMX Track",
                "sports",
                "BMX Track",
                "bmx",
            ),
            (
                "Cache Test Gymnastics Center",
                "gymnastics",
                "Gymnastics Center",
                "gymnastics_cheer",
            ),
        ]
        for name, prov_cat, google_cat, act_cat in seeds:
            _insert_provider(self.db, name, prov_cat, google_cat)
            _insert_program(self.db, name, act_cat)

        refresh_entity_matcher(self.db)
        rows_by_name: dict[str, _EntityRow] = {
            r.canonical: r for r in (entity_matcher._rows or [])
        }
        for name, _, _, _ in seeds:
            self.assertIn(name, rows_by_name, f"missing canonical {name!r}")
            batched_blob = rows_by_name[name].category_blob
            per_row_blob = _category_blob_for_canonical(self.db, name)
            self.assertEqual(
                set(batched_blob.split()),
                set(per_row_blob.split()),
                f"blob token set mismatch for {name!r}: "
                f"batched={batched_blob!r} per_row={per_row_blob!r}",
            )


if __name__ == "__main__":
    unittest.main()

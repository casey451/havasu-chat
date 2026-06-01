from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy.orm import Session

from app.chat.entity_matcher import (
    _MIN_QUERY_LENGTH,
    _needles_for_canonical,
    _normalize_for_match,
    extract_catalog_entities_from_text,
    find_near_match,
    match_entity,
    match_entity_with_ambiguity,
    match_entity_with_rows,
    query_has_ambiguous_entities,
    refresh_entity_matcher,
    reset_entity_matcher,
)
from app.db.database import SessionLocal
from app.db.models import Program, Provider
from app.schemas.program import ProgramCreate


def _insert_program(db: Session, provider_name: str) -> str:
    payload = ProgramCreate(
        title="Test activity for entity matcher",
        description="Twenty chars minimum here.",
        activity_category="sports",
        schedule_start_time="09:00",
        schedule_end_time="10:00",
        location_name="Lake Havasu City",
        provider_name=provider_name,
        tags=["entity_matcher_test"],
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


class EntityMatcherRowsTests(unittest.TestCase):
    def test_sonics_alias(self) -> None:
        canon = "Universal Gymnastics and All Star Cheer — Sonics"
        m = match_entity_with_rows("sonics gymnastics cost", [canon])
        self.assertIsNotNone(m)
        self.assertEqual(m[0], canon)
        self.assertGreater(m[1], 75.0)

    def test_altitude_short_name(self) -> None:
        canon = "Altitude Trampoline Park — Lake Havasu City"
        m = match_entity_with_rows("where is altitude trampoline park", [canon])
        self.assertIsNotNone(m)
        self.assertEqual(m[0], canon)

    def test_bmx_alias(self) -> None:
        canon = "Lake Havasu City BMX"
        m = match_entity_with_rows("how much does bmx cost", [canon])
        self.assertIsNotNone(m)
        self.assertEqual(m[0], canon)

    def test_mountain_bike_club_aliases(self) -> None:
        canon = "Lake Havasu Mountain Bike Club"
        for q in (
            "My son wants to ride mountain bikes. Any classes available?",
            "mountain biking trails in Havasu",
            "where can I mountain bike",
        ):
            with self.subTest(q=q):
                m = match_entity_with_rows(q, [canon])
                self.assertIsNotNone(m, msg=q)
                self.assertEqual(m[0], canon)
                self.assertGreater(m[1], 75.0)

    def test_below_threshold(self) -> None:
        m = match_entity_with_rows("quantum physics tutoring seattle", ["Lake Havasu City BMX"])
        self.assertIsNone(m)

    def test_fixture_file_exists(self) -> None:
        path = Path(__file__).resolve().parent / "fixtures" / "havasu_chat_test_queries.txt"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("DATE_LOOKUP", text)
        self.assertGreater(
            len([ln for ln in text.splitlines() if "|" in ln and not ln.strip().startswith("#")]),
            80,
        )


# ─────────── Backlog #50 — minimum-length floor at matcher entry ───────────
#
# Smoke catalog Class C2 (2026-05-08): single-char queries like ``"a"`` fuzzy-
# matched short canonical prefixes ("A & A Electronics Assembly", …). Fix:
# ``_MIN_QUERY_LENGTH = 3`` floor centralized in
# ``entity_matcher._normalize_for_match`` and used by every entry point.
#
# These tests pin the floor behavior across the four direct entry points and
# the helper itself. Floor is applied AFTER ``normalize()``, so whitespace-only
# / whitespace-padded short queries are also blocked.


class MinimumQueryLengthFloorTests(unittest.TestCase):
    """DB-free coverage via :func:`match_entity_with_rows` — the simplest entry
    point to exercise the floor in isolation. Parameterized over the six cases
    called out in the task scope."""

    _CANON = "Lake Havasu City BMX"

    def test_normalize_for_match_returns_empty_for_short_input(self) -> None:
        """Sanity check on the helper: short or empty input → empty string,
        so callers' existing ``if not norm: return …`` guards trigger."""
        self.assertEqual(_normalize_for_match(""), "")
        self.assertEqual(_normalize_for_match("  "), "")
        self.assertEqual(_normalize_for_match("a"), "")
        self.assertEqual(_normalize_for_match("ab"), "")
        # Whitespace-padded short input must also fail the floor — that's the
        # "post-normalize" contract: ``"  a  "`` normalizes to ``"a"`` (1 char)
        # and is rejected, even though the raw string was 5 chars long.
        self.assertEqual(_normalize_for_match("  a  "), "")
        # ≥3 chars of content → identity passthrough (post-normalize).
        self.assertEqual(_normalize_for_match("bmx"), "bmx")
        self.assertEqual(_normalize_for_match("BMX"), "bmx")
        self.assertEqual(_normalize_for_match("  bmx  "), "bmx")

    def test_min_query_length_constant_is_three(self) -> None:
        """Pin the floor at 3. Lowering it would re-open the C2 smoke regression;
        raising it would silently drop legitimate ``"bmx"`` / ``"mtb"`` / ``"dbr"``
        queries. A future tweak should be deliberate, not accidental."""
        self.assertEqual(_MIN_QUERY_LENGTH, 3)

    def test_floor_blocks_subthreshold_queries_via_match_entity_with_rows(self) -> None:
        """Each subthreshold query must return ``None`` from
        :func:`match_entity_with_rows`. Six cases per the task scope."""
        cases = [
            ("empty string", ""),
            ("pure whitespace", "   "),
            ("single char", "a"),
            ("two chars", "ab"),
            ("whitespace + 1 char (post-normalize check)", "  a  "),
            ("whitespace + 2 chars (post-normalize check)", "  ab  "),
        ]
        for label, query in cases:
            with self.subTest(label=label, query=repr(query)):
                self.assertIsNone(
                    match_entity_with_rows(query, [self._CANON]),
                    msg=f"floor should block {label!r}",
                )

    def test_three_char_query_passes_floor_and_reaches_match_logic(self) -> None:
        """At-floor queries (≥3 chars post-normalize) must reach scoring. ``"bmx"``
        is a curated alias for ``Lake Havasu City BMX`` and exists specifically as
        a short-query positive case."""
        hit = match_entity_with_rows("bmx", [self._CANON])
        self.assertIsNotNone(hit, "3-char query 'bmx' must clear the floor and match")
        assert hit is not None
        self.assertEqual(hit[0], self._CANON)
        self.assertGreater(hit[1], 75.0)

    def test_three_char_query_via_whitespace_padding_passes_floor(self) -> None:
        """``"  bmx  "`` normalizes to a 3-char string and must NOT be blocked
        by the floor. Pins the post-normalize ordering: the floor reads the
        normalized length, not the raw input length."""
        hit = match_entity_with_rows("  bmx  ", [self._CANON])
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], self._CANON)

    def test_needles_for_canonical_does_not_apply_query_side_floor(self) -> None:
        """Pin the index-side invariant: ``_needles_for_canonical`` deliberately
        calls ``normalize`` (not ``_normalize_for_match``), so 3-char curated
        aliases like ``"mtb"`` (in ``CANONICAL_EXTRAS`` for "Lake Havasu Mountain
        Bike Club") are still indexed. The floor is a query-side gate, never an
        index-side filter — a future "consistency-fix" pass that collapses the
        index-side ``normalize`` call to ``_normalize_for_match`` would silently
        drop the 3-char aliases and break short-query matches like ``"mtb"``.
        This test would catch that regression."""
        needles = _needles_for_canonical("Lake Havasu Mountain Bike Club")
        self.assertIn("mtb", needles)


class MinimumQueryLengthFloorEntryPointTests(unittest.TestCase):
    """Lock down the floor at every direct entry point, not just
    :func:`match_entity_with_rows`. Backlog #50 added the same floor to
    :func:`extract_catalog_entities_from_text`,
    :func:`match_entity` (via :func:`match_entity_with_ambiguity`), and
    :func:`find_near_match` — these tests prevent silent drift if a future
    refactor reintroduces a per-entry ``normalize`` call that bypasses the
    helper."""

    def setUp(self) -> None:
        reset_entity_matcher()
        self._ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._ids:
                row = db.get(Program, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_match_entity_floor_on_subthreshold_queries(self) -> None:
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            for label, query in (
                ("single char", "a"),
                ("two chars", "ab"),
                ("whitespace + 1 char", "  a  "),
                ("empty", ""),
            ):
                with self.subTest(label=label, query=repr(query)):
                    self.assertIsNone(
                        match_entity(query, db),
                        msg=f"match_entity must drop {label!r}",
                    )

    def test_extract_catalog_entities_floor_on_subthreshold_text(self) -> None:
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            for label, text in (
                ("single char", "a"),
                ("two chars", "ab"),
                ("pure whitespace", "   "),
            ):
                with self.subTest(label=label, text=repr(text)):
                    self.assertEqual(
                        extract_catalog_entities_from_text(text, db),
                        [],
                        msg=f"extract_catalog_entities_from_text must drop {label!r}",
                    )

    def test_find_near_match_floor_on_subthreshold_queries(self) -> None:
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            for label, query in (
                ("single char", "a"),
                ("two chars", "ab"),
                ("whitespace + 2 chars", "  ab  "),
            ):
                with self.subTest(label=label, query=repr(query)):
                    self.assertIsNone(
                        find_near_match(query, db),
                        msg=f"find_near_match must drop {label!r}",
                    )

    def test_match_entity_with_ambiguity_floor_on_subthreshold_queries(self) -> None:
        """Pins the delegation contract: ``match_entity`` and
        ``query_has_ambiguous_entities`` inherit the floor via
        ``match_entity_with_ambiguity``. A future refactor that re-introduces a
        direct ``normalize()`` call would silently bypass the floor and re-open
        #50's C2 regression for these direct entry points."""
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            for label, query in (
                ("single char", "a"),
                ("two chars", "ab"),
                ("whitespace + 1 char", "  a  "),
                ("whitespace + 2 chars", "  ab  "),
            ):
                with self.subTest(label=label, query=repr(query)):
                    hit, ambiguous = match_entity_with_ambiguity(query, db)
                    self.assertIsNone(
                        hit,
                        msg=f"match_entity_with_ambiguity must drop {label!r}",
                    )
                    self.assertFalse(
                        ambiguous,
                        msg=f"match_entity_with_ambiguity ambiguous flag must be False on {label!r}",
                    )

    def test_query_has_ambiguous_entities_floor_on_subthreshold_queries(self) -> None:
        """Pins the delegation contract: ``match_entity`` and
        ``query_has_ambiguous_entities`` inherit the floor via
        ``match_entity_with_ambiguity``. A future refactor that re-introduces a
        direct ``normalize()`` call would silently bypass the floor and re-open
        #50's C2 regression for these direct entry points."""
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            for label, query in (
                ("single char", "a"),
                ("two chars", "ab"),
                ("whitespace + 1 char", "  a  "),
                ("whitespace + 2 chars", "  ab  "),
            ):
                with self.subTest(label=label, query=repr(query)):
                    self.assertFalse(
                        query_has_ambiguous_entities(query, db),
                        msg=f"query_has_ambiguous_entities must return False on {label!r}",
                    )


class EntityMatcherDbTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_entity_matcher()
        self._ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._ids:
                row = db.get(Program, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_refresh_and_match_uses_distinct_providers(self) -> None:
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hit = match_entity("bmx track hours", db)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0], canon)

    def test_match_mountain_bike_generic_query(self) -> None:
        canon = "Lake Havasu Mountain Bike Club"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hit = match_entity(
                "My son wants to ride mountain bikes. Any classes available?",
                db,
            )
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0], canon)
        self.assertGreater(hit[1], 75.0)


class ExtractCatalogEntitiesFromTextTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_entity_matcher()
        self._ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._ids:
                row = db.get(Program, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_extract_one_provider_mentioned(self) -> None:
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hits = extract_catalog_entities_from_text(
                "Kids love the bmx track in Lake Havasu City on weekends.",
                db,
            )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].name, canon)
        self.assertEqual(hits[0].type, "provider")

    def test_extract_two_providers(self) -> None:
        a, b = "Lake Havasu City BMX", "Havasu Lanes"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, a))
            self._ids.append(_insert_program(db, b))
            refresh_entity_matcher(db)
            hits = extract_catalog_entities_from_text(
                "Check out Lake Havasu City BMX then bowl at Havasu Lanes.",
                db,
            )
        names = {h.name for h in hits}
        self.assertEqual(names, {a, b})
        for h in hits:
            self.assertEqual(h.type, "provider")

    def test_extract_empty_text(self) -> None:
        with SessionLocal() as db:
            refresh_entity_matcher(db)
            self.assertEqual(extract_catalog_entities_from_text("", db), [])
            self.assertEqual(extract_catalog_entities_from_text("   ", db), [])

    def test_extract_no_catalog_mentions(self) -> None:
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hits = extract_catalog_entities_from_text(
                "Quantum tutoring in Seattle has no local overlap here.",
                db,
            )
        self.assertEqual(hits, [])

    def test_extract_duplicate_canonical_once(self) -> None:
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._ids.append(_insert_program(db, canon))
            refresh_entity_matcher(db)
            hits = extract_catalog_entities_from_text(
                "Lake Havasu City BMX is fun. Visit Lake Havasu City BMX twice.",
                db,
            )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].name, canon)


def _insert_google_provider(
    db: Session,
    *,
    provider_name: str,
    is_active: bool = True,
    draft: bool = False,
) -> str:
    """Insert a Google-sourced Provider row for entity matcher tests (Slice A)."""
    p = Provider(
        provider_name=provider_name,
        category="food_drink",
        source="google_places",
        google_place_id=f"test_place_{provider_name.lower().replace(' ', '_')}",
        is_active=is_active,
        draft=draft,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


class EntityMatcherGoogleProviderTests(unittest.TestCase):
    """Slice A: refresh_entity_matcher must index active Provider rows from the
    unified providers table — including Google Places businesses — not just
    distinct Program.provider_name values."""

    def setUp(self) -> None:
        reset_entity_matcher()
        self._provider_ids: list[str] = []
        self._program_ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._provider_ids:
                row = db.get(Provider, pid)
                if row is not None:
                    db.delete(row)
            for pid in self._program_ids:
                row = db.get(Program, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_google_provider_matches_by_distinctive_name(self) -> None:
        canon = "Mudshark Brewing Company"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("phone number for mudshark brewing", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)
        self.assertGreater(hit[1], 75.0)

    def test_inactive_google_provider_excluded(self) -> None:
        canon = "Closed Down Diner"
        with SessionLocal() as db:
            self._provider_ids.append(
                _insert_google_provider(db, provider_name=canon, is_active=False)
            )
            refresh_entity_matcher(db)
            hit = match_entity("closed down diner hours", db)
        self.assertIsNone(hit)

    def test_draft_google_provider_excluded(self) -> None:
        canon = "Half Finished Cafe"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon, draft=True))
            refresh_entity_matcher(db)
            hit = match_entity("half finished cafe address", db)
        self.assertIsNone(hit)

    def test_program_and_provider_dedup(self) -> None:
        """Same provider_name in both Program and Provider tables yields one index entry."""
        canon = "Lake Havasu City BMX"
        with SessionLocal() as db:
            self._program_ids.append(_insert_program(db, canon))
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hits = extract_catalog_entities_from_text(
                f"Visit {canon} this weekend.",
                db,
            )
        self.assertEqual(len(hits), 1)
        assert hits
        self.assertEqual(hits[0].name, canon)

    def test_canonical_extras_still_apply_for_curated_names(self) -> None:
        """Curated synonyms in CANONICAL_EXTRAS keep working alongside the wider index."""
        canon = "Altitude Trampoline Park — Lake Havasu City"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("address for altitude", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)


class EntityMatcherIntentPaddingStripTests(unittest.TestCase):
    """Slice F6: queries with Tier-1 intent padding (e.g. "is mudshark open right now")
    must still match the canonical entity. Pre-fix these scored ~50–60 token_set_ratio
    against the canonical name and fell below the 75 threshold; the padded scorer
    strips the intent prefix/suffix and uses whichever form scores higher.
    """

    def setUp(self) -> None:
        reset_entity_matcher()
        self._provider_ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._provider_ids:
                row = db.get(Provider, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_open_now_padding_does_not_drop_match(self) -> None:
        canon = "Mudshark Brewing Company"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("is mudshark open right now", db)
        self.assertIsNotNone(hit, "padded query must still resolve the entity")
        assert hit is not None
        self.assertEqual(hit[0], canon)

    def test_phone_number_for_padding(self) -> None:
        canon = "Sloane's Pizzeria"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("phone number for sloane's", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)

    def test_what_are_the_hours_for_padding(self) -> None:
        canon = "Iron Wolf Golf & Country Club"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("what are the hours for iron wolf", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)

    def test_where_is_padding(self) -> None:
        canon = "The Foundry on the Green"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("where is the foundry", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)

    def test_padding_strip_does_not_create_false_positives(self) -> None:
        """A query that strips down to a generic word ("the") must NOT produce a match."""
        canon = "Some Random Business"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("phone number for the", db)
        self.assertIsNone(hit)


class EntityMatcherTypoToleranceTests(unittest.TestCase):
    """Slice F: partial_token_set_ratio added to _best_score so common typos
    ("mudsharks" → "Mudshark Brewery") still resolve without lowering the threshold."""

    def setUp(self) -> None:
        reset_entity_matcher()
        self._provider_ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._provider_ids:
                row = db.get(Provider, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_extra_trailing_s_resolves(self) -> None:
        canon = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("is mudsharks open right now", db)
        self.assertIsNotNone(
            hit, "trailing-s typo should still resolve via partial_token_set_ratio"
        )
        assert hit is not None
        self.assertEqual(hit[0], canon)

    def test_single_char_drop_resolves(self) -> None:
        canon = "The Foundry on the Green"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = match_entity("phone for the foundy", db)  # missing 'r'
        self.assertIsNotNone(hit, "single-char-drop typo should still resolve")
        assert hit is not None
        self.assertEqual(hit[0], canon)

    def test_typo_does_not_create_random_false_positive(self) -> None:
        """A typo on a query that has no near-match in the catalog must still return None."""
        canon = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            # Query about a totally different business — partial token matcher must
            # not dredge up Mudshark just because of letter overlap.
            hit = match_entity("phone for unknown plumbing service xyz", db)
        self.assertIsNone(hit)

    def test_typo_resolves_directly_when_strongly_distinctive(self) -> None:
        """Slice F: 'mudsharks brewry' is close enough to one Mudshark variant
        (Brewery, not Pizza) that the matcher should resolve it directly to Tier 1
        without surfacing the 'Did you mean X?' disambiguation."""
        with SessionLocal() as db:
            self._provider_ids.append(
                _insert_google_provider(db, provider_name="Mudshark Brewery and Public House")
            )
            self._provider_ids.append(
                _insert_google_provider(db, provider_name="Mudshark Pizza & Pasta")
            )
            refresh_entity_matcher(db)
            hit = match_entity("phone for mudsharks brewry", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], "Mudshark Brewery and Public House")
        # Must be above the strict 75 threshold (otherwise it'd hit the near-match
        # disambiguation path).
        self.assertGreater(hit[1], 75.0)

    def test_short_canonical_does_not_get_inflated_partial_score(self) -> None:
        """Regression: 'mudsharks brewry' must NOT match a 3-char canonical like 'DBR'
        via partial_token_set_ratio's substring fallback."""
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name="DBR"))
            self._provider_ids.append(_insert_google_provider(db, provider_name="Mudshark Brewery"))
            refresh_entity_matcher(db)
            hit = match_entity("phone for mudsharks brewry", db)
        # Must match Mudshark (the real intent), NOT DBR.
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], "Mudshark Brewery")


class EntityMatcherNearMatchTests(unittest.TestCase):
    """Slice F: 'Did you mean X?' disambiguation for queries scoring in the
    near-match band (55–75) — too far for an exact-match Tier 1 reply but close
    enough that the user is likely typing a real catalog name."""

    def setUp(self) -> None:
        reset_entity_matcher()
        self._provider_ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._provider_ids:
                row = db.get(Provider, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_severe_typo_returns_near_match(self) -> None:
        from app.chat.entity_matcher import find_near_match

        canon = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            # "mdshrkbrwry" — heavy typo (vowels dropped); scores ~65 in NEAR band.
            # "mudsharks brewry" by contrast resolves directly via the typo scorer
            # (covered in EntityMatcherTypoToleranceTests::test_typo_resolves_directly).
            hit = find_near_match("phone for mdshrkbrwry", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)

    def test_clean_match_does_not_return_near(self) -> None:
        """When the score is high enough for an exact match, find_near_match must
        return None so the router uses the Tier 1 path instead of disambiguating."""
        from app.chat.entity_matcher import find_near_match

        canon = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = find_near_match("is mudshark open right now", db)
        self.assertIsNone(hit)

    def test_unrelated_query_does_not_return_near(self) -> None:
        """No near-match for queries that don't resemble any canonical."""
        from app.chat.entity_matcher import find_near_match

        canon = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._provider_ids.append(_insert_google_provider(db, provider_name=canon))
            refresh_entity_matcher(db)
            hit = find_near_match("phone for completely unrelated business 123", db)
        self.assertIsNone(hit)


class EntityMatcherAmbiguityTests(unittest.TestCase):
    """Slice F §3.2: when multiple distinct providers tie above the threshold, the
    matcher returns None so the router can defer to Tier 3 disambiguation rather than
    Tier 1 picking arbitrarily.
    """

    def setUp(self) -> None:
        reset_entity_matcher()
        self._provider_ids: list[str] = []

    def tearDown(self) -> None:
        with SessionLocal() as db:
            for pid in self._provider_ids:
                row = db.get(Provider, pid)
                if row is not None:
                    db.delete(row)
            db.commit()
        reset_entity_matcher()

    def test_strong_tied_match_returns_alphabetic_pick_with_ambiguous_flag(self) -> None:
        """Slice F §3.2 (post-revert): on a tie, the matcher picks the alphabetically
        first canonical (deterministic) and SETS ``is_ambiguous=True`` so future
        callers can disambiguate without re-running the match."""
        from app.chat.entity_matcher import (
            match_entity_with_ambiguity,
            query_has_ambiguous_entities,
        )

        with SessionLocal() as db:
            self._provider_ids.append(
                _insert_google_provider(db, provider_name="Joes Pizza Downtown")
            )
            self._provider_ids.append(
                _insert_google_provider(db, provider_name="Joes Pizza Channel")
            )
            refresh_entity_matcher(db)
            hit = match_entity("phone for joes pizza", db)
            resolution, ambiguous = match_entity_with_ambiguity("phone for joes pizza", db)
            ambiguous_flag = query_has_ambiguous_entities("phone for joes pizza", db)
        # Both names tie at score 100 against the stripped "joes pizza"; alphabetical
        # tiebreak picks "Joes Pizza Channel" over "Joes Pizza Downtown".
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], "Joes Pizza Channel")
        self.assertIsNotNone(resolution)
        self.assertTrue(ambiguous, "ambiguous flag must still be True on near-ties")
        self.assertTrue(ambiguous_flag)

    def test_unambiguous_distinctive_match_still_works(self) -> None:
        """When one candidate clearly wins, the matcher still returns it (not None)."""
        from app.chat.entity_matcher import match_entity_with_ambiguity

        with SessionLocal() as db:
            self._provider_ids.append(
                _insert_google_provider(db, provider_name="Mudshark Brewing Company")
            )
            self._provider_ids.append(
                _insert_google_provider(db, provider_name="Cool Beans Coffee")
            )
            refresh_entity_matcher(db)
            hit = match_entity("phone for mudshark brewing", db)
            resolution, ambiguous = match_entity_with_ambiguity("phone for mudshark brewing", db)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], "Mudshark Brewing Company")
        self.assertIsNotNone(resolution)
        self.assertFalse(ambiguous)

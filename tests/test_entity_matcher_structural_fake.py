"""Phase 7.5.5 — structurally-fake token gate at the entity-matcher boundary.

Repros the false-positive did-you-mean bug surfaced in production: a junk query
like ``"When is the zzznonexistentevent999abc?"`` was passing the rapidfuzz
typo guard (because ``partial_ratio("zzznonexistentevent999abc", "steven") ≈
83.3`` clears the 80-point floor) and producing a wrong-entity near-match
("Closest match in the catalog is Biehn Steven A...").

The fix adds a per-token structural-fake heuristic to
:func:`app.chat.entity_matcher._normalize_for_match`. Any normalized query
containing a token shaped like a fabricated name (digit-run inside letters,
long low-vowel alphanumeric, or consonant-run + digits) is rejected at the
matcher boundary — every entry point ``match_entity``,
``match_entity_with_ambiguity``, ``find_near_match``,
``extract_catalog_entities_from_text``, and ``match_entity_with_rows``
returns the empty / None signal.

Load-bearing negative regressions:

- ``mdshrkbrwry`` (vowels-dropped severe typo for "mudshark brewery") — 11
  consonants, no digits, not ≥15 chars — MUST clear the gate and still
  surface Mudshark as a near-match (Backlog #44).
- Legitimate short canonicals/aliases (``"mtb"``, ``"bmx"``, ``"lhcbba"``,
  ``"sonics"``, ``"havasu"``) — must NOT trigger structural-fake.
"""
from __future__ import annotations

import unittest

from sqlalchemy.orm import Session

from app.chat.entity_matcher import (
    _normalize_for_match,
    _query_has_structurally_fake_token,
    _token_looks_structurally_fake,
    find_near_match,
    match_entity,
    match_entity_with_rows,
    refresh_entity_matcher,
    reset_entity_matcher,
)
from app.db.database import SessionLocal
from app.db.models import Provider


def _slug(name: str) -> str:
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", "—", "'", "&"):
            out.append("_")
    return "".join(out).strip("_")


def _insert_provider(db: Session, *, provider_name: str) -> str:
    p = Provider(
        provider_name=provider_name,
        category="health_medical",
        source="google_places",
        google_place_id=f"test_place_p755_{_slug(provider_name)}",
        is_active=True,
        draft=False,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


# ─── Unit tests for the structural-fake helpers (no DB) ───────────────────


class TokenLooksStructurallyFakeTests(unittest.TestCase):
    """Per-token heuristic — :func:`_token_looks_structurally_fake`."""

    # ---- Positive: structurally fake shapes ----

    def test_token_with_embedded_digit_run_flagged(self) -> None:
        """Token like ``event999abc`` (letters + 3-digit run) is junk-shaped."""
        self.assertTrue(_token_looks_structurally_fake("event999abc"))

    def test_token_with_long_alphanumeric_low_vowel_flagged(self) -> None:
        """The headline 25-char junk token — fires on the embedded-digit-run
        rule. Independently, the long+low-vowel rule (rule 2) also covers
        very-long no-digit junk like ``zzzzxkcdbqzzzxkcdbq`` (19 chars, 0%
        vowels). Pin both."""
        self.assertTrue(_token_looks_structurally_fake("zzznonexistentevent999abc"))
        self.assertTrue(_token_looks_structurally_fake("zzzzxkcdbqzzzxkcdbq"))

    def test_token_with_consonant_run_plus_digit_flagged(self) -> None:
        """``lhcbba999xyz`` style — 6+ consonants AND a digit."""
        self.assertTrue(_token_looks_structurally_fake("xkcdbzwx9"))

    def test_token_business_4042_flagged(self) -> None:
        """``business4042`` — letters + 3-digit run."""
        self.assertTrue(_token_looks_structurally_fake("business4042"))

    # ---- Negative: real or near-real tokens MUST NOT trigger ----

    def test_mdshrkbrwry_pure_consonant_typo_not_flagged(self) -> None:
        """Load-bearing Backlog #44 negative regression. ``mdshrkbrwry`` is 11
        consonants with 0 digits — must NOT be flagged so the severe-typo
        escape hatch in :func:`find_near_match` still surfaces Mudshark."""
        self.assertFalse(_token_looks_structurally_fake("mdshrkbrwry"))

    def test_real_short_aliases_not_flagged(self) -> None:
        for tok in ("mtb", "bmx", "lhcbba", "sonics", "havasu", "mudshark",
                    "steven", "biehn", "altitude", "foundry"):
            with self.subTest(tok=tok):
                self.assertFalse(_token_looks_structurally_fake(tok))

    def test_empty_token_not_flagged(self) -> None:
        self.assertFalse(_token_looks_structurally_fake(""))

    def test_pure_numeric_token_not_flagged(self) -> None:
        """Pure-numeric tokens like ``"2024"`` may be legitimate event years —
        the digit-run gate requires letters to be present."""
        self.assertFalse(_token_looks_structurally_fake("2024"))


class QueryHasStructurallyFakeTokenTests(unittest.TestCase):
    """Query-level: any one fake token taints the whole query."""

    def test_junk_query_with_embedded_token_flagged(self) -> None:
        """The headline repro: real intent words + one junk token = junk query."""
        self.assertTrue(
            _query_has_structurally_fake_token(
                "when is the zzznonexistentevent999abc"
            )
        )

    def test_clean_typo_query_not_flagged(self) -> None:
        """``phone for mdshrkbrwry`` has no fake-shaped tokens — only a
        legitimate severe typo."""
        self.assertFalse(_query_has_structurally_fake_token("phone for mdshrkbrwry"))

    def test_clean_real_query_not_flagged(self) -> None:
        self.assertFalse(
            _query_has_structurally_fake_token(
                "phone number for mudshark brewery"
            )
        )


class NormalizeForMatchStructuralFakeGateTests(unittest.TestCase):
    """The structural-fake gate sits inside :func:`_normalize_for_match` so
    every matcher entry point inherits it. Pin the gate at the helper level
    so callers don't need to repeat the check."""

    def test_junk_query_returns_empty_string(self) -> None:
        """``_normalize_for_match`` returns ``""`` for queries with a fake-
        shaped token. The empty-string return is the existing "no match"
        sentinel — callers already short-circuit on it."""
        self.assertEqual(
            _normalize_for_match("When is the zzznonexistentevent999abc?"),
            "",
        )

    def test_clean_typo_query_normalizes_through(self) -> None:
        """``phone for mdshrkbrwry`` (Backlog #44 spec case) must pass through
        the gate unchanged so the severe-typo escape hatch still fires."""
        self.assertEqual(
            _normalize_for_match("phone for mdshrkbrwry"),
            "phone for mdshrkbrwry",
        )


# ─── Integration tests against entry points with seeded catalog rows ───


class _MatcherTestBase(unittest.TestCase):
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

    def _seed(self, db: Session, names: list[str]) -> None:
        for name in names:
            self._provider_ids.append(_insert_provider(db, provider_name=name))
        refresh_entity_matcher(db)


class JunkQueryEntryPointTests(_MatcherTestBase):
    """End-to-end: a junk query must not surface a did-you-mean against a
    seeded person-style canonical (``"Biehn Steven A"`` is the production
    repro — ``"steven"`` matches the ``"even"`` substring of the junk token)."""

    def test_zzznonexistentevent_does_not_dym_to_person_via_find_near_match(self) -> None:
        """Headline regression — Phase 7.5.5 repro.

        Pre-fix: scores 57.1+ in the [55, 75) NEAR band and surfaces
        ``Closest match in the catalog is Biehn Steven A...``. Post-fix:
        the structural-fake gate empties the normalized query, so
        :func:`find_near_match` returns ``None``."""
        with SessionLocal() as db:
            self._seed(db, ["Biehn Steven A"])
            self.assertIsNone(
                find_near_match("When is the zzznonexistentevent999abc?", db),
                "junk query must not produce a did-you-mean against a "
                "person-style canonical (Phase 7.5.5)",
            )

    def test_zzznonexistentevent_does_not_direct_match(self) -> None:
        """Same junk query against :func:`match_entity` — also blocked."""
        with SessionLocal() as db:
            self._seed(db, ["Biehn Steven A"])
            self.assertIsNone(
                match_entity("When is the zzznonexistentevent999abc?", db),
            )

    def test_match_entity_with_rows_also_blocks_junk(self) -> None:
        """The DB-free entry point inherits the gate via
        ``_normalize_for_match`` — pin so a future refactor that bypasses
        the helper would fail this test."""
        self.assertIsNone(
            match_entity_with_rows(
                "When is the zzznonexistentevent999abc?",
                ["Biehn Steven A"],
            ),
        )


class StructuralFakeNegativeRegressionTests(_MatcherTestBase):
    """The fix must NOT regress the Backlog #44 severe-typo escape hatch."""

    def test_mdshrkbrwry_still_resolves_to_mudshark_as_near_match(self) -> None:
        """``phone for mdshrkbrwry`` clears the structural-fake gate (no
        digits, only 11 chars) and is still routed through the rapidfuzz
        near-match path — Mudshark must surface in the [55, 75) NEAR band."""
        canon = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._seed(db, [canon])
            hit = find_near_match("phone for mdshrkbrwry", db)
        self.assertIsNotNone(hit, "severe typo must still surface as did-you-mean (Backlog #44)")
        assert hit is not None
        self.assertEqual(hit[0], canon)
        self.assertGreaterEqual(hit[1], 55.0)
        self.assertLess(hit[1], 75.0)


if __name__ == "__main__":
    unittest.main()

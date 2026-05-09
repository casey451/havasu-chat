"""Adversarial regression tests for Backlog #46 — connector-word bypass.

Lane #44 (shipped 2026-05-08) introduced ``_best_partial_ratio_per_needle_token``
in ``app/chat/entity_matcher.py``. Independent code review + the voice-battery
agent investigation found the helper materially weakens the false-positive
guard for any needle containing a 3-char connector word ("and", "the", "for",
"jiu", "bmx", "one", "man") because ``partial_ratio`` of any 6+ char query
token vs a 3-char needle token returns ~80 (best 3-char window match).

These tests pin:

- **Class A** — connector-word bypass cases that must return no match once
  the guard is tightened (currently RED; will go green when the fix lands).
- **Class B** — the original Backlog #44 severe-typo cases that must continue
  to resolve (current spec — must stay green through the #46 fix).
- **Class C** — boundary cases (empty / single-char / numeric / short-canonical
  fallback) that must remain stable.

See ``docs/BACKLOG.md`` ("Backlog 46") for the full reproduction recipe and
voice-battery investigation table.
"""

from __future__ import annotations

import unittest

from sqlalchemy.orm import Session

from app.chat.entity_matcher import (
    find_near_match,
    match_entity,
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


def _insert_google_provider(db: Session, *, provider_name: str) -> str:
    """Insert an active non-draft Google-sourced Provider for entity-matcher tests.

    Mirrors the helper used in ``tests/test_entity_matcher.py`` so the index
    indexes both Program.provider_name and active Provider rows.
    """
    p = Provider(
        provider_name=provider_name,
        category="food_drink",
        source="google_places",
        google_place_id=f"test_place_b46_{_slug(provider_name)}",
        is_active=True,
        draft=False,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


class _MatcherTestBase(unittest.TestCase):
    """setUp/tearDown that resets the in-memory matcher index and removes
    any Provider rows seeded by the test."""

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
            self._provider_ids.append(_insert_google_provider(db, provider_name=name))
        refresh_entity_matcher(db)


class ConnectorWordBypassTests(_MatcherTestBase):
    """Backlog #46 Class A — connector-word bypass cases must return no match.

    These query/seed combinations triggered wrong-entity behavior in the live
    2,232-provider catalog after Lane #44. The mechanism: ``partial_ratio`` of
    any 6+ char query token vs a 3-char needle word ("and", "the", "for",
    "one", "man", "jiu", "bmx") returns ~80, so any needle containing such a
    connector passed the typo guard for almost any long query token. The fix
    tightens the guard to score only against substantive (≥5-char) needle
    tokens, restoring the intended behavior.

    Each test seeds only the *bypass-target* canonical (the entity that the
    bug wrongly surfaces) and asserts no match. After the fix, none of these
    canonicals should be reachable from the adversarial query.
    """

    def test_addrss_does_not_match_via_for_connector_word(self) -> None:
        """``phone for addrss`` must not surface ``Ross Dress for Less``.

        Pre-fix: scores 72.7 in NEAR band → ``did you mean Ross Dress for
        Less?``. ``addrss`` (6 chars) bypasses the per-token guard via
        ``partial_ratio("addrss", "for") ≈ 80``. See Backlog #46.
        """
        with SessionLocal() as db:
            self._seed(db, ["Ross Dress for Less"])
            self.assertIsNone(
                find_near_match("phone for addrss", db),
                "must not surface Ross Dress for Less as did-you-mean (Backlog #46)",
            )
            self.assertIsNone(
                match_entity("phone for addrss", db),
                "must not direct-match Ross Dress for Less (Backlog #46)",
            )

    def test_sloane_number_does_not_match_via_one_connector_word(self) -> None:
        """``sloane number`` must not match ``Number One Nails``.

        Pre-fix: scores 75.9 → Tier 1 wrong-entity dispatch. ``sloane`` (6
        chars) bypasses the per-token guard via the 3-char ``"one"`` token in
        ``Number One Nails``. See Backlog #46.
        """
        with SessionLocal() as db:
            self._seed(db, ["Number One Nails"])
            self.assertIsNone(
                match_entity("sloane number", db),
                "must not direct-match Number One Nails (Backlog #46)",
            )
            self.assertIsNone(
                find_near_match("sloane number", db),
                "must not surface Number One Nails as did-you-mean (Backlog #46)",
            )

    def test_mountian_biking_does_not_match_via_and_connector_word(self) -> None:
        """``mountian biking`` (typo) must not match a needle containing
        ``"and"``. Confirmed numerically by the voice-battery agent:
        ``partial_ratio("mountian", "and") = 80`` — exactly at the guard
        threshold. Mudshark Brewery and Public House is one of the affected
        canonicals listed in Backlog #46.
        """
        with SessionLocal() as db:
            self._seed(db, ["Mudshark Brewery and Public House"])
            self.assertIsNone(
                match_entity("mountian biking", db),
                "must not direct-match via 'and' connector (Backlog #46)",
            )
            self.assertIsNone(
                find_near_match("mountian biking", db),
                "must not surface as did-you-mean via 'and' connector (Backlog #46)",
            )

    def test_mudshark_address_does_not_match_altitude_via_lake_connector(self) -> None:
        """``mudshark address`` must not resolve to
        ``Altitude Trampoline Park — Lake Havasu City``. The 4-char ``"lake"``
        token in the canonical was within the lowered-floor pre-fix bypass.
        See Backlog #46 affected-canonicals sample list.
        """
        with SessionLocal() as db:
            self._seed(db, ["Altitude Trampoline Park — Lake Havasu City"])
            self.assertIsNone(
                match_entity("mudshark address", db),
                "must not cross-match Altitude (Backlog #46)",
            )
            self.assertIsNone(
                find_near_match("mudshark address", db),
                "must not surface Altitude as did-you-mean (Backlog #46)",
            )

    def test_ironwood_does_not_match_iron_man_via_short_token(self) -> None:
        """``ironwood`` must not cross-match ``Iron Man Triathlon``.

        Pre-fix: ``partial_ratio("ironwood", "iron") = 100`` (4-char
        substring) clears the guard, then WRatio + partial_token_set_ratio
        score high. Post-fix: the ≥5-char floor excludes ``"iron"`` and
        ``"man"`` from the guard targets, leaving only ``"triathlon"`` which
        has no substring overlap with ``"ironwood"``. See Backlog #46.
        """
        with SessionLocal() as db:
            self._seed(db, ["Iron Man Triathlon"])
            self.assertIsNone(
                match_entity("ironwood", db),
                "must not direct-match Iron Man Triathlon (Backlog #46)",
            )
            self.assertIsNone(
                find_near_match("ironwood", db),
                "must not surface Iron Man Triathlon as did-you-mean (Backlog #46)",
            )

    def test_tappp_does_not_match_jiu_or_bmx_short_token_needles(self) -> None:
        """``tappp`` must not match canonicals whose only short tokens are
        the 3-char ``"jiu"`` or ``"bmx"`` — both are explicitly listed in the
        Backlog #46 affected-canonicals sample.
        """
        with SessionLocal() as db:
            self._seed(db, ["The Tap Room Jiu Jitsu", "Lake Havasu City BMX"])
            self.assertIsNone(
                match_entity("tappp", db),
                "must not direct-match jiu/bmx-bearing canonical (Backlog #46)",
            )
            self.assertIsNone(
                find_near_match("tappp", db),
                "must not surface jiu/bmx-bearing canonical as did-you-mean (Backlog #46)",
            )


class OriginalNearMatchPreservationTests(_MatcherTestBase):
    """Backlog #46 Class B — Lane #44 fix cases that MUST continue to work.

    The #46 tightening must not regress the severe-typo behavior #44 enabled.
    These are spec-pinning tests for the fix lane. They are expected to pass
    *before* the fix lands (because #44 already shipped) and must remain
    green *after* the fix lands.
    """

    def test_mdshrkbrwry_resolves_to_mudshark_in_near_band(self) -> None:
        """The original Backlog #44 case: vowels-dropped severe typo →
        ``find_near_match`` returns Mudshark in the [55, 75) NEAR band so
        the router can offer ``did you mean Mudshark...?``."""
        canon = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._seed(db, [canon])
            hit = find_near_match("phone for mdshrkbrwry", db)
        self.assertIsNotNone(hit, "severe typo must surface as did-you-mean (Backlog #44)")
        assert hit is not None
        self.assertEqual(hit[0], canon)
        self.assertGreaterEqual(hit[1], 55.0, "score must be in NEAR band [55, 75)")
        self.assertLess(hit[1], 75.0, "score must be in NEAR band [55, 75)")

    def test_mudsharks_brewry_resolves_directly(self) -> None:
        """Mild typo → direct Tier 1 match (>75). Backlog #44 spec
        preservation.

        Query is wrapped with the ``phone for`` intent prefix because
        :func:`_best_score_padded` only runs the typo scorers (WRatio +
        partial_token_set_ratio) when the intent-strip *changes* the query.
        Bare ``"mudsharks brewry"`` runs only ``token_set_ratio`` (no
        token-set intersection vs the canonical) and falls below 75 by
        design — that's the existing Slice F behavior, not a #46 bug.
        """
        canon = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._seed(db, [canon])
            hit = match_entity("phone for mudsharks brewry", db)
        self.assertIsNotNone(hit, "mild typo must direct-match (Backlog #44)")
        assert hit is not None
        self.assertEqual(hit[0], canon)
        self.assertGreater(hit[1], 75.0)

    def test_the_foundy_resolves_directly(self) -> None:
        """Single-char-drop typo → direct Tier 1 match. Voice-battery agent
        verification table — must remain green through the #46 tightening."""
        canon = "The Foundry on the Green"
        with SessionLocal() as db:
            self._seed(db, [canon])
            hit = match_entity("phone for the foundy", db)
        self.assertIsNotNone(hit, "single-char-drop typo must direct-match")
        assert hit is not None
        self.assertEqual(hit[0], canon)
        self.assertGreater(hit[1], 75.0)


class EdgeCaseTests(_MatcherTestBase):
    """Backlog #46 Class C — boundary cases worth pinning so the fix doesn't
    inadvertently change behavior for trivial inputs."""

    def test_empty_query_returns_none(self) -> None:
        with SessionLocal() as db:
            self._seed(db, ["Mudshark Brewery and Public House"])
            self.assertIsNone(match_entity("", db))
            self.assertIsNone(find_near_match("", db))

    def test_single_character_query_does_not_match_seeded_canonical(self) -> None:
        """Single-char queries must not produce spurious matches against the
        seeded canonical. They MAY match real catalog entries that legitimately
        have single-char tokens (e.g. ``"Approved Gym X"`` matches query ``"x"``
        at 100% — that's correct matcher behavior, not a regression). The
        contract this test pins: the #46 connector-word tightening must not
        accidentally route trivial inputs to the test fixture."""
        seeded = "Mudshark Brewery and Public House"
        with SessionLocal() as db:
            self._seed(db, [seeded])
            match_result = match_entity("x", db)
            near_result = find_near_match("x", db)
        # Whatever the live catalog produces is acceptable; the seeded canonical
        # specifically must not be the answer to a single-char "x".
        if match_result is not None:
            self.assertNotEqual(match_result[0], seeded)
        if near_result is not None:
            self.assertNotEqual(near_result[0], seeded)

    def test_pure_numeric_query_returns_none(self) -> None:
        """A bare phone-number-shaped query must not resolve to any canonical
        — there's no entity content to match on."""
        with SessionLocal() as db:
            self._seed(db, ["Mudshark Brewery and Public House"])
            self.assertIsNone(match_entity("555 1234", db))
            self.assertIsNone(find_near_match("555 1234", db))

    def test_short_canonical_full_phrase_fallback_still_resolves(self) -> None:
        """When the seeded needle has no ≥5-char tokens (e.g. the 3-char
        canonical ``"DBR"``), ``_typo_guard_query_token_matches_needle``
        falls back to ``partial_ratio`` against the full phrase. The #46
        tightening (≥5-char floor on substantive needle tokens) must keep
        this fallback path live so short canonicals remain matchable.
        """
        with SessionLocal() as db:
            self._seed(db, ["DBR"])
            hit = match_entity("dbr", db)
        self.assertIsNotNone(hit, "short canonical must remain matchable post-#46")
        assert hit is not None
        self.assertEqual(hit[0], "DBR")

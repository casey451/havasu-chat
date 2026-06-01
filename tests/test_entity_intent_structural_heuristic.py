"""Unit tests for Phase 7.5.3 F1: _looks_structurally_fake heuristic and the
generalized query_mentions_fake_entity_marker behavior.

Red tests (would FAIL against pre-7.5.3 code where the function is a pure
whitelist regex): structurally fabricated names without marker tokens.

Green tests: real entities — including typo-shaped real entities — must NOT
trigger the heuristic. The Mudshark Brewery typo case is the load-bearing
negative-regression — F1 must not steal it from the rapidfuzz escape hatch in
near_match_subject_overlaps.
"""

from __future__ import annotations

import unittest

from app.chat.entity_intent import (
    _looks_structurally_fake,
    query_mentions_fake_entity_marker,
)


class LooksStructurallyFakeTests(unittest.TestCase):
    # ------- Positive: structurally-fake shapes (RED before F1) -------

    def test_high_digit_density_token_flagged(self) -> None:
        self.assertTrue(_looks_structurally_fake("Tell me about Joe 9999 Tavern Place"))

    def test_consonant_run_flagged(self) -> None:
        self.assertTrue(_looks_structurally_fake("Tell me about zzznonexistent fancy venue"))

    def test_long_query_with_consonant_run_flagged(self) -> None:
        self.assertTrue(_looks_structurally_fake("Where is xkcdbzzz Restaurant in Lake Havasu"))

    # ------- Negative regressions (must stay False) -------

    def test_mudshark_brewery_typo_not_flagged(self) -> None:
        # Phase 7.5.3 F1 load-bearing negative regression. mdshrkbrwry has a
        # 4-consonant run but the query is < 5 tokens so the short-circuit
        # protects it. The rapidfuzz escape hatch in
        # near_match_subject_overlaps must take precedence.
        self.assertFalse(_looks_structurally_fake("phone for mdshrkbrwry"))

    def test_heat_hotel_not_flagged(self) -> None:
        self.assertFalse(_looks_structurally_fake("Heat Hotel hours"))

    def test_short_query_skipped(self) -> None:
        # < 5 tokens — short-circuit.
        self.assertFalse(_looks_structurally_fake("zzznonexistent venue"))

    def test_empty_query_returns_false(self) -> None:
        self.assertFalse(_looks_structurally_fake(""))


class QueryMentionsFakeEntityMarkerTests(unittest.TestCase):
    # ------- Whitelist path preserved -------

    def test_xyz_marker_still_flagged(self) -> None:
        self.assertTrue(
            query_mentions_fake_entity_marker("Tell me about Totally Fake Business XYZ 404")
        )

    def test_zzz_marker_still_flagged(self) -> None:
        # Whitelist requires a word-boundary token (not "zzz" inside "zzznonexistent").
        self.assertTrue(query_mentions_fake_entity_marker("about zzz nonexistent venue"))

    # ------- Heuristic path (RED before F1) -------

    def test_unmarked_digit_density_flagged_via_heuristic(self) -> None:
        # No whitelist token; relies on _looks_structurally_fake.
        self.assertTrue(query_mentions_fake_entity_marker("Tell me about Joe 9999 Tavern Place"))

    # ------- Negative regressions -------

    def test_mudshark_brewery_typo_not_flagged(self) -> None:
        # Same load-bearing assertion at the function-level.
        self.assertFalse(query_mentions_fake_entity_marker("phone for mdshrkbrwry"))

    def test_heat_hotel_not_flagged(self) -> None:
        self.assertFalse(query_mentions_fake_entity_marker("rating for Heat Hotel"))

    def test_short_real_entity_not_flagged(self) -> None:
        self.assertFalse(query_mentions_fake_entity_marker("hours for Mudshark"))


if __name__ == "__main__":
    unittest.main()

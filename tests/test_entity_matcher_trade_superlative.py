"""BACKLOG #52 — trade-aligned superlative queries vs cross-category guard (#47)."""

from __future__ import annotations

import unittest

from app.chat.entity_matcher import (
    _category_guard_skips_row,
    _EntityRow,
    _needles_for_canonical,
    match_entity_with_rows,
    normalize,
)


class TradeSuperlativeBypassTests(unittest.TestCase):
    """#52 positives — same-trade rows stay eligible; integration smoke strings."""

    def test_allstar_gym_matches_universal_gymnastics_canonical(self) -> None:
        canon = "Universal Gymnastics and All Star Cheer — Sonics"
        hit = match_entity_with_rows("allstar gym", [canon])
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)
        self.assertGreater(hit[1], 75.0)

    def test_best_plumber_superlative_matches_all_seasons_canonical(self) -> None:
        canon = "All Seasons Plumbing"
        hit = match_entity_with_rows(
            "what is the best plumber in lake havasu",
            [canon],
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], canon)
        self.assertGreater(hit[1], 75.0)

    def test_same_trade_overlap_skips_guard_for_gym_row(self) -> None:
        canon = "Universal Gymnastics and All Star Cheer — Sonics"
        row = _EntityRow(canon, _needles_for_canonical(canon), "")
        q = normalize("allstar gym")
        self.assertFalse(_category_guard_skips_row(q, row))


class TradeSuperlativeNegativeRegressionTests(unittest.TestCase):
    """#47-style negatives — incompatible trades still drop rows."""

    def test_plumber_superlative_skips_bmx_row(self) -> None:
        canon = "Lake Havasu City BMX"
        row = _EntityRow(canon, _needles_for_canonical(canon), "sports")
        q = normalize("what is the best plumber in lake havasu")
        self.assertTrue(_category_guard_skips_row(q, row))

    def test_gym_superlative_skips_bmx_row(self) -> None:
        canon = "Lake Havasu City BMX"
        row = _EntityRow(canon, _needles_for_canonical(canon), "")
        q = normalize("allstar gym")
        self.assertTrue(_category_guard_skips_row(q, row))

    def test_plumber_superlative_skips_trampoline_park_row(self) -> None:
        canon = "Altitude Trampoline Park — Lake Havasu City"
        row = _EntityRow(canon, _needles_for_canonical(canon), "")
        q = normalize("what is the best plumber in lake havasu")
        self.assertTrue(_category_guard_skips_row(q, row))


class TradeSuperlativeEdgeCaseTests(unittest.TestCase):
    """Boundary rows for trade tagging + guard interaction."""

    def test_guard_not_applied_when_query_carries_no_trade_tags(self) -> None:
        row = _EntityRow(
            "Lake Havasu City BMX",
            _needles_for_canonical("Lake Havasu City BMX"),
            "",
        )
        q = normalize("lake havasu")
        self.assertFalse(_category_guard_skips_row(q, row))

    def test_gym_query_skips_row_without_gym_trade_signals(self) -> None:
        row = _EntityRow(
            "Some Generic Venue LLC",
            frozenset({"some generic venue llc"}),
            "event venue",
        )
        q = normalize("find the best gym in lake havasu today")
        self.assertTrue(_category_guard_skips_row(q, row))


if __name__ == "__main__":
    unittest.main()

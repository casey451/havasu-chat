"""Unit tests for app.categories.water_misfiled_rules.classify_water_misfiled_leaf.

Phase 4 (QA diagnostic 2026-06-12): only the unambiguous corrections fire
(detailing -> auto-marine-detailing, food/drink -> eat-drink). Genuine rentals
and marine repair/sales return None (left for Casey's per-row judgment).
"""

from __future__ import annotations

import unittest

from app.categories.water_misfiled_rules import classify_water_misfiled_leaf


class ClassifyWaterMisfiledLeafTests(unittest.TestCase):
    def test_detailing_shops_go_to_auto_marine_detailing(self) -> None:
        for name in (
            "928DesertDetailing",
            "Premier Detailing",
            "Mystique detailing llc",
            "RPM Detail",
            "Crown Mobile Detailing",
            "JT KUSTOM DETAILING",
            "Howard Custom Detail",
            "Above All Mobile Detailing",
        ):
            self.assertEqual(
                classify_water_misfiled_leaf(name), "auto-marine-detailing", name
            )

    def test_saloon_goes_to_eat_drink(self) -> None:
        self.assertEqual(classify_water_misfiled_leaf("Ghost Mine Saloon"), "eat-drink")

    def test_other_food_drink_markers(self) -> None:
        for name in ("Channel Tavern", "Lakeside Grill", "Havasu Brewery", "Channel Sports Bar"):
            self.assertEqual(classify_water_misfiled_leaf(name), "eat-drink", name)

    def test_genuine_rentals_untouched(self) -> None:
        for name in (
            "Arizona TikiToons Boat Rental",
            "Paradise Wild Wave Boat Rentals",
            "River Sports Boat Rentals",
            "Hooks Boat Rentals",
            "Arizona's Fun On The Water",
        ):
            self.assertIsNone(classify_water_misfiled_leaf(name), name)

    def test_marine_repair_and_sales_left_for_judgment(self) -> None:
        for name in (
            "Barrett Custom Marine",
            "Domn8er Power Boats",
            "Sun Country Marine Group",
            "IMAGE MARINE",
        ):
            self.assertIsNone(classify_water_misfiled_leaf(name), name)

    def test_bar_substring_does_not_false_match(self) -> None:
        # "Barrett" / "barber" must not trip the " bar" food/drink rule.
        self.assertIsNone(classify_water_misfiled_leaf("Barrett Custom Marine"))
        self.assertIsNone(classify_water_misfiled_leaf("Barber Marine Service"))

    def test_empty_name_returns_none(self) -> None:
        self.assertIsNone(classify_water_misfiled_leaf(""))
        self.assertIsNone(classify_water_misfiled_leaf(None))


if __name__ == "__main__":
    unittest.main()

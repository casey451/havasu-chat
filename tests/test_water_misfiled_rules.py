"""Unit tests for app.categories.water_misfiled_rules.classify_water_misfiled_leaf.

Phase 4 (QA diagnostic 2026-06-12): detailing -> auto-marine-detailing and
food/drink -> eat-drink (unambiguous). The Casey-approved (2026-06-12) marine
rule then maps supplier/store/dealer primary types -> boat-sales and explicit
marine-service names -> boat-repair-and-service, while genuine rentals/tours/
guides always return None — even though they are google "service"-typed too.
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

    def test_marine_dealers_go_to_boat_sales(self) -> None:
        # Sales is taken ONLY from the supplier/store/dealer primary type — names
        # alone never decide sales, because rentals share "marine" names.
        for name, primary in (
            ("R & D Marine", "Boat dealer"),
            ("Domn8er Power Boats", "Marine supplier"),
            ("Prestige Marine", "Boat dealer"),
            ("Xtreme Speed And Marine", "Outboard motor store"),
        ):
            self.assertEqual(
                classify_water_misfiled_leaf(name, primary), "boat-sales", name
            )

    def test_marine_service_shops_go_to_boat_repair(self) -> None:
        # Repair fires on explicit marine-service name markers (no supplier type).
        for name in (
            "Barrett Custom Marine",
            "Sun Country Marine Group",
            "IMAGE MARINE",
            "JandJ Performance & Marine Service",
            "Saleen Fiberglass Restoration",
            "Boat Body Shop",
            "Max Machine Worx",
        ):
            self.assertEqual(
                classify_water_misfiled_leaf(name), "boat-repair-and-service", name
            )

    def test_genuine_rentals_never_pulled_into_sales_or_repair(self) -> None:
        # Rentals are google "service"-typed too, so the name exclusion must win
        # before the sales/repair branches — never re-shelve a real rental.
        for name, primary in (
            ("Tortuga Boat Rentals", "Boat rental service"),
            ("Lake Havasu Jet Ski Rentals", "Personal watercraft rental service"),
            ("Arizona TikiToons Boat Rental", "Boat rental service"),
            ("Sunset Watersports Tours", "Boat tour agency"),
            ("Havasu Paddle Guide Co", "Tour operator"),
        ):
            self.assertIsNone(classify_water_misfiled_leaf(name, primary), name)

    def test_bar_substring_does_not_false_match(self) -> None:
        # "barber" must not trip the " bar" food/drink rule. Use names with no
        # marine/detailing markers so the result is purely the bar-guard's None.
        self.assertIsNone(classify_water_misfiled_leaf("Barber Shop On Main"))
        self.assertIsNone(classify_water_misfiled_leaf("Barrett Storage Yard"))

    def test_empty_name_returns_none(self) -> None:
        self.assertIsNone(classify_water_misfiled_leaf(""))
        self.assertIsNone(classify_water_misfiled_leaf(None))


if __name__ == "__main__":
    unittest.main()

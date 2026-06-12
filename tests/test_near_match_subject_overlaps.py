"""Unit tests for app.chat.entity_intent.near_match_subject_overlaps.

Red tests (q22 fix 2026-05-19): a fake-entity query that happens to share a
category word with a real catalog row must not pass the near-match guard.

Green tests: legitimate typo near-matches still pass.
"""

from __future__ import annotations

import unittest

from app.chat.entity_intent import (
    near_match_subject_overlaps,
    near_match_subject_tokens,
)


class NearMatchSubjectOverlapsTests(unittest.TestCase):
    def test_q22_fabricated_hotel_vs_real_hotel_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps("rating for Fabricated Hotel Name 555", "Heat Hotel")
        )

    def test_fake_restaurant_vs_real_restaurant_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps("hours for ZZZ Imaginary Restaurant", "Heat Restaurant")
        )

    def test_fake_gym_vs_real_gym_rejected(self) -> None:
        self.assertFalse(near_match_subject_overlaps("phone for Fake 999 Gym", "Iron Gym"))

    def test_only_category_word_in_query_rejected(self) -> None:
        self.assertFalse(near_match_subject_overlaps("rating for nowhere hotel", "Heat Hotel"))

    def test_typo_heat_hotell_passes(self) -> None:
        self.assertTrue(near_match_subject_overlaps("rating for Heat Hotell", "Heat Hotel"))

    def test_typo_heat_hote_passes(self) -> None:
        self.assertTrue(near_match_subject_overlaps("rating for Heat Hote", "Heat Hotel"))

    def test_severe_typo_mudshark_passes(self) -> None:
        self.assertTrue(
            near_match_subject_overlaps(
                "phone for mdshrkbrwry", "Mudshark Brewery and Public House"
            )
        )

    def test_partial_name_match_passes(self) -> None:
        self.assertTrue(
            near_match_subject_overlaps("phone for mudshark", "Mudshark Brewery and Public House")
        )

    def test_where_is_library_still_works(self) -> None:
        self.assertEqual(near_match_subject_tokens("where is the library"), frozenset({"library"}))

    def test_empty_query_returns_false(self) -> None:
        self.assertFalse(near_match_subject_overlaps("", "Heat Hotel"))

    def test_all_category_words_requires_shared_token(self) -> None:
        self.assertTrue(near_match_subject_overlaps("rating for the hotel", "Heat Hotel"))
        self.assertFalse(near_match_subject_overlaps("place near me", "Heat Hotel"))

    # Keyword-artifact guard (QA diagnostic 2026-06-12): a descriptive clause
    # that shares only a single generic word with a business name must not
    # surface that unrelated business. Each of these was an observed live
    # artifact on askhava.com.
    def test_descriptive_truck_clause_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps(
                "Where can I leave my truck and trailer all day?", "A Toe Truck"
            )
        )

    def test_descriptive_sunset_clause_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps("Where can we watch sunset without hiking?", "Sunset Plaza")
        )

    def test_descriptive_local_clause_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps(
                "Where are the local boutiques versus the big-box stores?", "The Local Craving"
            )
        )

    def test_descriptive_biting_right_clause_rejected(self) -> None:
        self.assertFalse(
            near_match_subject_overlaps(
                "What is biting right now, and where?", "Done Right Auto RV and Alignment"
            )
        )

    def test_single_generic_word_lookup_still_passes(self) -> None:
        # A genuine one-word lookup of a generically-named place is not an
        # artifact and must still resolve.
        self.assertTrue(near_match_subject_overlaps("sunset", "Sunset Plaza"))


if __name__ == "__main__":
    unittest.main()

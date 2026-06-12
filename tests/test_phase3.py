from __future__ import annotations

import unittest

from app.core.intent import detect_out_of_scope_category


class Phase3SearchTests(unittest.TestCase):
    def test_rain_triggers_out_of_scope(self) -> None:
        self.assertEqual(detect_out_of_scope_category("is it going to rain"), "weather")

    def test_restaurant_week_not_dining_redirect(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("restaurant week"))

    def test_weather_station_tour_not_weather_redirect(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("weather station tour"))

    # P1-1: bare "rain" substring no longer false-matches "training"/"drain".
    def test_rain_word_boundary_ignores_training_and_drain(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("personal training schedule"))
        self.assertIsNone(detect_out_of_scope_category("drain cleaning service"))

    def test_rain_whole_word_still_weather(self) -> None:
        self.assertEqual(detect_out_of_scope_category("will it rain tomorrow"), "weather")
        self.assertEqual(detect_out_of_scope_category("is it raining right now"), "weather")

    # P1-1: price adjectives are in scope (dining), not commercial out-of-scope.
    def test_cheap_eats_not_out_of_scope(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("cheap eats downtown"))
        self.assertIsNone(detect_out_of_scope_category("affordable restaurants near me"))

    # C5: lodging is no longer refused — it reaches the lodging_find resolver.
    def test_lodging_not_out_of_scope(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("where to stay in havasu"))
        self.assertIsNone(detect_out_of_scope_category("hotel near the lake"))
        self.assertIsNone(detect_out_of_scope_category("cheap motels in town"))

    # Birthday-party / party-venue queries are local-venue searches, not refused.
    def test_birthday_party_not_out_of_scope(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("where can I have a birthday party"))
        self.assertIsNone(detect_out_of_scope_category("good birthday party venue"))
        self.assertIsNone(detect_out_of_scope_category("wedding venue ideas"))

    # "book a table" / "venue for" are catalog provider/venue intents, not refused.
    def test_booking_and_venue_for_not_out_of_scope(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("book a table for two tonight"))
        self.assertIsNone(detect_out_of_scope_category("venue for a graduation party"))

    # Commercial bucket removed: rentals + hire are catalog provider/rental queries.
    def test_rentals_and_hire_not_out_of_scope(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("boat rental for the weekend"))
        self.assertIsNone(detect_out_of_scope_category("where can I rent a kayak"))
        self.assertIsNone(detect_out_of_scope_category("hire a plumber"))

    # P0-3 (QA diagnostic 2026-06-12): a soft trigger (parking / weather / car
    # rental) riding on an in-scope place/activity anchor is a catalog question,
    # not a refusal.
    def test_parking_with_place_anchor_not_out_of_scope(self) -> None:
        self.assertIsNone(
            detect_out_of_scope_category("Which beach has bathrooms, shade, and easy parking?")
        )
        self.assertIsNone(
            detect_out_of_scope_category("Which trailheads have shade, parking, or restrooms?")
        )
        self.assertIsNone(
            detect_out_of_scope_category("Which shopping area is easiest if I want simple parking?")
        )

    def test_weather_modifier_on_activity_not_out_of_scope(self) -> None:
        self.assertIsNone(
            detect_out_of_scope_category("Is there a heat advisory or weather reason not to hike today?")
        )
        self.assertIsNone(detect_out_of_scope_category("What is the water temperature today?"))
        self.assertIsNone(
            detect_out_of_scope_category("Is there a dog-friendly place to cool off in hot weather?")
        )

    def test_contingency_frame_not_out_of_scope(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("What happens if wind or weather turns bad?"))
        self.assertIsNone(
            detect_out_of_scope_category("What is the smart weather backup for wind or extreme heat?")
        )
        self.assertIsNone(
            detect_out_of_scope_category("What is the cancellation policy if the weather turns?")
        )

    def test_local_car_rental_not_out_of_scope(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("Can I rent a car or RV locally?"))

    # P0-3 must NOT over-correct: pure meteorology and hard transportation stay refused.
    def test_pure_weather_still_refused(self) -> None:
        self.assertEqual(detect_out_of_scope_category("What is the weather this weekend?"), "weather")
        self.assertEqual(detect_out_of_scope_category("What's the weather like in Lake Havasu?"), "weather")
        self.assertEqual(detect_out_of_scope_category("what's the forecast"), "weather")

    def test_hard_transportation_still_refused(self) -> None:
        self.assertEqual(detect_out_of_scope_category("how do I get to Phoenix"), "transportation")
        self.assertEqual(detect_out_of_scope_category("uber to the airport"), "transportation")
        self.assertEqual(detect_out_of_scope_category("how far to Parker Dam"), "transportation")


def test_lodging_phrasings_resolve_to_lodging_find() -> None:
    """C5 end-to-end at the resolver: the phrasings that used to be refused now
    route to the working lodging_find intent."""
    from app.chat.intents.resolver import resolve

    for phrase in ("where to stay in havasu", "hotel near the lake", "cheap motels in town"):
        resolved = resolve(phrase)
        assert resolved is not None, f"{phrase!r} fell through"
        assert resolved.intent_key == "lodging_find", (
            f"{phrase!r} routed to {resolved.intent_key}"
        )


if __name__ == "__main__":
    unittest.main()

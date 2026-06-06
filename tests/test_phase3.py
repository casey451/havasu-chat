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

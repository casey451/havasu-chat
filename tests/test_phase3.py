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


if __name__ == "__main__":
    unittest.main()

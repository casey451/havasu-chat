from __future__ import annotations

import unittest

from app.chat.tier1_templates import (
    CONTACT_FOR_PRICING,
    INTENT_PATTERNS,
    TEMPLATES,
    render,
)


class _Entity:
    """Minimal attribute-access entity for render() tests."""

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class RenderSuccessTests(unittest.TestCase):
    def test_date_lookup(self) -> None:
        out = render(
            "DATE_LOOKUP",
            _Entity(provider_name="Desert Storm Poker Run"),
            {"date": "April 20–27"},
            variant=0,
        )
        self.assertEqual(out, "The next Desert Storm Poker Run is April 20–27.")

    def test_time_lookup(self) -> None:
        out = render(
            "TIME_LOOKUP",
            _Entity(provider_name="Lake Havasu City BMX"),
            {"program": "BMX race", "time": "7pm"},
            variant=0,
        )
        self.assertEqual(out, "BMX race starts at 7pm.")

    def test_location_lookup(self) -> None:
        out = render(
            "LOCATION_LOOKUP",
            {"provider_name": "Ballet Havasu", "address": "2126 McCulloch Blvd N"},
            variant=0,
        )
        self.assertEqual(out, "Ballet Havasu is at 2126 McCulloch Blvd N.")

    def test_phone_lookup(self) -> None:
        out = render(
            "PHONE_LOOKUP",
            _Entity(provider_name="Havasu Lanes", phone="(928) 764-1404"),
            variant=0,
        )
        self.assertEqual(out, "Havasu Lanes: (928) 764-1404.")

    def test_hours_lookup(self) -> None:
        out = render(
            "HOURS_LOOKUP",
            _Entity(provider_name="Altitude", hours="Mon–Sat 10a–9p"),
            variant=1,
        )
        self.assertEqual(out, "Hours: Mon–Sat 10a–9p.")

    def test_hours_lookup_weekday_with_pipe_hours_focuses_day(self) -> None:
        hours = "Sun 11am–7pm | Fri 11am–8pm | Sat 9am–9pm"
        out = render(
            "HOURS_LOOKUP",
            _Entity(provider_name="Altitude Trampoline Park — Lake Havasu City", hours=hours),
            {"normalized_query": "is altitude open late on friday"},
            variant=0,
        )
        self.assertIsNotNone(out)
        low = out.lower()
        self.assertIn("friday", low)
        self.assertIn("11am", low)
        self.assertNotIn("|", out)

    def test_hours_lookup_weekday_non_pipe_hours_keeps_full_dump(self) -> None:
        out = render(
            "HOURS_LOOKUP",
            _Entity(provider_name="Co", hours="Mon–Sun 9:00 AM – 8:00 PM"),
            {"normalized_query": "what are co hours on tuesday"},
            variant=1,
        )
        self.assertIsNotNone(out)
        self.assertIn("Mon", out)

    def test_hours_lookup_closed_day_segment(self) -> None:
        out = render(
            "HOURS_LOOKUP",
            _Entity(provider_name="Iron Wolf", hours="Mon 9a–9p | Tue CLOSED | Wed 9a–9p"),
            {"normalized_query": "is iron wolf open on tuesday"},
            variant=0,
        )
        self.assertIsNotNone(out)
        low = out.lower()
        self.assertIn("closed", low)
        self.assertIn("tuesday", low)

    def test_hours_day_long_display_name_uses_is_open_not_possessive(self) -> None:
        """Multi-word / long short names avoid \"Club's open\" (Phase 6.1.4)."""
        out = render(
            "HOURS_LOOKUP",
            _Entity(
                provider_name="Iron Wolf Golf & Country Club",
                hours="Mon 9am–9pm | Tue 9am–9pm",
            ),
            {"normalized_query": "is iron wolf open on monday"},
            variant=0,
        )
        self.assertIsNotNone(out)
        low = out.lower()
        self.assertIn("is open", low)
        self.assertIn("monday", low)
        self.assertNotRegex(low, r"country club's open")

    def test_hours_day_short_display_name_allows_possessive_open(self) -> None:
        out = render(
            "HOURS_LOOKUP",
            _Entity(provider_name="Iron Wolf", hours="Mon 9a–9p | Tue 9a–9p"),
            {"normalized_query": "is iron wolf open on monday"},
            variant=0,
        )
        self.assertIsNotNone(out)
        low = out.lower()
        self.assertRegex(low, r"iron wolf's open|iron wolf runs")

    def test_website_lookup(self) -> None:
        out = render(
            "WEBSITE_LOOKUP",
            _Entity(provider_name="Iron Wolf", website="ironwolfgcc.com"),
            variant=0,
        )
        self.assertEqual(out, "Iron Wolf: ironwolfgcc.com")

    def test_age_lookup_uses_program_from_data(self) -> None:
        out = render(
            "AGE_LOOKUP",
            _Entity(provider_name="Lake Havasu Little League"),
            {"program": "Little League", "age_range": "5–12"},
            variant=0,
        )
        self.assertEqual(out, "Little League is for ages 5–12.")

    def test_cost_lookup_normal(self) -> None:
        out = render(
            "COST_LOOKUP",
            _Entity(provider_name="Altitude"),
            {"cost": "$20/hr"},
            variant=0,
        )
        self.assertEqual(out, "Altitude is $20/hr.")


class CostContactForPricingTests(unittest.TestCase):
    def test_sentinel_cost_switches_variant(self) -> None:
        out = render(
            "COST_LOOKUP",
            _Entity(provider_name="Iron Wolf", phone="(928) 764-1404"),
            {"cost": CONTACT_FOR_PRICING},
            variant=0,
        )
        self.assertEqual(out, "Iron Wolf doesn't post pricing — call (928) 764-1404.")

    def test_show_pricing_cta_with_null_cost(self) -> None:
        out = render(
            "COST_LOOKUP",
            _Entity(provider_name="Sonics", phone="(928) 555-0100", show_pricing_cta=True),
            {"cost": None},
            variant=1,
        )
        self.assertEqual(out, "No public pricing. Call Sonics at (928) 555-0100.")

    def test_contact_variant_without_phone_returns_none(self) -> None:
        out = render(
            "COST_LOOKUP",
            _Entity(provider_name="Sonics", show_pricing_cta=True),
            {"cost": None},
            variant=0,
        )
        self.assertIsNone(out)


class HoursClosedTodayTests(unittest.TestCase):
    def test_closed_today_switches_variant(self) -> None:
        out = render(
            "HOURS_LOOKUP",
            _Entity(provider_name="Iron Wolf", hours="Mon 9a–9p | Tue CLOSED"),
            {"closed_today": True},
            variant=0,
        )
        self.assertEqual(out, "Iron Wolf is closed today.")


class MissingSlotTests(unittest.TestCase):
    def test_missing_date_returns_none(self) -> None:
        self.assertIsNone(render("DATE_LOOKUP", _Entity(provider_name="Anything"), {}))

    def test_missing_address_returns_none(self) -> None:
        self.assertIsNone(render("LOCATION_LOOKUP", _Entity(provider_name="Foo"), None))

    def test_missing_phone_returns_none(self) -> None:
        self.assertIsNone(render("PHONE_LOOKUP", _Entity(provider_name="Foo"), None))

    def test_unknown_intent_returns_none(self) -> None:
        self.assertIsNone(render("MULTI_INTENT", _Entity(provider_name="Foo"), None))

    def test_no_entity_returns_none(self) -> None:
        self.assertIsNone(render("PHONE_LOOKUP", None, {"phone": "555"}))

    def test_empty_cost_string_falls_through(self) -> None:
        # Empty cost with no CTA flag → can't fill template → None
        self.assertIsNone(
            render("COST_LOOKUP", _Entity(provider_name="Foo"), {"cost": ""})
        )


class IntentPatternTests(unittest.TestCase):
    def _first_match(self, query: str) -> str | None:
        for intent, pattern in INTENT_PATTERNS:
            if pattern.search(query):
                return intent
        return None

    def test_website_beats_other_intents(self) -> None:
        self.assertEqual(self._first_match("iron wolf golf website"), "WEBSITE_LOOKUP")

    def test_phone_lookup(self) -> None:
        self.assertEqual(self._first_match("havasu lanes phone number"), "PHONE_LOOKUP")

    def test_age_lookup(self) -> None:
        self.assertEqual(self._first_match("what age is bmx for"), "AGE_LOOKUP")

    def test_cost_lookup(self) -> None:
        self.assertEqual(self._first_match("how much is altitude"), "COST_LOOKUP")

    def test_time_before_hours(self) -> None:
        self.assertEqual(self._first_match("what time does altitude open"), "TIME_LOOKUP")

    def test_hours_lookup(self) -> None:
        self.assertEqual(self._first_match("what are altitude hours"), "HOURS_LOOKUP")

    def test_hours_open_late_and_early_phrases(self) -> None:
        self.assertEqual(self._first_match("is altitude open late on friday"), "HOURS_LOOKUP")
        self.assertEqual(self._first_match("is sonics open early on monday"), "HOURS_LOOKUP")

    def test_close_time_stays_time_lookup_when_what_time_present(self) -> None:
        self.assertEqual(
            self._first_match("what time does altitude close on friday"),
            "TIME_LOOKUP",
        )

    def test_open_now_hours(self) -> None:
        self.assertEqual(self._first_match("is altitude open right now"), "HOURS_LOOKUP")

    def test_location_lookup(self) -> None:
        self.assertEqual(self._first_match("where is altitude trampoline park"), "LOCATION_LOOKUP")

    def test_date_lookup(self) -> None:
        self.assertEqual(self._first_match("when is desert storm poker run"), "DATE_LOOKUP")


class TemplateInventoryTests(unittest.TestCase):
    def test_all_tier1_intents_have_variants(self) -> None:
        for intent in (
            "DATE_LOOKUP",
            "TIME_LOOKUP",
            "LOCATION_LOOKUP",
            "COST_LOOKUP",
            "PHONE_LOOKUP",
            "HOURS_LOOKUP",
            "WEBSITE_LOOKUP",
            "AGE_LOOKUP",
        ):
            self.assertIn(intent, TEMPLATES, msg=f"missing intent: {intent}")
            self.assertGreaterEqual(len(TEMPLATES[intent]), 1)

    def test_cost_contact_and_hours_closed_variants_exist(self) -> None:
        self.assertIn("COST_LOOKUP_CONTACT", TEMPLATES)
        self.assertIn("HOURS_LOOKUP_CLOSED_TODAY", TEMPLATES)


if __name__ == "__main__":
    unittest.main()

"""Phase 8.5 — search & intent architecture rewrite."""

from __future__ import annotations

import unittest

from app.core.intent import (
    ADD_EVENT,
    DEAL_SEARCH,
    GREETING,
    LISTING_INTENT,
    OUT_OF_SCOPE,
    REFINEMENT,
    SEARCH_EVENTS,
    SERVICE_REQUEST,
    detect_intent,
    detect_out_of_scope_category,
    is_hard_reset,
    is_soft_cancel,
)
from app.core.search import decide_search_strategy, format_search_results
from app.core.session import get_session, set_flow_awaiting
from app.core.slots import extract_activity_family, extract_audience, extract_date_range, merge_date_range


class Phase85IntentTests(unittest.TestCase):
    def test_single_word_activity_search(self) -> None:
        self.assertEqual(detect_intent("golf", {}), SEARCH_EVENTS)
        self.assertEqual(detect_intent("Pickleball?", {}), SEARCH_EVENTS)

    def test_hosting_with_date_add_event(self) -> None:
        self.assertEqual(
            detect_intent("I'm hosting a kids workshop Saturday at 10 at the library", {}),
            ADD_EVENT,
        )

    def test_hosting_without_date_is_search(self) -> None:
        self.assertEqual(detect_intent("I'm hosting a workshop?", {}), SEARCH_EVENTS)

    def test_can_i_add_event_is_add_intent(self) -> None:
        self.assertEqual(detect_intent("Can I add an event?", {}), ADD_EVENT)

    def test_listing_intent(self) -> None:
        self.assertEqual(detect_intent("show me all", {}), LISTING_INTENT)
        self.assertEqual(detect_intent("what events are this weekend?", {}), LISTING_INTENT)

    def test_hard_reset(self) -> None:
        self.assertTrue(is_hard_reset("start over"))
        self.assertTrue(is_hard_reset("please reset"))

    def test_soft_cancel(self) -> None:
        self.assertTrue(is_soft_cancel("never mind"))
        self.assertTrue(is_soft_cancel("nvm"))

    def test_greeting_idle(self) -> None:
        self.assertEqual(detect_intent("hello", {}), GREETING)

    def test_refinement_when_narrow_awaiting(self) -> None:
        s = get_session("p85-refine")
        set_flow_awaiting(s, "narrow_followup")
        self.assertEqual(detect_intent("tennis", s), REFINEMENT)

    def test_greeting_during_narrow(self) -> None:
        s = get_session("p85-greet-narrow")
        set_flow_awaiting(s, "narrow_followup")
        self.assertEqual(detect_intent("hi", s), GREETING)

    def test_stubs(self) -> None:
        self.assertEqual(detect_intent("who does plumbing around here", {}), SERVICE_REQUEST)
        self.assertEqual(detect_intent("any happy hour deals", {}), DEAL_SEARCH)

    def test_out_of_scope_weather(self) -> None:
        self.assertEqual(detect_intent("what's the weather this weekend", {}), OUT_OF_SCOPE)

    def test_out_of_scope_lodging(self) -> None:
        self.assertEqual(detect_intent("where should I stay in Havasu", {}), OUT_OF_SCOPE)

    def test_event_indicator_overrides_out_of_scope(self) -> None:
        self.assertEqual(
            detect_intent("hotel grand opening event tonight", {}),
            SEARCH_EVENTS,
        )

    def test_add_an_event_phrase_is_add_intent(self) -> None:
        self.assertEqual(detect_intent("add an event", {}), ADD_EVENT)

    def test_commercial_services_cheap_rental(self) -> None:
        self.assertEqual(detect_intent("cheap boat rental", {}), OUT_OF_SCOPE)
        self.assertEqual(detect_out_of_scope_category("cheap boat rental"), "commercial_services")

    def test_commercial_services_book_table(self) -> None:
        self.assertEqual(detect_intent("book me a table", {}), OUT_OF_SCOPE)
        self.assertEqual(detect_out_of_scope_category("book me a table"), "commercial_services")

    def test_rental_event_phrase_not_commercial(self) -> None:
        self.assertIsNone(detect_out_of_scope_category("boat rental event on Saturday"))


class Phase85SlotTests(unittest.TestCase):
    def test_weekend_then_next_week_overwrites_date(self) -> None:
        d1 = extract_date_range("this weekend")
        d2 = extract_date_range("next week")
        assert d1 and d2
        merged = merge_date_range(d1, d2)
        self.assertEqual(merged, d2)

    def test_kids_weekend_one_message(self) -> None:
        msg = "kids stuff this weekend"
        self.assertIsNotNone(extract_date_range(msg))
        self.assertEqual(extract_audience(msg), "kids")

    def test_soccer_maps_sports(self) -> None:
        self.assertEqual(extract_activity_family("soccer clinic"), "sports")

    def test_first_friday_does_not_set_next_friday_date_range(self) -> None:
        self.assertIsNone(extract_date_range("first friday"))


class Phase85StrategyTests(unittest.TestCase):
    def test_listing_mode_broad(self) -> None:
        self.assertEqual(decide_search_strategy({}, True, "show me all"), "RUN_BROAD")

    def test_date_only_nudge(self) -> None:
        dr = extract_date_range("this weekend")
        slots = {"date_range": dr, "activity_family": None, "audience": None, "location_hint": None}
        self.assertEqual(decide_search_strategy(slots, False, "this weekend"), "RUN_WITH_NUDGE")

    def test_date_and_activity_filtered(self) -> None:
        dr = extract_date_range("Saturday")
        slots = {"date_range": dr, "activity_family": "sports", "audience": None, "location_hint": None}
        self.assertEqual(decide_search_strategy(slots, False, "sports Saturday"), "RUN_FILTERED")

    def test_open_ended_clarify(self) -> None:
        self.assertEqual(decide_search_strategy({}, False, "what's good?"), "CLARIFY_DATE")


class Phase85FormatTests(unittest.TestCase):
    def test_zero_slots_empty_copy(self) -> None:
        text = format_search_results([], "RUN_WITH_NUDGE", {})
        self.assertIn("Nothing yet", text)


if __name__ == "__main__":
    unittest.main()

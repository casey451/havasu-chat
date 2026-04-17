"""Phase 8.5 — search & intent architecture rewrite."""

from __future__ import annotations

import time
import unittest
from fastapi.testclient import TestClient

from app.core.conversation_copy import CLARIFY_DATE, HARD_RESET_REPLY, SOFT_CANCEL_REPLY
from app.core.intent import (
    ADD_EVENT,
    DEAL_SEARCH,
    GREETING,
    HARD_RESET,
    LISTING_INTENT,
    OUT_OF_SCOPE,
    REFINEMENT,
    SEARCH_EVENTS,
    SERVICE_REQUEST,
    SOFT_CANCEL,
    detect_intent,
    is_hard_reset,
    is_soft_cancel,
)
from app.core.search import decide_search_strategy, format_search_results
from app.core.session import clear_session_state, get_flow, get_search, get_session, set_flow_awaiting
from app.core.slots import extract_activity_family, extract_audience, extract_date_range, merge_date_range
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app
from app.schemas.event import EventCreate


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


class Phase85RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(Event).delete()
            db.commit()
        for sid in (
            "p85-hard",
            "p85-soft",
            "p85-stale",
            "p85-escape",
            "p85-clarify",
            "p85-e2e",
        ):
            clear_session_state(sid)

    def test_hard_reset_reply(self) -> None:
        r = self.__class__.client.post("/chat", json={"session_id": "p85-hard", "message": "start over"})
        self.assertEqual(r.json()["intent"], HARD_RESET)
        self.assertEqual(r.json()["response"], HARD_RESET_REPLY)

    def test_soft_cancel_reply(self) -> None:
        self.__class__.client.post("/chat", json={"session_id": "p85-soft", "message": "golf"})
        r = self.__class__.client.post("/chat", json={"session_id": "p85-soft", "message": "never mind"})
        self.assertEqual(r.json()["intent"], SOFT_CANCEL)
        self.assertEqual(r.json()["response"], SOFT_CANCEL_REPLY)

    def test_stale_clears_await_keeps_slots(self) -> None:
        sid = "p85-stale"
        s = get_session(sid)
        get_search(s)["slots"]["audience"] = "kids"
        set_flow_awaiting(s, "clarify_date")
        s["blocking_mono"] = time.monotonic() - 400
        r = self.__class__.client.post("/chat", json={"session_id": sid, "message": "this weekend"})
        self.assertEqual(r.status_code, 200, msg=r.text)
        body = r.json()
        self.assertIn("response", body)
        self.assertIn("cleared where we left off", body["response"].lower())
        s2 = get_session(sid)
        self.assertIsNone(get_flow(s2).get("awaiting"))

    def test_escape_from_add_to_search(self) -> None:
        c = self.__class__.client
        c.post(
            "/chat",
            json={
                "session_id": "p85-escape",
                "message": (
                    "basketball camp Saturday at 9 at aquatic center "
                    "https://example.com/x info 928-555-0100"
                ),
            },
        )
        r = c.post(
            "/chat",
            json={"session_id": "p85-escape", "message": "actually I was just looking for what's on"},
        )
        self.assertEqual(r.json()["intent"], "SEARCH_EVENTS")
        self.assertIn("switching gears", r.json()["response"].lower())

    def test_clarify_then_weekend(self) -> None:
        c = self.__class__.client
        r1 = c.post("/chat", json={"session_id": "p85-clarify", "message": "what's good?"})
        self.assertEqual(r1.json()["response"], CLARIFY_DATE)
        r2 = c.post("/chat", json={"session_id": "p85-clarify", "message": "this weekend"})
        self.assertEqual(r2.json()["intent"], "SEARCH_EVENTS")


class Phase85FormatTests(unittest.TestCase):
    def test_zero_slots_empty_copy(self) -> None:
        text = format_search_results([], "RUN_WITH_NUDGE", {})
        self.assertIn("Nothing yet", text)


class Phase85E2EScenario(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        clear_session_state("p85-e2e")
        dr = extract_date_range("next week")
        assert dr is not None
        event_day = dr["start"]
        with SessionLocal() as db:
            db.query(Event).delete()
            for title, fam in (
                ("Kids Soccer Fun", "soccer for kids"),
                ("Kids Art Hour", "painting for children"),
                ("Adult Jazz Night", "music for adults"),
            ):
                db.add(
                    Event.from_create(
                        EventCreate(
                            title=title,
                            date=event_day,
                            start_time="10:00:00",
                            end_time=None,
                            location_name="Community Center",
                            description=f"{fam} — community program with local instructors and supplies included.",
                            event_url="https://example.com/e",
                            contact_name="Alex",
                            contact_phone="928-555-0100",
                            tags=[],
                            embedding=None,
                            status="live",
                            created_by="user",
                            admin_review_by=None,
                        )
                    )
                )
            db.commit()

    def test_kids_weekend_then_listing_then_sports(self) -> None:
        c = self.__class__.client
        r1 = c.post(
            "/chat",
            json={"session_id": "p85-e2e", "message": "Any events for kids next week?"},
        )
        self.assertIn("Kids", r1.json()["response"])
        r2 = c.post("/chat", json={"session_id": "p85-e2e", "message": "show me all"})
        self.assertEqual(r2.json()["intent"], LISTING_INTENT)
        r3 = c.post("/chat", json={"session_id": "p85-e2e", "message": "sports"})
        self.assertIn("Soccer", r3.json()["response"])


if __name__ == "__main__":
    unittest.main()

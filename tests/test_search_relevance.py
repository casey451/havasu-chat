"""Search relevance: honest no-match, thresholds, listing (quality pass)."""

from __future__ import annotations

import unittest
from datetime import date, time as time_type, timedelta

from fastapi.testclient import TestClient

from app.core.session import clear_session_state
from app.core.slots import extract_date_range
from app.db.database import SessionLocal
from app.db.models import Event
from app.main import app
from app.schemas.event import EventCreate


def _sat() -> date:
    dr = extract_date_range("this weekend")
    assert dr is not None
    return dr["start"]


class SearchRelevanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def setUp(self) -> None:
        for sid in ("rel-gym", "rel-yoga", "rel-kids", "rel-list"):
            clear_session_state(sid)
        with SessionLocal() as db:
            db.query(Event).delete()
            db.commit()

    def test_short_noun_query_requires_literal_match(self) -> None:
        future_day = date.today() + timedelta(days=20)
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Country Divas Concert",
                        date=future_day,
                        start_time="19:00:00",
                        end_time=None,
                        location_name="Havasu Landing Casino",
                        description="Live country concert with dinner and drinks.",
                        event_url="https://example.com/country-divas",
                        contact_name=None,
                        contact_phone="928-555-0109",
                        tags=["music", "concert"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        r = self.__class__.client.post("/chat", json={"session_id": "rel-gym", "message": "rodeo"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["count"], 0)

    def test_synonym_counts_as_literal_match(self) -> None:
        future_day = date.today() + timedelta(days=21)
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Desert Storm Poker Run",
                        date=future_day,
                        start_time="14:00:00",
                        end_time=None,
                        location_name="Bridgewater Channel",
                        description="Performance boating poker run and speedboat showcase.",
                        event_url="https://example.com/desert-storm",
                        contact_name=None,
                        contact_phone="928-555-0110",
                        tags=["boating", "poker run"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        r = self.__class__.client.post("/chat", json={"session_id": "rel-gym", "message": "regatta"})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["data"]["count"], 1)
        self.assertIn("Desert Storm Poker Run", r.json()["response"])

    def test_sunset_market_matches_market_event(self) -> None:
        future_day = date.today() + timedelta(days=24)
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Havasu Sunset Market",
                        date=future_day,
                        start_time="18:00:00",
                        end_time=None,
                        location_name="Downtown Lake Havasu",
                        description="Sunset market with local vendors, food booths, and live music.",
                        event_url="https://example.com/sunset-market",
                        contact_name=None,
                        contact_phone="928-555-0111",
                        tags=["market", "shopping", "community"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "rel-gym", "message": "sunset market"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["data"]["count"], 1)
        self.assertIn("Havasu Sunset Market", r.json()["response"])

    def test_word_boundary_prevents_night_matching_tonight(self) -> None:
        future_day = date.today() + timedelta(days=22)
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Tiki Party Tonight",
                        date=future_day,
                        start_time="20:00:00",
                        end_time=None,
                        location_name="Heat Hotel",
                        description="Special party tonight with drinks and island music.",
                        event_url="https://example.com/tiki-party",
                        contact_name=None,
                        contact_phone="928-555-0112",
                        tags=["nightlife", "adults"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "rel-gym", "message": "trivia night"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["count"], 0)
        self.assertIn("No trivia", r.json()["response"])

    def test_gymnastics_for_kids_no_soccer_honest_copy(self) -> None:
        sat = _sat()
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Saturday Soccer League",
                        date=sat,
                        start_time="09:00:00",
                        end_time=None,
                        location_name="Rotary Community Park, Lake Havasu City",
                        description="Youth soccer league games for ages 8–12 with volunteer refs and team jerseys.",
                        event_url="https://www.facebook.com/search/top?q=Rotary%20Community%20Park%20Lake%20Havasu",
                        contact_name=None,
                        contact_phone="928-555-0101",
                        tags=["sports", "soccer", "kids"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "rel-gym", "message": "gymnastics for an 8 year old girl this weekend"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()["response"]
        self.assertIn("No gymnastics", body)
        self.assertNotIn("Soccer", body)
        self.assertNotIn("soccer", body.lower())

    def test_yoga_weekend_honest_when_no_yoga_events(self) -> None:
        sat = _sat()
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Saturday Soccer League",
                        date=sat,
                        start_time="09:00:00",
                        end_time=None,
                        location_name="Rotary Community Park, Lake Havasu City",
                        description="Youth soccer league games for ages 8–12 with volunteer refs and team jerseys.",
                        event_url="https://www.facebook.com/search/top?q=Rotary%20Community%20Park%20Lake%20Havasu",
                        contact_name=None,
                        contact_phone="928-555-0102",
                        tags=["sports", "soccer"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "rel-yoga", "message": "yoga this weekend"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()["response"]
        self.assertIn("No yoga events coming up", body)
        self.assertIn("weekend events", body)

    def test_kids_activities_weekend_returns_matches_sorted(self) -> None:
        sat = _sat()
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Zebra Kids Art Hour",
                        date=sat,
                        start_time="14:00:00",
                        end_time=None,
                        location_name="Lake Havasu City Library",
                        description="Painting and crafts for children ages 6–10 with all supplies included.",
                        event_url="https://www.facebook.com/search/top?q=Lake%20Havasu%20City%20Library",
                        contact_name=None,
                        contact_phone="928-555-0103",
                        tags=["kids", "arts"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Morning Kids Soccer Kickabout",
                        date=sat,
                        start_time="09:00:00",
                        end_time=None,
                        location_name="Rotary Community Park, Lake Havasu City",
                        description="Casual soccer games for kids with parent volunteers and water breaks.",
                        event_url="https://www.facebook.com/search/top?q=Rotary%20Community%20Park%20Lake%20Havasu",
                        contact_name=None,
                        contact_phone="928-555-0104",
                        tags=["kids", "sports"],
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "rel-kids", "message": "kids activities this weekend"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()["response"]
        self.assertIn("Kids", body)
        self.assertIn("Soccer", body)
        self.assertIn("Art", body)

    def test_whats_on_weekend_grouped_listing(self) -> None:
        sat = _sat()
        with SessionLocal() as db:
            rows = [
                (
                    "Trail Walk for Beginners",
                    "Easy walk at Sara Park with a ranger talk about desert plants and wildlife.",
                    ["outdoors", "hiking"],
                ),
                (
                    "Community Jazz on the Lawn",
                    "Local jazz trio and food trucks near the channel; bring chairs or blankets.",
                    ["music", "community"],
                ),
                (
                    "Sunset Kayak Paddle",
                    "Guided evening paddle on the lake with life jackets and safety briefing for beginners.",
                    ["outdoors", "kayak"],
                ),
                (
                    "Open Mic Songwriters Night",
                    "Acoustic open stage for local musicians at the waterfront pavilion near London Bridge.",
                    ["music", "community"],
                ),
            ]
            for i, (title, desc, tags) in enumerate(rows):
                db.add(
                    Event.from_create(
                        EventCreate(
                            title=title,
                            date=sat,
                            start_time=time_type(17 + i, 0, 0),
                            end_time=None,
                            location_name="Sara Park, Lake Havasu City",
                            description=desc,
                            event_url="https://www.facebook.com/search/top?q=Sara%20Park%20Lake%20Havasu",
                            contact_name=None,
                            contact_phone=f"928-555-{(105 + i):04d}",
                            tags=tags,
                            embedding=None,
                            status="live",
                            created_by="user",
                            admin_review_by=None,
                        )
                    )
                )
            db.commit()

        r = self.__class__.client.post(
            "/chat",
            json={"session_id": "rel-list", "message": "what's on this weekend"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()["response"]
        self.assertIn("Here's what I found", body)
        self.assertTrue("Outdoors" in body or "Fun Activities" in body or "General" in body)

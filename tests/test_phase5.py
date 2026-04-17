from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.core.search import format_results, generate_query_embedding, search_events
from app.db.database import SessionLocal
from app.db.models import Event
from app.schemas.event import EventCreate


class Phase5EmbeddingSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(Event).delete()
            db.commit()

    def test_past_events_never_surface(self) -> None:
        today = date.today()
        past = today - timedelta(days=3)
        future = today + timedelta(days=3)

        emb = generate_query_embedding("community soccer")

        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Old Game",
                        date=past,
                        start_time="09:00:00",
                        end_time=None,
                        location_name="Field",
                        description="Past soccer match from the previous season.",
                        event_url="https://example.com/old-game",
                        contact_name=None,
                        contact_phone=None,
                        tags=[],
                        embedding=emb,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Upcoming Game",
                        date=future,
                        start_time="09:00:00",
                        end_time=None,
                        location_name="Field",
                        description="Soccer match this week.",
                        event_url="https://example.com/upcoming-game",
                        contact_name=None,
                        contact_phone=None,
                        tags=[],
                        embedding=emb,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        with SessionLocal() as db:
            results = search_events(
                db=db,
                date_context=None,
                activity_type=None,
                keywords=[],
                query_message="soccer",
            ).events

        titles = [e.title for e in results]
        self.assertIn("Upcoming Game", titles)
        self.assertNotIn("Old Game", titles)

    def test_embedding_ranking_orders_by_relevance(self) -> None:
        today = date.today()
        future = today + timedelta(days=5)
        emb_soccer = generate_query_embedding("youth soccer league fun")
        emb_opera = generate_query_embedding("classical opera symphony evening")

        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Soccer League",
                        date=future,
                        start_time="10:00:00",
                        end_time=None,
                        location_name="Park",
                        description="Youth soccer league games.",
                        event_url="https://example.com/soccer-league",
                        contact_name=None,
                        contact_phone=None,
                        tags=[],
                        embedding=emb_soccer,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Opera Night",
                        date=future,
                        start_time="19:00:00",
                        end_time=None,
                        location_name="Hall",
                        description="Classical opera performance.",
                        event_url="https://example.com/opera",
                        contact_name=None,
                        contact_phone=None,
                        tags=[],
                        embedding=emb_opera,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()

        with SessionLocal() as db:
            results = search_events(
                db=db,
                date_context=None,
                activity_type=None,
                keywords=[],
                query_message="kids soccer league",
            ).events

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0].title, "Soccer League")

    def test_format_results_includes_emoji_group_headers(self) -> None:
        today = date.today()
        future = today + timedelta(days=2)
        e1 = Event.from_create(
            EventCreate(
                title="Karate Kids",
                date=future,
                start_time="15:00:00",
                end_time=None,
                location_name="Dojo",
                description="Martial arts for beginners.",
                event_url="https://example.com/karate",
                contact_name=None,
                contact_phone=None,
                tags=[],
                embedding=None,
                status="live",
                created_by="user",
                admin_review_by=None,
            )
        )
        e2 = Event.from_create(
            EventCreate(
                title="Soccer Camp",
                date=future,
                start_time="09:00:00",
                end_time=None,
                location_name="Field",
                description="Sports camp for kids.",
                event_url="https://example.com/soccer-camp",
                contact_name=None,
                contact_phone=None,
                tags=[],
                embedding=None,
                status="live",
                created_by="user",
                admin_review_by=None,
            )
        )

        single = format_results([e1])
        self.assertIn("Found one that might work", single)
        self.assertIn("Karate Kids", single)
        self.assertIn("📅", single)
        self.assertIn("Dojo", single)

        text = format_results([e1, e2])
        self.assertIn("Here are your matches:", text)
        self.assertIn("1.", text)
        self.assertIn("2.", text)
        self.assertIn("Karate Kids", text)
        self.assertIn("Soccer Camp", text)


if __name__ == "__main__":
    unittest.main()

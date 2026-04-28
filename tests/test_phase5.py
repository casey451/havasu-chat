from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import patch

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

    def test_explicit_past_date_context_is_honored(self) -> None:
        today = date.today()
        in_window = today - timedelta(days=2)
        out_of_window = today + timedelta(days=5)
        emb = generate_query_embedding("farmers market")

        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Weekend Farmers Market",
                        date=in_window,
                        start_time="08:00:00",
                        end_time=None,
                        location_name="Downtown",
                        description="Fresh produce and vendors.",
                        event_url="https://example.com/market",
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
                        title="Future Concert",
                        date=out_of_window,
                        start_time="20:00:00",
                        end_time=None,
                        location_name="Amphitheater",
                        description="Live music event with local performers.",
                        event_url="https://example.com/concert",
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
                date_context={"start": in_window, "end": in_window},
                activity_type=None,
                keywords=[],
                query_message="farmers market",
            ).events

        titles = [e.title for e in results]
        self.assertIn("Weekend Farmers Market", titles)
        self.assertNotIn("Future Concert", titles)

    def test_date_context_includes_event_when_multi_day_spans_single_day_window(self) -> None:
        """Overlap: event May 5–10 is included when the filter window is only May 8."""
        token = "uniquemdspan123"
        emb = generate_query_embedding(f"{token} river")
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title=f"SpanTest {token}",
                        date=date(2026, 5, 5),
                        end_date=date(2026, 5, 10),
                        start_time="10:00:00",
                        end_time=None,
                        location_name="Waterfront",
                        description=f"Multi-day event {token} for search overlap.",
                        event_url="https://example.com/span-test",
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
                date_context={"start": date(2026, 5, 8), "end": date(2026, 5, 8)},
                activity_type=None,
                keywords=[],
                query_message=token,
            ).events

        self.assertTrue(any(token in (e.title + (e.description or "")) for e in results))

    def test_ongoing_multi_day_surfaces_without_date_context(self) -> None:
        """Started yesterday but ends tomorrow: still in the unscoped future candidate set."""
        t = date.today()
        token = "ongoingmdtoken"
        emb = generate_query_embedding(token)
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Multi Still On",
                        date=t - timedelta(days=1),
                        end_date=t + timedelta(days=1),
                        start_time="10:00:00",
                        end_time=None,
                        location_name="Lake",
                        description=f"Event {token} still running.",
                        event_url="https://example.com/ongoing-md",
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
                query_message=token,
            ).events

        self.assertTrue(any(e.title == "Multi Still On" for e in results))

    def test_embedding_ranking_orders_by_relevance(self) -> None:
        def _deterministic_embedding_source(text: str) -> tuple[list[float], bool]:
            from app.core.search import _deterministic_embedding_1536

            return (_deterministic_embedding_1536(text), False)

        with patch(
            "app.core.search.generate_query_embedding_with_source",
            side_effect=_deterministic_embedding_source,
        ):
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

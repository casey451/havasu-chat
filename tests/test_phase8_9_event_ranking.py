from __future__ import annotations

import unittest
from datetime import date, time, timedelta
from unittest.mock import patch

from app.core.event_recurrence import event_text_blob, is_recurring_heuristic
from app.core.search import (
    SearchOutcome,
    _apply_time_scoped_merged_sort,
    search_events,
    search_events_keyword_only,
)
from app.db.database import SessionLocal
from app.db.models import Event
from app.schemas.event import EventCreate


class Phase89RecurrenceHeuristicTests(unittest.TestCase):
    def test_every_saturday_in_text_is_recurring(self) -> None:
        blob = event_text_blob("Yoga in the Park every Saturday", "morning class", [])
        self.assertTrue(is_recurring_heuristic(blob))

    def test_one_time_festival_is_not_recurring(self) -> None:
        blob = event_text_blob(
            "Desert Storm Poker Run 2026",
            "one-day speedboat event on the lake; tickets online.",
            ["racing", "fundraiser"],
        )
        self.assertFalse(is_recurring_heuristic(blob))


class Phase89MergedSortTests(unittest.TestCase):
    def test_time_scoped_merged_prefers_one_time_at_equal_relevance(self) -> None:
        d = date(2026, 6, 15)
        t0 = time(9, 0)
        t1 = time(9, 0)

        class _Ev:
            __slots__ = ("is_recurring", "date", "start_time", "id")

            def __init__(self, is_r: bool, eid: str) -> None:
                self.is_recurring = is_r
                self.date = d
                self.start_time = t0 if eid == "a" else t1
                self.id = eid

        a = _Ev(True, "a")
        b = _Ev(False, "b")
        merged: list = [(a, 0.5), (b, 0.5)]
        _apply_time_scoped_merged_sort(merged, time_scoped=True)
        self.assertEqual([x[0].id for x in merged], ["b", "a"])

    def test_open_ended_merged_ignores_recurrence_uses_relevance(self) -> None:
        d = date(2026, 6, 15)

        class _Ev:
            __slots__ = ("is_recurring", "date", "start_time", "id")

            def __init__(self, is_r: bool, eid: str) -> None:
                self.is_recurring = is_r
                self.date = d
                self.start_time = time(9, 0)
                self.id = eid

        a = _Ev(True, "a")
        b = _Ev(False, "b")
        merged: list = [(a, 0.9), (b, 0.5)]
        _apply_time_scoped_merged_sort(merged, time_scoped=False)
        self.assertEqual([x[0].id for x in merged], ["a", "b"])


class Phase89SearchEventsIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(Event).delete()
            db.commit()

    def test_time_scoped_equal_embedding_one_time_first(self) -> None:
        with patch("app.core.search.cosine_similarity", return_value=0.5):
            def _det(src: str) -> tuple[list[float], bool]:
                from app.core.search import _deterministic_embedding_1536

                return _deterministic_embedding_1536(src), False

            with patch("app.core.search.generate_query_embedding_with_source", side_effect=_det):
                today = date.today()
                d = today + timedelta(days=5)
                ctx = {"start": today, "end": today + timedelta(days=14)}
                _emb = [0.1] * 1536

                with SessionLocal() as db:
                    for is_r, title in (
                        (True, "Farmers market weekly"),
                        (False, "One day craft fair"),
                    ):
                        db.add(
                            Event.from_create(
                                EventCreate(
                                    title=title,
                                    date=d,
                                    start_time="10:00:00",
                                    end_time=None,
                                    location_name="Field",
                                    description="x" * 25,
                                    event_url="https://example.com/x",
                                    contact_name=None,
                                    contact_phone=None,
                                    tags=[],
                                    is_recurring=is_r,
                                    embedding=_emb,
                                    status="live",
                                    created_by="user",
                                    admin_review_by=None,
                                )
                            )
                        )
                    db.commit()

                with SessionLocal() as db:
                    out = search_events(
                        db=db,
                        date_context=ctx,
                        activity_type=None,
                        keywords=[],
                        query_message="field events and community things",
                        strict_relevance=False,
                    )

                self.assertEqual(out.events[0].title, "One day craft fair")
                self.assertEqual(out.events[1].title, "Farmers market weekly")
                self.assertFalse(out.all_recurring)

    def test_all_recurring_flag_when_time_scoped_all_recurring(self) -> None:
        with patch("app.core.search.cosine_similarity", return_value=0.5):
            def _det(src: str) -> tuple[list[float], bool]:
                from app.core.search import _deterministic_embedding_1536

                return _deterministic_embedding_1536(src), False

            with patch("app.core.search.generate_query_embedding_with_source", side_effect=_det):
                today = date.today()
                d = today + timedelta(days=5)
                ctx = {"start": today, "end": today + timedelta(days=20)}

                with SessionLocal() as db:
                    for t in ("First Friday on Main", "Every Sunday market"):
                        db.add(
                            Event.from_create(
                                EventCreate(
                                    title=t,
                                    date=d,
                                    start_time="10:00:00",
                                    end_time=None,
                                    location_name="Downtown",
                                    description="y" * 25,
                                    event_url="https://example.com/y",
                                    contact_name=None,
                                    contact_phone=None,
                                    tags=[],
                                    is_recurring=True,
                                    embedding=[0.1] * 1536,
                                    status="live",
                                    created_by="user",
                                    admin_review_by=None,
                                )
                            )
                        )
                    db.commit()

                with SessionLocal() as db:
                    res = search_events(
                        db=db,
                        date_context=ctx,
                        activity_type=None,
                        keywords=[],
                        query_message="downtown and community",
                        strict_relevance=False,
                    )
                self.assertTrue(res.all_recurring)

    def test_all_recurring_not_set_without_time_scope(self) -> None:
        with patch("app.core.search.cosine_similarity", return_value=0.5):
            def _det(src: str) -> tuple[list[float], bool]:
                from app.core.search import _deterministic_embedding_1536

                return _deterministic_embedding_1536(src), False

            with patch("app.core.search.generate_query_embedding_with_source", side_effect=_det):
                today = date.today()
                d = today + timedelta(days=5)
                with SessionLocal() as db:
                    db.add(
                        Event.from_create(
                            EventCreate(
                                title="Every Sunday",
                                date=d,
                                start_time="10:00:00",
                                end_time=None,
                                location_name="Xyz",
                                description="z" * 25,
                                event_url="https://example.com/z",
                                contact_name=None,
                                contact_phone=None,
                                tags=[],
                                is_recurring=True,
                                embedding=[0.1] * 1536,
                                status="live",
                                created_by="user",
                                admin_review_by=None,
                            )
                        )
                    )
                    db.commit()
                with SessionLocal() as db:
                    res = search_events(
                        db=db,
                        date_context=None,
                        activity_type=None,
                        keywords=[],
                        query_message="sunday",
                        strict_relevance=False,
                    )
                self.assertFalse(res.all_recurring)


class Phase89SearchKeywordOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(Event).delete()
            db.commit()

    def test_keyword_only_time_scoped_one_time_first(self) -> None:
        today = date.today()
        d = today + timedelta(days=6)
        ctx = {"start": today, "end": today + timedelta(days=30)}
        with SessionLocal() as db:
            db.add(
                Event.from_create(
                    EventCreate(
                        title="Weekly market night",
                        date=d,
                        start_time="18:00:00",
                        end_time=None,
                        location_name="Downtown",
                        description="A night market, runs weekly like clockwork.",
                        event_url="https://example.com/m",
                        contact_name=None,
                        contact_phone=None,
                        tags=[],
                        is_recurring=True,
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
                        title="Charity dinner night",
                        date=d,
                        start_time="19:00:00",
                        end_time=None,
                        location_name="Downtown",
                        description="A special dinner night, one time only this season.",
                        event_url="https://example.com/d",
                        contact_name=None,
                        contact_phone=None,
                        tags=[],
                        is_recurring=False,
                        embedding=None,
                        status="live",
                        created_by="user",
                        admin_review_by=None,
                    )
                )
            )
            db.commit()
        with SessionLocal() as db:
            out = search_events_keyword_only(
                db,
                date_context=ctx,
                activity_type=None,
                keywords=["night"],
            )
        self.assertEqual([e.title for e in out], ["Charity dinner night", "Weekly market night"])


class Phase89SearchOutcomeDefaultTests(unittest.TestCase):
    def test_outcome_includes_all_recurring(self) -> None:
        o = SearchOutcome(
            events=[],
            suppressed_low_relevance=False,
            slot_filter_exhausted=False,
            honest_no_match=False,
        )
        self.assertFalse(o.all_recurring)

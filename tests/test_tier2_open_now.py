"""Tier 2 ``open_now`` filter (Phase 5.6)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.chat import tier2_db_query
from app.contrib.hours_helper import LAKE_HAVASU_TZ
from app.chat.tier2_handler import try_tier2_with_usage
from app.chat.tier2_schema import Tier2Filters
from app.db.database import SessionLocal
from app.db.models import Provider


def test_tier2filters_coerces_open_now_null() -> None:
    f = Tier2Filters.model_validate({"parser_confidence": 0.8, "open_now": None})
    assert f.open_now is False


def test_tier2filters_open_now_true_from_json() -> None:
    f = Tier2Filters.model_validate(
        {"parser_confidence": 0.82, "category": "restaurant", "open_now": True, "fallback_to_tier3": False}
    )
    assert f.open_now is True
    assert f.category == "restaurant"


def test_try_tier2_mocked_parser_open_now_calls_formatter_with_rows() -> None:
    f = Tier2Filters(parser_confidence=0.9, category="x", open_now=True, fallback_to_tier3=False)
    rows = [{"type": "provider", "name": "Only Open", "category": "x"}]
    with patch("app.chat.tier2_handler.tier2_parser.parse", return_value=(f, 2, 1)):
        with patch("app.chat.tier2_handler.tier2_db_query.query", return_value=rows) as q:
            with patch(
                "app.chat.tier2_handler.tier2_formatter.format",
                return_value=("formatted", 3, 1),
            ) as fmt:
                text, total, tin, tout = try_tier2_with_usage("dinner right now")
    q.assert_called_once()
    assert q.call_args[0][0].open_now is True
    fmt.assert_called_once()
    assert fmt.call_args[0][1] == rows
    assert text == "formatted"


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_open_now_filters_providers_by_structured_hours(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tier2_db_query,
        "_now_lake_havasu",
        lambda: datetime(2026, 6, 15, 12, 0, 0, tzinfo=LAKE_HAVASU_TZ),
    )
    suf = "t2on1"
    p_ok = Provider(
        provider_name=f"Diner Open {suf}",
        category="restaurant",
        verified=True,
        draft=False,
        is_active=True,
        source="tier2-open-test",
        description="food here",
        hours_structured={"monday": [{"open": "09:00", "close": "23:00"}]},
    )
    p_late = Provider(
        provider_name=f"Diner Closed {suf}",
        category="restaurant",
        verified=True,
        draft=False,
        is_active=True,
        source="tier2-open-test",
        description="food there",
        hours_structured={"monday": [{"open": "18:00", "close": "20:00"}]},
    )
    p_none = Provider(
        provider_name=f"Diner NoStruct {suf}",
        category="restaurant",
        verified=True,
        draft=False,
        is_active=True,
        source="tier2-open-test",
        description="food none",
    )
    db.add_all([p_ok, p_late, p_none])
    db.commit()

    from app.chat.tier2_db_query import query as tier2_query

    rows = tier2_query(
        Tier2Filters(parser_confidence=0.9, entity_name=f"Diner Open {suf}", open_now=True),
    )
    prov_names = [r["name"] for r in rows if r["type"] == "provider"]
    assert any(f"Diner Open {suf}" in n for n in prov_names)
    assert not any(f"Diner Closed {suf}" in n for n in prov_names)
    assert not any(f"Diner NoStruct {suf}" in n for n in prov_names)

    for p in (p_ok, p_late, p_none):
        db.delete(db.merge(p))
    db.commit()


def test_open_now_false_includes_providers_without_structured(db: Session) -> None:
    from app.chat.tier2_db_query import query as tier2_query

    suf = "t2on2"
    p = Provider(
        provider_name=f"NoStruct Browse {suf}",
        category="bakery",
        verified=True,
        draft=False,
        is_active=True,
        source="tier2-open-test",
        description="bread",
    )
    db.add(p)
    db.commit()
    rows = tier2_query(Tier2Filters(parser_confidence=0.9, category="bakery", open_now=False))
    assert any(r["type"] == "provider" and suf in r["name"] for r in rows)
    db.delete(db.merge(p))
    db.commit()

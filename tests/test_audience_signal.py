"""Tests for ``app.chat.audience_signal`` and its persistence wiring (Lane S3).

Covers:

* The composition rule in ``classify_audience`` for the three audience classes
  plus the ambiguous default.
* The header-driven geo-bucket stub (no GeoIP dependency).
* Time-of-day, day-of-week, and season bucket boundaries.
* The defensive ChatLog write — when the ``audience_signal`` column does not
  exist on the model yet (Lane S1's parallel migration), ``log_unified_route``
  skips silently and emits exactly one process-wide warning.
"""

from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.chat.audience_signal import (
    AudienceSignal,
    bucket_geo_from_headers,
    classify_audience,
    day_of_week_bucket,
    season_bucket,
    time_of_day_bucket,
)

_LH = ZoneInfo("America/Phoenix")


def _t(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Build a Lake-Havasu-local datetime fixture."""
    return datetime(2026, month, day, hour, minute, tzinfo=_LH)


# --- Composition tests -------------------------------------------------------


def test_classify_in_town_local_query() -> None:
    """86404 in-town zip + a clear local query → audience=local, confidence > 0.6."""
    headers = {"X-Zip": "86404"}
    # Tuesday afternoon in May — no spring_break / weekend bumps for visitor.
    sig = classify_audience(
        client_ip=None,
        accept_language=None,
        request_time_local=_t(5, 12, 14),  # Tue 2 PM
        query_text="find a plumber",
        headers=headers,
    )
    assert sig.audience == "local"
    assert sig.geo_bucket == "in_town"
    assert sig.confidence > 0.6


def test_classify_out_of_area_tourist_query() -> None:
    """Out-of-area IP + tourist query → audience=visitor, confidence > 0.6."""
    # Use a US country with a non-AZ/NV/CA region → out_of_area.
    headers = {"CF-IPCountry": "US", "CF-Region-Code": "TX"}
    sig = classify_audience(
        client_ip=None,
        accept_language=None,
        request_time_local=_t(7, 11, 11),  # Sat midday, summer + weekend
        query_text="boat rental this weekend",
        headers=headers,
    )
    assert sig.audience == "visitor"
    assert sig.geo_bucket == "out_of_area"
    assert sig.confidence > 0.6


def test_classify_ambiguous_returns_ambiguous() -> None:
    """No headers + a query without visitor/local keywords → ambiguous."""
    sig = classify_audience(
        client_ip=None,
        accept_language=None,
        # April 25 is shoulder, mid-week → no seasonal bumps.
        request_time_local=_t(4, 22, 13),  # Wed midday
        query_text="what's open",
        headers=None,
    )
    assert sig.audience == "ambiguous"
    assert sig.geo_bucket == "unknown"
    # Default ambiguous confidence is fixed at ~0.3.
    assert 0.25 <= sig.confidence <= 0.35


# --- Geo bucket -------------------------------------------------------------


def test_geo_bucket_unknown_when_no_headers() -> None:
    """No IP-related headers → geo_bucket == 'unknown'."""
    assert bucket_geo_from_headers(None) == "unknown"
    assert bucket_geo_from_headers({}) == "unknown"
    # Header present but unrelated to geo.
    assert bucket_geo_from_headers({"User-Agent": "curl/8"}) == "unknown"


# --- Time / season buckets --------------------------------------------------


def test_time_of_day_morning_at_8am() -> None:
    """08:00 LH local → 'morning'."""
    assert time_of_day_bucket(_t(5, 12, 8)) == "morning"
    # Boundary checks for safety: 5 AM is morning, 11 AM is midday.
    assert time_of_day_bucket(_t(5, 12, 5)) == "morning"
    assert time_of_day_bucket(_t(5, 12, 11)) == "midday"


def test_season_snowbird_in_january() -> None:
    """A January request → season == 'snowbird'."""
    # Jan 10 is well before mid-Feb so spring_break override doesn't apply.
    assert season_bucket(_t(1, 10, 12)) == "snowbird"
    # Sanity: late-Feb flips into spring_break.
    assert season_bucket(_t(2, 20, 12)) == "spring_break"


# --- Query-shape keyword scan -----------------------------------------------


def test_query_shape_visitor_words() -> None:
    """A query containing 'things to do' pushes the visitor score by +2.

    Configure the request so geo / season contribute zero — the only signal
    is the keyword scan. 'things to do' adds 2 to visitor; the 2-point margin
    is exactly enough to flip the outcome to 'visitor'.
    """
    sig = classify_audience(
        client_ip=None,
        accept_language=None,
        request_time_local=_t(4, 22, 13),  # shoulder, weekday
        query_text="things to do around here",
        headers=None,  # geo unknown → no geo bump
    )
    assert sig.audience == "visitor"


def test_query_shape_local_words() -> None:
    """A query containing 'tonight' pushes the local score by +2."""
    sig = classify_audience(
        client_ip=None,
        accept_language=None,
        request_time_local=_t(4, 22, 13),  # shoulder, weekday
        query_text="who's open tonight",
        headers=None,
    )
    assert sig.audience == "local"


# --- Defensive persistence --------------------------------------------------


def test_persistence_skips_silently_when_column_missing(caplog) -> None:
    """When ChatLog has no ``audience_signal`` attr, persistence skips and warns once.

    Mocks a ChatLog-shaped object that lacks the attribute, runs the
    persistence path twice, and asserts:
    1. No exception is raised.
    2. Exactly one WARN-level log line is emitted across both calls.
    """
    from app.db import chat_logging as cl

    # Reset the module-level once-flag so this test is order-independent.
    cl._audience_signal_warned_once = False

    class _Stub:
        """Mimics a ChatLog row but does NOT define ``audience_signal``."""

        def __init__(self, **kwargs: object) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.id = "stub-id"

        # Block hasattr(..., 'audience_signal') from probing __getattr__.
        def __getattr__(self, name: str) -> object:  # pragma: no cover
            raise AttributeError(name)

    class _DBStub:
        def add(self, *_a: object, **_k: object) -> None:  # noqa: D401
            pass

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

    sig = AudienceSignal(
        audience="visitor",
        geo_bucket="out_of_area",
        time_of_day="midday",
        day_of_week="weekend",
        season="summer",
        confidence=0.75,
    )

    # Patch ChatLog at the chat_logging module so the row is a _Stub.
    with patch.object(cl, "ChatLog", _Stub), caplog.at_level(logging.WARNING):
        # Call twice — only one warning should be emitted.
        rid1 = cl.log_unified_route(
            _DBStub(),  # type: ignore[arg-type]
            session_id="s",
            query_text_hashed="h",
            normalized_query="nq",
            mode="ask",
            sub_intent=None,
            entity_matched=None,
            tier_used="3",
            latency_ms=12,
            response_text="ok",
            audience_signal=sig,
        )
        rid2 = cl.log_unified_route(
            _DBStub(),  # type: ignore[arg-type]
            session_id="s",
            query_text_hashed="h",
            normalized_query="nq",
            mode="ask",
            sub_intent=None,
            entity_matched=None,
            tier_used="3",
            latency_ms=12,
            response_text="ok",
            audience_signal=sig,
        )

    # Both calls succeeded — no exception bubbled out.
    assert rid1 == "stub-id"
    assert rid2 == "stub-id"

    # Exactly one WARN-level audience_signal message across both calls.
    audience_warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "audience_signal" in r.getMessage()
    ]
    assert len(audience_warnings) == 1, audience_warnings

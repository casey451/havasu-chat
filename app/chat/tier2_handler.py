"""Tier 2 orchestrator: parser → DB → formatter (Phase 4.2). Wired from router in Phase 4.3."""

from __future__ import annotations

import logging
import re
import time
from datetime import date
from typing import Any, Optional

from app.chat import (
    tier2_business_shortcut,
    tier2_cache,
    tier2_day_agenda,
    tier2_db_query,
    tier2_formatter,
    tier2_parser,
)
from app.chat.chat_request_context import ChatRequestContext
from app.chat.tier2_db_query import _event_dict
from app.chat.tier2_schema import Tier2Filters
from app.core.timezone import now_lake_havasu
from app.db.database import SessionLocal
from app.events.queries import events_in_window, intent_window_for_when

# Parser scores below this threshold skip Tier 2 and defer to Tier 3 (tunable in a later phase).
TIER2_CONFIDENCE_THRESHOLD = 0.7

# Phase 7.7 — honest empty listing for open_now zero-rows.
# Fires when the user asked for currently-open <category> AND the catalog has rows
# matching the category BUT zero rows survive the open_now filter (typically because
# hours_structured / google_hours data is missing). Deterministic, zero LLM tokens.
_OPEN_NOW_EMPTY_LISTING_TEMPLATE = (
    "I have {category_label} in the Lake Havasu catalog, but I don't have "
    "current hours data for them yet — so I can't tell you which are open "
    "right now. Try https://www.golakehavasu.com/ for a hours-aware listing, "
    "or share a Google Business page at /contribute and I'll fill the gap."
)


def _open_now_empty_listing(category: str) -> str:
    """Render the honest empty listing for a single ``category`` (e.g. "restaurant").

    Pluralizes via :func:`tier2_business_shortcut._pluralize_for_header` so the
    label reads naturally for one-word ("restaurants") and two-word ("coffee
    shops") categories alike.
    """
    label = tier2_business_shortcut._pluralize_for_header(category or "places")
    return _OPEN_NOW_EMPTY_LISTING_TEMPLATE.format(category_label=label)


_MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_MONTH_DAY_RE = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?\s*"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(20\d{2}))?\b",
    re.IGNORECASE,
)


def _explicit_month_day(query: str) -> date | None:
    m = _MONTH_DAY_RE.search(query or "")
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    day = int(m.group(2))
    today = now_lake_havasu().date()
    year = int(m.group(3)) if m.group(3) else today.year
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    if m.group(3) is None and d < today:
        try:
            d = date(year + 1, month, day)
        except ValueError:
            return None
    return d


def detect_event_intent(query: str) -> dict[str, str] | None:
    """Return ``{'when': ...}`` when the query is event-flavored."""
    q = (query or "").lower()
    if "this weekend" in q or "saturday" in q or "sunday" in q:
        return {"when": "this_weekend"}
    if any(
        k in q
        for k in (
            "tonight",
            "what's on",
            "whats on",
            "what is on",
            "what's happening",
            "whats happening",
            " events",
            " event ",
        )
    ):
        return {"when": "tonight" if "tonight" in q else "today"}
    return None


def _event_rows_for_intent(when: str) -> list[dict[str, Any]]:
    today = now_lake_havasu().date()
    win_start, win_end = intent_window_for_when(when, today=today)
    with SessionLocal() as db:
        flat = events_in_window(
            db, window_start=win_start, window_end=win_end, limit=8
        )
    rows: list[dict[str, Any]] = []
    for event, occ_date in flat:
        row = _event_dict(event)
        row["date"] = occ_date.isoformat()
        rows.append(row)
    return rows


def _normalize_tier2_filters_from_query(query: str, filters: Tier2Filters) -> Tier2Filters:
    """Correct common LLM-router date/category drift with deterministic query facts."""
    q = query or ""
    low = q.lower()
    updates: dict[str, object] = {}

    if explicit := _explicit_month_day(q):
        updates.update(
            {
                "date_exact": explicit,
                "date_start": None,
                "date_end": None,
                "time_window": None,
                "month_name": None,
                "season": None,
                "day_of_week": None,
            }
        )
    elif "this weekend" in low:
        updates.update(
            {
                "time_window": "this_weekend",
                "date_exact": None,
                "date_start": None,
                "date_end": None,
                "month_name": None,
                "season": None,
                "day_of_week": None,
            }
        )
    elif "this week" in low:
        updates.update(
            {
                "time_window": "this_week",
                "date_exact": None,
                "date_start": None,
                "date_end": None,
                "month_name": None,
                "season": None,
                "day_of_week": None,
            }
        )

    if re.search(r"\bart(?:s| class| classes| workshop| workshops)?\b", low):
        updates["category"] = "arts"

    if not updates:
        return filters
    return filters.model_copy(update=updates)


def try_tier2_with_usage(
    query: str,
    *,
    component_meta: Optional[dict[str, Any]] = None,
    chat_ctx: ChatRequestContext | None = None,
    telemetry: dict | None = None,
) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    """Return (response_text, llm_tokens_used, llm_input_tokens, llm_output_tokens).

    On full success, ``llm_tokens_used`` is parser+formatter totals; on fallback ``text`` is
    ``None`` and token fields are ``None``.

    Slice D: business-listing shapes ("find me a barber in LHC") take a zero-token
    fast path — regex-extracted filters + deterministic listing render. Falls through
    to the LLM parser path when the shortcut returns None or finds no providers.

    BUILD.md task #12: when ``component_meta`` is provided and the query
    asks "what's on <day>" with multiple events, populates it with
    ``{"type": "day_agenda", "data": {...}}`` and returns a short voice
    line as ``response_text``. The structured listing renders front-end
    side. Without ``component_meta`` (or for non-day-shape queries) the
    long-prose formatter path runs unchanged.
    """
    q = (query or "").strip()
    if not q:
        logging.info("tier2_handler: fallback: empty query")
        return None, None, None, None

    event_intent = detect_event_intent(q)
    if event_intent is not None:
        from app.chat import tier2_catalog_render

        rows = _event_rows_for_intent(event_intent["when"])
        if rows:
            logging.info("tier2_handler: event-intent path when=%s", event_intent["when"])
            text = tier2_catalog_render.render_tier2_events(q, rows)
            if telemetry is not None:
                telemetry["cache_status"] = "bypass"
            return text, 0, 0, 0
        logging.info("tier2_handler: event-intent matched but zero rows; fall through")

    shortcut_filters = tier2_business_shortcut.try_business_listing_shortcut(q)
    if shortcut_filters is not None:
        t_db_start = time.perf_counter()
        rows = tier2_db_query.query(shortcut_filters, ctx=chat_ctx)
        if telemetry is not None:
            telemetry["tier2_db_ms"] = int((time.perf_counter() - t_db_start) * 1000)
        listing = tier2_business_shortcut.render_business_listing_with_component(
            rows,
            shortcut_filters.category or "",
            intent_query=q,
        )
        if listing is not None:
            text, comp_data = listing
            if component_meta is not None:
                component_meta["type"] = "business_list"
                component_meta["data"] = comp_data
            logging.info("tier2_handler: business-listing shortcut hit (zero tokens)")
            if telemetry is not None:
                telemetry["cache_status"] = "bypass"
            return text, 0, 0, 0
        # Phase 7.7 — honest empty listing. The shortcut matched the user-intent
        # shape, the catalog has rows matching the category, but the open_now
        # filter dropped them all (no hours_structured / google_hours). Emit a
        # deterministic tier-2 reply instead of falling through to the LLM.
        if shortcut_filters.open_now and shortcut_filters.category:
            logging.info(
                "tier2_handler: open_now zero-rows; emitting honest empty listing (shortcut path)"
            )
            if telemetry is not None:
                telemetry["cache_status"] = "bypass"
            return _open_now_empty_listing(shortcut_filters.category), 0, 0, 0
        # Shortcut matched the shape but returned no provider rows — fall through to the
        # LLM path so the user still gets a useful answer.
        logging.info("tier2_handler: shortcut shape matched but no provider rows; falling through")

    today_iso = now_lake_havasu().strftime("%Y-%m-%d")
    parser_cache_hit = False
    t_parser_start = time.perf_counter()
    with SessionLocal() as db:
        cached_filters = tier2_cache.lookup_parser(db, q, today_iso)
        if cached_filters is not None:
            filters, p_in, p_out = cached_filters, 0, 0
            parser_cache_hit = True
        else:
            filters, p_in, p_out = tier2_parser.parse(q)
            if filters is not None:
                tier2_cache.store_parser(db, q, today_iso, filters)
            parser_cache_hit = False
    parser_ms = int((time.perf_counter() - t_parser_start) * 1000)
    if telemetry is not None:
        telemetry["tier2_parser_ms"] = parser_ms
        telemetry["tier2_parser_cache"] = "hit_exact" if parser_cache_hit else "miss"
    if filters is None:
        logging.info("tier2_handler: fallback: parser error")
        return None, None, None, None
    if filters.fallback_to_tier3:
        logging.info("tier2_handler: fallback: parser refused")
        return None, None, None, None
    if filters.parser_confidence < TIER2_CONFIDENCE_THRESHOLD:
        logging.info("tier2_handler: fallback: low confidence")
        return None, None, None, None

    filters = _normalize_tier2_filters_from_query(q, filters)
    t_db_start = time.perf_counter()
    rows = tier2_db_query.query(filters, ctx=chat_ctx)
    db_ms = int((time.perf_counter() - t_db_start) * 1000)
    if telemetry is not None:
        telemetry["tier2_db_ms"] = db_ms
    if len(rows) == 0:
        # Phase 7.7 — same honest empty listing also applies to parser-built
        # filters with the q03 shape (open_now + explicit category). The LLM
        # parser sometimes sets open_now=True with category=None for shapes
        # like "anywhere open right now"; those continue to fall through to
        # tier-3 as today.
        if filters.open_now and filters.category:
            logging.info(
                "tier2_handler: parser-path open_now zero-rows; emitting honest empty listing"
            )
            pi, po = (p_in or 0), (p_out or 0)
            if telemetry is not None:
                telemetry["cache_status"] = "bypass"
            return _open_now_empty_listing(filters.category), pi + po, pi, po
        logging.info("tier2_handler: fallback: no matches")
        return None, None, None, None

    # BUILD.md task #12: day-shape branch. When the query asks "what's
    # happening on <day>" with multiple events, skip the long-prose
    # formatter and emit a structured day_agenda component + a short
    # voice line via component_meta. Existing behavior is unchanged for
    # all other shapes.
    if component_meta is not None:
        agenda = tier2_day_agenda.try_build_day_agenda(q, filters, rows)
        if agenda is not None:
            voice, comp_data, v_in, v_out = agenda
            component_meta["type"] = "day_agenda"
            component_meta["data"] = comp_data
            pi, po = (p_in or 0), (p_out or 0)
            in_sum = pi + (v_in or 0)
            out_sum = po + (v_out or 0)
            total = in_sum + out_sum
            if telemetry is not None:
                telemetry["cache_status"] = "bypass"
            return voice, total, in_sum, out_sum

    fmt_cache_hit = False
    t_fmt_start = time.perf_counter()
    with SessionLocal() as db:
        cached_raw = tier2_cache.lookup_formatter(db, q, rows)
        if cached_raw is not None:
            # Backlog #49: cache stores raw LLM text. Re-run post-processors
            # on every hit so confidence-tier flag flips and edits to
            # ``_inject_event_url_links`` / ``_enforce_low_tier_phone`` take
            # effect immediately instead of waiting for the 1-day TTL.
            text, f_in, f_out = tier2_formatter.postprocess(cached_raw, rows), 0, 0
            fmt_cache_hit = True
        else:
            raw_text, f_in, f_out = tier2_formatter.format(q, rows)
            # Store the *raw* LLM output so post-processors can re-run on
            # cache hits (see Backlog #49 / tier3_handler.py:332-334).
            if raw_text:
                tier2_cache.store_formatter(db, q, rows, raw_text)
            text = tier2_formatter.postprocess(raw_text, rows)
            fmt_cache_hit = False
    fmt_ms = int((time.perf_counter() - t_fmt_start) * 1000)
    if telemetry is not None:
        telemetry["tier2_fmt_ms"] = fmt_ms
        telemetry["tier2_fmt_cache"] = "hit_exact" if fmt_cache_hit else "miss"
        if parser_cache_hit and fmt_cache_hit:
            telemetry["cache_status"] = "hit_exact"
        else:
            telemetry["cache_status"] = "miss"
    if text is None:
        logging.info("tier2_handler: fallback: formatter error")
        return None, None, None, None

    pi, po = (p_in or 0), (p_out or 0)
    fi, fo = (f_in or 0), (f_out or 0)
    in_sum = pi + fi
    out_sum = po + fo
    total = in_sum + out_sum
    return text, total, in_sum, out_sum


def answer_with_tier2(query: str) -> Optional[str]:
    """Chain parser → DB query → formatter. Returns None to signal 'fall back to Tier 3'."""
    text, _, _, _ = try_tier2_with_usage(query)
    return text


def try_tier2_with_filters_with_usage(
    query: str,
    filters: Tier2Filters,
    *,
    component_meta: Optional[dict[str, Any]] = None,
    chat_ctx: ChatRequestContext | None = None,
    telemetry: dict | None = None,
) -> tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    """Run Tier 2 using precomputed filters (skip parser).

    Returns the same tuple shape as :func:`try_tier2_with_usage`. Honors
    the same ``component_meta`` hook (BUILD.md task #12) — when provided
    and the query is day-shape, emits day_agenda + short voice instead
    of the long-prose formatter.
    """
    q = (query or "").strip()
    if not q:
        logging.info("tier2_handler: fallback: empty query")
        return None, None, None, None
    if filters.fallback_to_tier3:
        logging.info("tier2_handler: fallback: router filters marked fallback_to_tier3")
        return None, None, None, None
    if filters.parser_confidence < TIER2_CONFIDENCE_THRESHOLD:
        logging.info("tier2_handler: fallback: router filters low confidence")
        return None, None, None, None

    filters = _normalize_tier2_filters_from_query(q, filters)
    t_db_start = time.perf_counter()
    rows = tier2_db_query.query(filters, ctx=chat_ctx)
    if telemetry is not None:
        telemetry["tier2_db_ms"] = int((time.perf_counter() - t_db_start) * 1000)
    if len(rows) == 0:
        logging.info("tier2_handler: fallback: no matches")
        return None, None, None, None

    if component_meta is not None:
        agenda = tier2_day_agenda.try_build_day_agenda(q, filters, rows)
        if agenda is not None:
            voice, comp_data, v_in, v_out = agenda
            component_meta["type"] = "day_agenda"
            component_meta["data"] = comp_data
            in_sum = v_in or 0
            out_sum = v_out or 0
            total = in_sum + out_sum
            if telemetry is not None:
                telemetry["cache_status"] = "bypass"
            return voice, total, in_sum, out_sum

    fmt_cache_hit = False
    t_fmt_start = time.perf_counter()
    with SessionLocal() as db:
        cached_raw = tier2_cache.lookup_formatter(db, q, rows)
        if cached_raw is not None:
            # Backlog #49: cache stores raw LLM text -- post-process on hit so
            # confidence-tier flag flips apply without waiting for TTL.
            text, f_in, f_out = tier2_formatter.postprocess(cached_raw, rows), 0, 0
            fmt_cache_hit = True
        else:
            raw_text, f_in, f_out = tier2_formatter.format(q, rows)
            # Store the *raw* LLM output (see Backlog #49 / tier3_handler.py).
            if raw_text:
                tier2_cache.store_formatter(db, q, rows, raw_text)
            text = tier2_formatter.postprocess(raw_text, rows)
            fmt_cache_hit = False
    if telemetry is not None:
        telemetry["tier2_fmt_ms"] = int((time.perf_counter() - t_fmt_start) * 1000)
        telemetry["tier2_fmt_cache"] = "hit_exact" if fmt_cache_hit else "miss"
        telemetry["cache_status"] = "hit_exact" if fmt_cache_hit else "miss"
    if text is None:
        logging.info("tier2_handler: fallback: formatter error")
        return None, None, None, None

    in_sum = f_in or 0
    out_sum = f_out or 0
    total = in_sum + out_sum
    return text, total, in_sum, out_sum

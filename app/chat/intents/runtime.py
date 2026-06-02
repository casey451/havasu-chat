"""Intent-layer runtime entry point (Ask Hava intent catalog, Phase 1).

``try_intent_layer(query, db)`` is the single function the router calls. It:

1. Returns ``None`` immediately when the ``USE_INTENT_LAYER`` flag is off (the
   production default) -- so the router is byte-identical until enabled.
2. Resolves the intent (L0-L2). ``None`` -> fall through to Tier 2 / Tier 3.
3. Runs the grounded query template.
4. Renders a Hava-voice line + a real card component (``business_list`` for
   providers, ``day_agenda`` / ``week_strip`` for events), or an honest "not in
   the catalog yet" + /contribute nudge on an empty result -- never fabricates.
5. Logs the normalized intent key + category + result_count to ``query_log``
   (master spec §9), including zero-row results (the coverage signal).

Everything is best-effort: any failure returns ``None`` so the request falls
through to the existing path rather than 500-ing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.chat.intents.queries import QueryResult, run_query
from app.chat.intents.resolver import resolve

logger = logging.getLogger(__name__)

_FLAG_ENV = "USE_INTENT_LAYER"
_MAX_LISTED = 6
_CONTRIBUTE_TAIL = (
    "Add it at /contribute or share the name and a link "
    "(Google Business page or official site) and I'll pass it along."
)


@dataclass
class IntentAnswer:
    text: str
    intent_key: str
    category: str | None
    result_count: int
    component_type: str = "none"
    component_data: dict = field(default_factory=dict)


def is_enabled() -> bool:
    return (os.environ.get(_FLAG_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def _empty_text(result: QueryResult) -> str:
    noun = {
        "events": "events on the calendar for that yet",
        "programs": "classes listed for that yet",
        "gas": "live gas prices right now",
    }.get(result.kind, "anything listed for that yet")
    return f"I don't have {noun}. {_CONTRIBUTE_TAIL}"


def _text_list(result: QueryResult) -> str:
    """Voice-only bulleted list for kinds without a card component (gas/programs)."""
    lines = [result.lead_in] if result.lead_in else []
    for row in result.rows[:_MAX_LISTED]:
        line = f"- {row.get('name', '')}"
        if row.get("subtitle"):
            line += f" -- {row['subtitle']}"
        if row.get("detail"):
            line += f" ({row['detail']})"
        lines.append(line)
    extra = result.result_count - _MAX_LISTED
    if extra > 0:
        lines.append(f"...and {extra} more.")
    return "\n".join(lines)


def _build_providers(result: QueryResult) -> tuple[str, str, dict]:
    from app.chat.component_builders import build_business_list

    data = build_business_list(
        result.rows,
        category=result.label or "businesses",
        total_count=result.result_count,
    )
    voice = result.lead_in.rstrip(":") + "." if result.lead_in else "Here are a few picks."
    return voice, "business_list", data


def _build_events(result: QueryResult, *, today: date) -> tuple[str, str, dict]:
    from app.chat import component_builders as cb
    from app.chat.intents.queries import _event_window_dates
    from app.chat.tier2_schema import Tier2Filters

    window = result.window or "upcoming"
    start, end = _event_window_dates(window, today)
    filters = Tier2Filters(parser_confidence=1.0, date_start=start, date_end=end)
    if start == end:
        data = cb.build_day_agenda(filters, result.rows)
        voice = cb.fallback_day_agenda_voice(result.rows, start)
        return voice, "day_agenda", data
    data = cb.build_week_strip(filters, result.rows)
    voice = cb.fallback_week_strip_voice(result.rows, (start, end))
    return voice, "week_strip", data


def _render(result: QueryResult, *, today: date) -> tuple[str, str, dict]:
    """Return (voice_text, component_type, component_data)."""
    if result.result_count == 0:
        return _empty_text(result), "none", {}
    if result.kind == "providers":
        return _build_providers(result)
    if result.kind == "events":
        return _build_events(result, today=today)
    # gas / programs -> voice-only list
    return _text_list(result), "none", {}


def _log(db: Session, result: QueryResult) -> None:
    # log_query_intent derives result_count from the component payload; pass the
    # rows under "businesses" so the logged count == result.result_count for
    # every kind (the component_type arg is used only for that count, not stored).
    try:
        from app.v1.query_log import log_query_intent

        log_query_intent(
            db,
            normalized_intent=result.intent_key,
            sub_intent=None,
            mode="ask",
            category_hint=result.category_hint,
            component_type="business_list",
            component_data={"businesses": result.rows},
        )
    except Exception:
        logger.exception("intent_layer: query_log write failed")


def try_intent_layer(
    query: str,
    db: Session,
    *,
    today: date | None = None,
    now: datetime | None = None,
) -> IntentAnswer | None:
    """Resolve + answer at the intent layer, or None to fall through."""
    if not is_enabled():
        return None
    try:
        resolved = resolve(query)
    except Exception:
        logger.exception("intent_layer: resolve failed")
        return None
    if resolved is None:
        return None

    try:
        result = run_query(resolved, db, today=today, now=now)
    except Exception:
        logger.exception("intent_layer: query template failed for %s", resolved.intent_key)
        return None

    if today is None:
        from app.core.timezone import now_lake_havasu

        today = now_lake_havasu().date()

    try:
        text, component_type, component_data = _render(result, today=today)
    except Exception:
        logger.exception("intent_layer: render failed for %s", result.intent_key)
        return None

    _log(db, result)
    return IntentAnswer(
        text=text,
        intent_key=result.intent_key,
        category=result.category_hint,
        result_count=result.result_count,
        component_type=component_type,
        component_data=component_data,
    )

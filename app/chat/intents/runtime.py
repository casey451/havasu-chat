"""Intent-layer runtime entry point (Ask Hava intent catalog, Phase 1).

``try_intent_layer(query, db)`` is the single function the router calls. It:

1. Returns ``None`` immediately when the ``USE_INTENT_LAYER`` flag is off. The
   flag is default-ON (see ``is_enabled``); it is a kill switch -- set it to
   "0"/"false"/"no"/"off" to make the router byte-identical to the pre-intent
   path.
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
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.chat.intents.queries import QueryResult, run_query
from app.chat.intents.resolver import ResolvedIntent, category_vocabulary, resolve

logger = logging.getLogger(__name__)

_FLAG_ENV = "USE_INTENT_LAYER"
_MAX_LISTED = 6

# Entity-specific factual lookups ("rating for X", "phone for X", "when is X").
# These are about ONE named thing -> the entity-aware Tier 1 / gap-template path
# owns them (incl. the anti-fabrication / near-match guards). The intent layer
# must not answer them with a generic category list.
_ENTITY_FACTUAL_SUBINTENTS = frozenset(
    {
        "PHONE_LOOKUP",
        "WEBSITE_LOOKUP",
        "RATING_LOOKUP",
        "REVIEW_COUNT_LOOKUP",
        "TIME_LOOKUP",
        "HOURS_LOOKUP",
        "LOCATION_LOOKUP",
        "DATE_LOOKUP",
        "AGE_LOOKUP",
        "COST_LOOKUP",
        "NEXT_OCCURRENCE",
    }
)


_SPURIOUS_FILLER_TOKENS: frozenset[str] = frozenset(
    """a an and any are around at best can cheap cheapest close closed could do
    does find for from get good great hava have help hey hi how i im in is it
    late me my near nearby need new now of ok okay on open or our please right
    should some something that the there this to today tonight tomorrow top
    town up us we week weekend what when where which who whose why with would
    you your""".split()
)
# Age/time phrasing tokens are generic too ("what activities can my 8 year old
# do after school hours" must not read "year"/"old"/"8" as distinctive).
_SPURIOUS_FILLER_TOKENS = _SPURIOUS_FILLER_TOKENS | frozenset(
    "year years yr yrs old olds month months day days hour hours time times".split()
)
_SPURIOUS_LOCALITY_TOKENS: frozenset[str] = frozenset(
    {"lake", "havasu", "city", "arizona", "az", "lhc"}
)


# Schedule-shaped words: with a matched venue these make the turn a
# venue-schedule browse ("what classes does the aquatic center offer and
# when"), which the per-venue grounded query answers at 0 tokens. Factual
# single-fact lookups (hours/phone/address) deliberately stay OUT of this set
# -- Tier 1 owns them and runs first.
_VENUE_SCHEDULE_RE = re.compile(
    r"\b(class|classes|program|programs|lesson|lessons|schedule|schedules|"
    r"offer|offers|offering|offerings|camp|camps|activities|activity|"
    r"happening|events|event|going on|sign up|register)\b"
)


def _wants_venue_schedule(query: str) -> bool:
    from app.chat.normalizer import normalize

    return bool(_VENUE_SCHEDULE_RE.search(normalize(query or "")))


def _entity_match_spurious(query: str) -> bool:
    """True when every query token is generic (category vocab/locality/filler).

    The entity matcher deliberately matches trade-superlative queries to a
    same-trade provider (backlog #52: "what is the best plumber in lake
    havasu" -> "All Seasons Plumbing"). For the intent layer that match must
    not block a category listing: when nothing in the query is distinctive,
    nothing ties the turn to the matched name, and the listing (which contains
    that provider) is the better zero-token answer.

    Conservative by design: ANY distinctive token — whether it ties to the
    matched entity ("mudshark") or to something else entirely — keeps the
    entity guard in place and falls through to the entity-aware path.
    """
    from app.chat.normalizer import normalize

    vocab = category_vocabulary()
    for tok in re.split(r"[^a-z0-9]+", normalize(query or "")):
        if not tok or tok in _SPURIOUS_FILLER_TOKENS or tok in _SPURIOUS_LOCALITY_TOKENS:
            continue
        if tok.isdigit():
            continue  # bare numbers are ages/times/counts, never business names
        if tok in vocab or (tok.endswith("s") and tok[:-1] in vocab) or (tok + "s") in vocab:
            continue
        # Distinctive token: the turn is about something specific — the
        # entity-aware path owns it.
        return False
    return True


@dataclass
class IntentAnswer:
    text: str
    intent_key: str
    category: str | None
    result_count: int
    component_type: str = "none"
    component_data: dict = field(default_factory=dict)


def is_enabled() -> bool:
    # Default ON; explicit "0"/"false"/"no"/"off" is the kill switch.
    return (os.environ.get(_FLAG_ENV) or "").strip().lower() not in ("0", "false", "no", "off")


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
    """Return (voice_text, component_type, component_data). Non-empty only."""
    if result.kind == "providers":
        return _build_providers(result)
    if result.kind == "events":
        return _build_events(result, today=today)
    # gas / programs -> voice-only list
    return _text_list(result), "none", {}


def _log(db: Session, result: QueryResult, *, min_layer: str | None = None) -> None:
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
            min_layer=min_layer,
        )
    except Exception:
        logger.exception("intent_layer: query_log write failed")


def is_entity_about_query_safe(query: str) -> bool:
    """About-shape probe that never raises (venue-schedule branch guard)."""
    try:
        from app.chat.entity_matcher import is_entity_about_query

        return is_entity_about_query(query)
    except Exception:
        logger.exception("intent_layer: about-shape probe failed")
        return True  # fail closed -- about-shaped turns belong to the entity path


def try_intent_layer(
    query: str,
    db: Session,
    *,
    entity: str | None = None,
    sub_intent: str | None = None,
    telemetry: dict | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> IntentAnswer | None:
    """Resolve + answer at the intent layer, or None to fall through.

    Falls through (returns None) when:
    * the flag is off;
    * ``entity`` is set -- the turn is about a specific named business/event
      ("tell me about Mudshark Brewery"); the entity-aware path owns it;
    * ``sub_intent`` is an entity-specific factual lookup ("rating for X") --
      the Tier 1 / gap-template path (with its anti-fabrication guards) owns it;
    * the resolver finds no confident intent;
    * the query template returns zero rows -- the legacy path's honest gap
      template + /contribute handles empties. We still log the zero-row to
      query_log first (the coverage signal) before falling through.

    The layer therefore only *claims* a query when it has real catalog results.
    """
    if not is_enabled():
        return None
    if entity and entity.strip():
        # 2026-06-06: bypass the guard when the match is explained entirely by
        # generic category/locality tokens (see _entity_match_spurious). The
        # factual-subintent and about-shape guards below still apply.
        try:
            spurious = _entity_match_spurious(query)
        except Exception:
            logger.exception("intent_layer: spurious-entity probe failed")
            spurious = False
        # Venue-schedule browse runs FIRST -- even when the entity match looks
        # "spurious" (a venue literally named with category words: "Lake Havasu
        # City Parks & Recreation"), schedule words + a matched venue mean the
        # per-venue grounded query is the right answer, not a generic listing.
        # Live regression 2026-06-07: "what classes does parks and recreation
        # offer" bypassed via spurious -> resolve() -> parks_trails listing.
        if _wants_venue_schedule(query) and not is_entity_about_query_safe(query):
            resolved_venue = ResolvedIntent("venue_schedule", {"venue": entity.strip()}, "L2")
            result = None
            try:
                result = run_query(resolved_venue, db, today=today, now=now)
            except Exception:
                logger.exception("intent_layer: venue_schedule query failed")
            if result is not None:
                _log(db, result, min_layer="L2")
                if telemetry is not None:
                    telemetry["intent_logged"] = True
                if result.result_count > 0:
                    if today is None:
                        from app.core.timezone import now_lake_havasu

                        today = now_lake_havasu().date()
                    try:
                        text, component_type, component_data = _render(result, today=today)
                    except Exception:
                        logger.exception("intent_layer: venue_schedule render failed")
                        return None
                    return IntentAnswer(
                        text=text,
                        intent_key=result.intent_key,
                        category=result.category_hint,
                        result_count=result.result_count,
                        component_type=component_type,
                        component_data=component_data,
                    )
            # Zero rows / failure: fall through to the spurious decision below
            # ("8 year old activities" with a spurious school match must still
            # reach kids_lessons; a genuine venue with no schedule data goes to
            # the entity-aware path).
        if not spurious:
            return None
    if sub_intent and sub_intent in _ENTITY_FACTUAL_SUBINTENTS:
        # 2026-06-04: the factual-subintent guard protects single-ENTITY lookups
        # ("where is mudshark"), but the classifier also labels recommendation
        # shapes LOCATION_LOOKUP ("where should we stay") -- those have no entity
        # and a category listing is the right zero-token answer. Only hold the
        # guard when the turn isn't recommendation-shaped.
        try:
            from app.chat.unified_router import _RECOMMENDATION_SHAPED

            if not _RECOMMENDATION_SHAPED.match(query or ""):
                return None
        except Exception:
            logger.exception("intent_layer: recommendation-shape probe failed")
            return None
    # 2026-06-04: about-shaped turns ("tell me about X", "who is X", "info on X")
    # are about ONE named thing. When the entity matcher resolved the name, the
    # entity guard above already fired; when it did NOT (unknown or fuzzy-missed
    # entity), claiming the turn as a category listing answers a different
    # question -- prod served "Here's what's good to eat." for "tell me about
    # Mudshark Brewery" via the cuisine token "brewery". Fall through so the
    # entity-aware path (Tier 1 / near-match / gap template) owns it.
    try:
        from app.chat.entity_matcher import is_entity_about_query

        if is_entity_about_query(query):
            return None
    except Exception:
        logger.exception("intent_layer: about-shape guard failed")
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

    # Log the resolved intent + result_count (incl. zero) for coverage, then
    # fall through on empty so the legacy honest-gap path answers. Signal that
    # we wrote the row so the HTTP layer's logger skips (one query_log row per
    # turn). The flag is set whether we claim or fall through on empty -- both
    # write a precise row here.
    _log(db, result, min_layer=resolved.layer)
    if telemetry is not None:
        telemetry["intent_logged"] = True
    if result.result_count == 0:
        return None

    if today is None:
        from app.core.timezone import now_lake_havasu

        today = now_lake_havasu().date()

    try:
        text, component_type, component_data = _render(result, today=today)
    except Exception:
        logger.exception("intent_layer: render failed for %s", result.intent_key)
        return None

    return IntentAnswer(
        text=text,
        intent_key=result.intent_key,
        category=result.category_hint,
        result_count=result.result_count,
        component_type=component_type,
        component_data=component_data,
    )

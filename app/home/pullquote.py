"""Hava's read on tonight — SWR-cached LLM-generated pullquote (BUILD.md step 4).

Stale-while-revalidate semantics:

* **Fresh (within TTL):** return cached, no LLM call.
* **Stale (TTL expired) AND a refresh is not already in flight:**
  return cached, spawn a background thread to regenerate.
* **Cold (no cache yet):** generate synchronously on the request thread.
  Only happens on the very first /home request after a worker boot, then
  never again until the worker restarts.
* **LLM failure:** keep showing the previous (or default) quote; retry
  next stale-hit. Never block the page on an LLM that's misbehaving.

Process-local cache: each FastAPI worker maintains its own. For a 1-hour
TTL pullquote, a few duplicate LLM calls per hour across workers is fine.
DB persistence is a future concern; in-memory keeps the surface tiny.

Voice contract: 1–3 sentences, declarative, periods only (no question
marks), at most one ``[name](url)`` link to a catalog item, never invents
venues. The system prompt enforces this; ``voice_links.render_voice_links``
turns the markdown link into a safe anchor at render time.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.chat.voice_principles import compose_voice_prompt
from app.core.llm_messages import call_anthropic_messages
from app.core.timezone import now_lake_havasu
from app.db.models import Event
from app.home.voice_links import render_voice_links

logger = logging.getLogger(__name__)

# 1-hour TTL — refresh in the background after this; keep serving stale.
_TTL = timedelta(hours=1)

# Hard fallback when the LLM is unavailable on cold-start. Voice-conformant,
# fact-free, no question marks. Periods only.
_DEFAULT_QUOTE = "It's a quiet evening in Havasu — the lake is glass, and the channel's lit up."

_VOICE_PROMPT = (
    compose_voice_prompt("pullquote")
    + "\n* If no candidate fits, write fact-free atmospheric prose with no link.\n\n"
    + "OUTPUT: just the quote. No quotation marks, no preface, no signature.\n"
)


@dataclass
class _CacheState:
    quote: str = ""
    quote_html: str = ""
    expires_at: datetime | None = None
    refreshing: bool = False
    last_error_at: datetime | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_cache = _CacheState()


# ─────────── public entrypoint ───────────


def get_quote(db: Session) -> dict[str, str]:
    """Return the pullquote dict for the home template.

    Always returns a usable result. Triggers background refresh when stale.
    Synchronously generates on cold-start; if that fails, falls back to
    the default quote (still voice-conformant, fact-free).
    """
    now = now_lake_havasu()

    # Fast path: fresh
    if _cache.quote and _cache.expires_at and now < _cache.expires_at:
        return _format_for_template(_cache.quote, _cache.quote_html, now)

    # Stale path: serve current, refresh in background
    if _cache.quote and _cache.expires_at and now >= _cache.expires_at:
        _maybe_spawn_refresh(db_factory_from_session(db))
        return _format_for_template(_cache.quote, _cache.quote_html, now)

    # Cold path: serve the deterministic default immediately and trigger
    # a background refresh. The next request will see the LLM-generated
    # quote (or the same default if the LLM is unavailable).
    _store(_DEFAULT_QUOTE, now)
    _maybe_spawn_refresh(db_factory_from_session(db))
    return _format_for_template(_cache.quote, _cache.quote_html, now)


# ─────────── internals ───────────


def db_factory_from_session(db: Session):
    """Capture the session's bind so the background thread can open its own.

    Sessions aren't thread-safe; the background refresh needs its own.
    """
    bind = db.get_bind()
    from sqlalchemy.orm import sessionmaker

    Maker = sessionmaker(bind=bind, autoflush=False, autocommit=False)
    return Maker


def _maybe_spawn_refresh(session_maker) -> None:
    """Spawn a daemon thread to regenerate. No-op if one is already running."""
    with _cache.lock:
        if _cache.refreshing:
            return
        _cache.refreshing = True
    t = threading.Thread(
        target=_refresh_worker,
        args=(session_maker,),
        name="hava-pullquote-refresh",
        daemon=True,
    )
    t.start()


def _refresh_worker(session_maker) -> None:
    """Background generator. Updates the cache; never raises."""
    try:
        with session_maker() as bg_db:
            quote = _generate(bg_db, now=now_lake_havasu())
        if quote:
            _store(quote, now_lake_havasu())
        else:
            # Generation returned nothing usable. Bump the cache so we
            # don't hammer the LLM, but keep the previous quote visible.
            with _cache.lock:
                _cache.expires_at = now_lake_havasu() + _TTL
                _cache.last_error_at = now_lake_havasu()
    except Exception:
        logger.exception("hava-pullquote-refresh failed")
    finally:
        with _cache.lock:
            _cache.refreshing = False


def _store(quote: str, now: datetime) -> None:
    quote_html = render_voice_links(quote)
    with _cache.lock:
        _cache.quote = quote
        _cache.quote_html = quote_html
        _cache.expires_at = now + _TTL


def _format_for_template(quote: str, quote_html: str, now: datetime) -> dict[str, str]:
    """Match the dict shape the home template expects."""
    posted = now.strftime("%I:%M %p").lower().lstrip("0")
    return {
        "quote": quote,
        "quote_html": quote_html,
        "byline": f"posted {posted} · refreshed every hour",
    }


# ─────────── LLM call ───────────


def _generate(db: Session, *, now: datetime) -> str | None:
    """One LLM call. Returns the quote string, or None on any failure."""
    user_text = _build_user_prompt(db, now=now)
    try:
        result = call_anthropic_messages(
            system_prompt=_VOICE_PROMPT,
            user_text=user_text,
            max_tokens=160,
            temperature=0.7,
        )
    except Exception:
        logger.exception("hava-pullquote: LLM call raised")
        return None
    if result is None:
        return None
    text = (result.text or "").strip()
    if not text:
        return None
    # Defensive: drop wrapping quotes if the LLM added them.
    if text.startswith(('"', "'", "“", "”")) and text.endswith(('"', "'", "“", "”")):
        text = text[1:-1].strip()
    return text or None


def _build_user_prompt(db: Session, *, now: datetime) -> str:
    """Compose the user message: timestamp + a few candidate venues."""
    weekday = now.strftime("%A")
    nice_time = now.strftime("%I:%M %p").lower().lstrip("0")
    nice_date = now.strftime("%B ") + str(now.day)
    candidates_block = _candidates_block(db, now=now)
    return (
        f"It's {weekday}, {nice_date}, {nice_time} in Lake Havasu City.\n\n"
        f"Candidates (you may mention AT MOST ONE, by name with a URL):\n"
        f"{candidates_block}\n\n"
        f"Write Hava's read on tonight."
    )


def _candidates_block(db: Session, *, now: datetime, limit: int = 4) -> str:
    """Pull a small set of upcoming events to give the LLM real names.

    Window: events starting today within the next ~5 hours. Keeps the
    prompt focused on what's actually next, not the whole day.
    """
    today = now.date()
    horizon = (now + timedelta(hours=5)).time()
    rows: list[Event] = (
        db.query(Event)
        .filter(
            Event.date == today,
            Event.status == "live",
            Event.start_time >= now.time(),
            Event.start_time <= horizon,
        )
        .order_by(Event.start_time.asc())
        .limit(limit)
        .all()
    )
    if not rows:
        return "(no events listed for the next few hours — write fact-free.)"
    lines: list[str] = []
    for ev in rows:
        nice_time = _format_event_time(ev.start_time)
        lines.append(
            f"- {ev.title} at {ev.location_name}, starts {nice_time}, url: /events/{ev.id}"
        )
    return "\n".join(lines)


def _format_event_time(t: Any) -> str:
    h12 = t.hour % 12 or 12
    suffix = "am" if t.hour < 12 else "pm"
    if t.minute:
        return f"{h12}:{t.minute:02d} {suffix}"
    return f"{h12} {suffix}"

"""Universal Sonics Gymnastics & Cheer — class-schedule scraper (LLM-assisted).

The studio publishes its weekly schedule as an irregular server-rendered text
grid (http-only; the https cert is broken), e.g.::

    Monday 3:00pm-4:15pm-Firecrackers Gymnastics * 3:15-4:15- Sonics Flight Class**
    4:00pm-5:00pm Recreational Gymnastics (ages 5yr-9yr) ...

Inconsistent dashes/spacing, inline age ranges, and ``*``/``**``/``***`` tier
markers (single ``*`` = a recreational class we list; ``**``/``***`` = by-placement
competitive team / all-star practices we DON'T) make a brittle regex a poor fit —
so we hand the schedule TEXT to the same server LLM used for the Parks & Rec OCR
task (a cheap text completion, not vision) and validate its structured output.

Pure-by-default: the network fetch and the LLM call are isolated and injectable,
so the tests drive parsing/validation with a recorded model reply and never touch
the network or spend a token. No DB access — the loader/pull script owns
persistence, and the studio schedules ship behind a human review gate (per
docs/scraper/HAVASU_LANES_SCRAPER_PLAN_2026-06-24.md §3), never auto-published.
Degrades to ``[]`` (one log line) when ``OPENAI_API_KEY`` is absent.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import time

import requests

try:  # same guarded import as the other OpenAI call sites
    from openai import OpenAI
except ImportError:  # pragma: no cover -- openai always present in prod
    OpenAI = None  # type: ignore[misc, assignment]

from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.openai_client import get_openai_client

logger = logging.getLogger(__name__)

SOURCE_NAME = "universal_sonics"
VENUE_NAME = "Universal Sonics Gymnastics & Cheer"
# http only — the https cert is broken (renders a login/error page). The schedule
# grid (days + times) lives on the ``action=view`` page, not the descriptions page.
SCHEDULE_URL = (
    "http://www.universalgymnasticslakehavasu.com/index.php"
    "?componentName=ClassScheduleDeluxe&scid=73927&action=view&classid=5878&offset_Class=0"
)
DEFAULT_MODEL = "gpt-4.1-mini"
_USER_AGENT = "AskHavaBot/1.0 (+https://askhava.com; Lake Havasu local directory)"

WEEKDAY_TO_INT: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_DAY_HEADER_RE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*$", re.IGNORECASE)
# Two-or-more asterisks mark a by-placement competitive team / all-star practice.
_COMPETITIVE_RE = re.compile(r"\*\*")


@dataclass(frozen=True)
class StudioClassRow:
    """One recreational class occurrence read off the schedule grid."""

    name: str
    weekday: int          # Monday=0 .. Sunday=6
    start_time: time
    end_time: time | None
    age: str | None
    source_line: str      # verbatim text the row was read from (provenance)


def fetch(url: str = SCHEDULE_URL, *, timeout: float = 30.0) -> str:
    """GET the schedule page over http (network; not used by the unit tests)."""
    resp = requests.get(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "text/html"}, timeout=timeout
    )
    resp.raise_for_status()
    return resp.text


def schedule_block(html: str) -> str:
    """Tag-stripped text from the first weekday header onward (drops the page
    chrome + class descriptions so the LLM sees only the day/time grid)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    m = _DAY_HEADER_RE.search(text)
    return text[m.start():].strip() if m else text


def extraction_system_prompt() -> str:
    return (
        "You are transcribing a youth gymnastics & cheer studio's weekly class "
        "schedule from messy text. Return ONLY the RECREATIONAL / preschool "
        "enrollable classes. EXCLUDE every by-placement competitive team or "
        "all-star practice — any class whose text carries two or more asterisks "
        "(** or ***), and the 'Sonics' competitive squads (Flight, Mini Militia, "
        "Youth Ignite, Junior/Senior Commanders, Blitz, Bombshell, Competitive, "
        "Cheer Tumbling levels). For each KEPT class return: day (full weekday "
        "name), start_time and end_time as 24h HH:MM (end_time null if absent), "
        "the class name verbatim (strip trailing * markers), age as printed (else "
        "null), and source_line = the exact text fragment you read it from. Do "
        "NOT invent classes, days, or times. Output strict JSON: "
        '{"classes":[{"day":...,"start_time":"HH:MM","end_time":"HH:MM"|null,'
        '"name":...,"age":...|null,"source_line":...}]}.'
    )


def _client(openai_symbol: object):
    if openai_symbol is None:
        return None
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    return get_openai_client(api_key, factory=openai_symbol, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)


def call_llm(schedule: str, *, model: str | None = None, openai_symbol: object = OpenAI) -> str:
    """Send the schedule text to the LLM; return its raw JSON reply (``""`` on
    failure / no key). The OpenAI symbol stays the patchable seam for tests."""
    client = _client(openai_symbol)
    if client is None:
        logger.info("universal_sonics: no OPENAI_API_KEY; returning empty extraction")
        return ""
    try:
        completion = client.chat.completions.create(
            model=model or (os.getenv("OPENAI_MODEL") or "").strip() or DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": extraction_system_prompt()},
                {"role": "user", "content": f"Schedule text:\n{schedule}"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
    except Exception:
        logger.exception("universal_sonics: LLM call failed")
        return ""
    choice = completion.choices[0] if completion.choices else None
    return (choice.message.content or "").strip() if choice and choice.message else ""


def _parse_time(value: object) -> time | None:
    s = (str(value).strip() if value is not None else "")
    if not s:
        return None
    m = _TIME_RE.match(s)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    mer = (m.group(3) or "").lower().replace(".", "")
    if mer == "pm" and hour != 12:
        hour += 12
    elif mer == "am" and hour == 12:
        hour = 0
    return time(hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def validate_rows(raw_rows: list[dict]) -> list[StudioClassRow]:
    """Keep well-formed recreational rows; drop competitive (``**``/``***``) and
    anything missing a day / start time / name. Pure (the tests drive every
    branch with recorded JSON)."""
    out: list[StudioClassRow] = []
    for r in raw_rows:
        if not isinstance(r, dict):
            continue
        src = str(r.get("source_line") or "").strip()
        if _COMPETITIVE_RE.search(src):
            continue  # belt-and-suspenders: a ** team the model failed to drop
        weekday = WEEKDAY_TO_INT.get(str(r.get("day") or "").strip().lower())
        start = _parse_time(r.get("start_time"))
        name = str(r.get("name") or "").strip().rstrip("* ").strip()
        if weekday is None or start is None or not name:
            continue
        age = str(r.get("age")).strip() if r.get("age") else None
        out.append(
            StudioClassRow(
                name=name, weekday=weekday, start_time=start,
                end_time=_parse_time(r.get("end_time")), age=age or None,
                source_line=src or name,
            )
        )
    return out


def parse_classes_json(raw_text: str) -> list[dict]:
    if not raw_text:
        return []
    try:
        data = json.loads(raw_text)
    except (ValueError, TypeError):
        logger.warning("universal_sonics: unparseable LLM reply head=%r", raw_text[:120])
        return []
    rows = data.get("classes") if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def extract_rows(
    schedule: str,
    *,
    model: str | None = None,
    openai_symbol: object = OpenAI,
    raw_text: str | None = None,
) -> list[StudioClassRow]:
    """Engine: (LLM call ->) parse -> validate. Tests pass ``raw_text`` to inject a
    recorded model reply and skip the live call."""
    text = raw_text if raw_text is not None else call_llm(
        schedule, model=model, openai_symbol=openai_symbol
    )
    return validate_rows(parse_classes_json(text))


def scrape_rows(*, model: str | None = None) -> list[StudioClassRow]:
    """Fetch the live schedule and return validated recreational rows. Network or
    parse failure yields ``[]`` (publish nothing — honesty contract)."""
    try:
        html = fetch()
    except requests.RequestException:
        logger.warning("universal_sonics: schedule fetch failed; nothing to propose")
        return []
    return extract_rows(schedule_block(html), model=model)

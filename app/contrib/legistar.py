"""legistar — Lake Havasu City council/board meetings via the Legistar Web API.

source-expansion #3. The City migrated its agendas off CivicPlus AgendaCenter to
Legistar, whose Web API is public JSON, no auth:

    https://webapi.legistar.com/v1/lakehavasucity/events?$top=20&$orderby=EventDate+desc

Each event is a meeting (City Council, Planning & Zoning, Board of Adjustment,
etc.) with a body name, date/time, location, and agenda/minutes PDF links
(``View.ashx?M=A|M&ID=..&GUID=..``). This powers the flagship "what's on the
council agenda Tuesday?" answer.

Inert build-only module: fetch + parse only, no DB writes, no orchestrator
registration. Modelled as meeting events; a ``to_event_payload`` mapper is
provided for the eventual integration step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

import httpx
from dateutil import parser as dateutil_parser

from app.contrib.rate_limiter import SourceLimiter

if TYPE_CHECKING:
    from app.contrib.event_record import EventRecord

logger = logging.getLogger(__name__)

SOURCE = "legistar"
CLIENT_NAME = "lakehavasucity"
BASE_URL = f"https://webapi.legistar.com/v1/{CLIENT_NAME}"
USER_AGENT = "havasu-chat/1.0 source-expansion (+https://havasu-chat-production.up.railway.app)"
_LIMITER = SourceLimiter("legistar", qps=0.5)


@dataclass
class LegistarMeeting:
    event_id: int | None
    body_name: str
    meeting_date: date | None
    start_time: time | None
    location: str | None
    agenda_url: str | None
    minutes_url: str | None
    comment: str | None = None
    insite_url: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def start_datetime(self) -> datetime | None:
        if self.meeting_date is None:
            return None
        return datetime.combine(self.meeting_date, self.start_time or time(0, 0))

    def dedupe_key(self) -> str:
        return f"legistar:{self.event_id}" if self.event_id is not None else (self.insite_url or self.body_name)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return dateutil_parser.parse(str(value)).date()
    except (ValueError, OverflowError):
        return None


def _parse_time(value: Any) -> time | None:
    if not value:
        return None
    try:
        return dateutil_parser.parse(str(value)).time().replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def parse_events(data: list[dict[str, Any]]) -> list[LegistarMeeting]:
    """Map raw Legistar event objects to LegistarMeeting records."""
    meetings: list[LegistarMeeting] = []
    for ev in data:
        if not isinstance(ev, dict):
            continue
        body = (ev.get("EventBodyName") or "").strip()
        if not body:
            continue
        meetings.append(
            LegistarMeeting(
                event_id=ev.get("EventId"),
                body_name=body,
                meeting_date=_parse_date(ev.get("EventDate")),
                start_time=_parse_time(ev.get("EventTime")),
                location=(ev.get("EventLocation") or "").strip() or None,
                agenda_url=(ev.get("EventAgendaFile") or "").strip() or None,
                minutes_url=(ev.get("EventMinutesFile") or "").strip() or None,
                comment=(ev.get("EventComment") or "").strip() or None,
                insite_url=(ev.get("EventInSiteURL") or "").strip() or None,
                raw={"EventId": ev.get("EventId"), "EventGuid": ev.get("EventGuid")},
            )
        )
    return meetings


def fetch_events(*, top: int = 20, client: httpx.Client | None = None) -> list[LegistarMeeting]:
    """Fetch the most recent ``top`` events, newest first."""
    params = {"$top": str(top), "$orderby": "EventDate desc"}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    owns = client is None
    c = client or httpx.Client(headers=headers, follow_redirects=True)
    try:
        resp = _LIMITER.call_with_retry(lambda: c.get(f"{BASE_URL}/events", params=params, timeout=30.0))
        if resp is None:
            raise RuntimeError("legistar events fetch failed")
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns:
            c.close()
    return parse_events(data if isinstance(data, list) else [])


def meeting_sample(m: LegistarMeeting) -> dict[str, Any]:
    return {
        "body": m.body_name,
        "when": m.start_datetime.isoformat() if m.start_datetime else None,
        "location": m.location,
        "agenda_url": m.agenda_url,
        "minutes_url": m.minutes_url,
    }


def _meeting_title(m: LegistarMeeting) -> str:
    body = m.body_name.strip()
    # "City Council" -> "City Council Meeting"; leave bodies that already read as
    # a meeting/session/hearing alone so we don't double up.
    if any(body.lower().endswith(w) for w in ("meeting", "session", "hearing", "workshop")):
        return body
    return f"{body} Meeting"


def _meeting_description(m: LegistarMeeting) -> str:
    parts = [f"{m.body_name.strip()} public meeting"]
    if m.location:
        parts.append(f"at {m.location.strip()}")
    if m.start_datetime:
        parts.append(f"on {m.start_datetime.strftime('%b %d, %Y')}")
    desc = " ".join(parts).rstrip(".") + "."
    if m.agenda_url:
        desc += f" Agenda: {m.agenda_url}"
    return desc


def to_event_records(
    meetings: list[LegistarMeeting], *, today: date | None = None
) -> list["EventRecord"]:
    """Map Legistar meetings to EventRecords for ingestion (upcoming only).

    Past meetings are dropped: the events catalog is forward-looking, so only
    meetings on/after ``today`` are surfaced (legistar fetches newest-first and
    the most-recent window mixes upcoming + just-passed meetings).
    """
    from app.contrib.event_record import EventRecord

    today = today or date.today()
    records: list[EventRecord] = []
    for m in meetings:
        if m.meeting_date is None or m.meeting_date < today:
            continue
        records.append(
            EventRecord(
                source=SOURCE,
                title=_meeting_title(m),
                start_date=m.meeting_date,
                start_time=m.start_time,
                venue_name=m.location or "Lake Havasu City",
                url=m.agenda_url or m.insite_url or m.minutes_url,
                description=_meeting_description(m),
                tags=["civic", "government", "meeting"],
                raw={"event_id": m.event_id, "body": m.body_name},
            )
        )
    return records

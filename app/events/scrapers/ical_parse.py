"""Minimal iCalendar VEVENT parser (Phase 9b).

Datetime convention: every consumer (lhc_library, lhc_parks_rec, lhusd)
treats ``ICalEvent.start``/``end`` as **naive Lake Havasu wall time** —
``.date()`` is compared against ``date.today()`` and ``.isoformat()`` strings
flow into the ingest pipeline. UTC (``Z``) and ``TZID=…`` values are therefore
converted to local wall time and returned naive, never aware.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.timezone import LAKE_HAVASU_TZ


@dataclass
class ICalEvent:
    summary: str
    uid: str
    start: datetime
    end: datetime | None
    description: str
    location: str
    url: str | None = None
    raw: dict[str, str] | None = None


def _unfold_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _to_local_naive(dt: datetime) -> datetime:
    """Convert an aware datetime to naive Lake Havasu wall time."""
    return dt.astimezone(LAKE_HAVASU_TZ).replace(tzinfo=None)


def _parse_ical_datetime(value: str, tzid: str | None = None) -> datetime:
    value = value.strip()
    if "T" in value:
        if value.endswith(("Z", "z")):
            # RFC 5545 UTC form: convert to local wall time. (Previously the
            # UTC value was returned as-is — a +7h error for genuine-UTC feeds.)
            parsed = datetime.strptime(value[:-1], "%Y%m%dT%H%M%S")
            return _to_local_naive(parsed.replace(tzinfo=timezone.utc))
        parsed = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        if tzid:
            # Both live feeds (Trumba, CivicEngage) emit TZID=America/Phoenix,
            # for which this conversion is the identity. An unrecognized TZID
            # keeps the historical assume-local behavior.
            try:
                return _to_local_naive(parsed.replace(tzinfo=ZoneInfo(tzid)))
            except (ZoneInfoNotFoundError, KeyError, ValueError):
                return parsed
        return parsed
    d = datetime.strptime(value[:8], "%Y%m%d").date()
    return datetime.combine(d, time.min)


def _split_prop(line: str) -> tuple[str, str, dict[str, str]]:
    if ":" not in line:
        return "", "", {}
    head, body = line.split(":", 1)
    parts = head.split(";")
    name = parts[0].strip().upper()
    params: dict[str, str] = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
    return name, body.strip(), params


def parse_ical_events(text: str) -> list[ICalEvent]:
    """Parse VEVENT blocks from iCal text."""
    cur: dict[str, str] = {}
    props: dict[str, dict[str, str]] = {}
    out: list[ICalEvent] = []
    in_event = False

    for line in _unfold_lines(text):
        if line == "BEGIN:VEVENT":
            in_event = True
            cur = {}
            props = {}
            continue
        if line == "END:VEVENT":
            if in_event and cur.get("SUMMARY"):
                tz = (props.get("DTSTART") or {}).get("TZID")
                start = _parse_ical_datetime(cur.get("DTSTART", ""), tz)
                end_raw = cur.get("DTEND")
                end = _parse_ical_datetime(end_raw, tz) if end_raw else None
                uid = cur.get("UID", cur.get("SUMMARY", ""))
                out.append(
                    ICalEvent(
                        summary=cur.get("SUMMARY", "").strip(),
                        uid=uid.strip(),
                        start=start,
                        end=end,
                        description=_html_to_text(cur.get("DESCRIPTION", "")),
                        location=cur.get("LOCATION", "").strip(),
                        url=cur.get("URL") or None,
                        raw=dict(cur),
                    )
                )
            in_event = False
            continue
        if not in_event:
            continue
        name, body, params = _split_prop(line)
        if name:
            cur[name] = body
            if params:
                props[name] = params

    return out


def _html_to_text(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

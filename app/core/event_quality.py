from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from pydantic import ValidationError

from app.schemas.event import EventCreate, normalize_event_url

FIELD_ORDER = [
    "title",
    "date",
    "start_time",
    "location_name",
    "description",
    "event_url",
]

FIELD_PROMPTS = {
    "title": "What should we call it? (Just needs a few characters.)",
    "date": "What day is it? You can say a weekday or something like 2026-04-20.",
    "start_time": "What time does it kick off? (e.g. 9am or 09:00:00 works.)",
    "location_name": "Where's it happening? (A neighborhood or place name is perfect.)",
    "description": "Give me a quick blurb — ~20 characters or more so folks know what they're getting.",
    "event_url": "Got a website or Facebook page for this? That helps people find more info 👍",
}

CONTACT_OPTIONAL_PROMPT = (
    "Anyone people can contact about this? (Name and number — totally optional, just skip if not)"
)

REVIEW_OFFER_MESSAGE = "Want me to send this to our team to finish up? I can hand it off for you."

SUBMITTED_REVIEW_MESSAGE = "You're in — it's submitted for review, and it'll go live once approved 🎉"


def is_loose_event_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    lower = s.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return True
    return "." in s


def normalize_partial_event(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    if "title" in out and isinstance(out["title"], str):
        out["title"] = out["title"].strip()
    if "location_name" in out and isinstance(out["location_name"], str):
        out["location_name"] = out["location_name"].strip()
    if "description" in out and isinstance(out["description"], str):
        out["description"] = out["description"].strip()
    if "event_url" in out and isinstance(out["event_url"], str) and out["event_url"].strip():
        out["event_url"] = normalize_event_url(out["event_url"].strip())
    if "contact_name" in out and isinstance(out["contact_name"], str):
        out["contact_name"] = out["contact_name"].strip() or None
    if "contact_phone" in out and isinstance(out["contact_phone"], str):
        out["contact_phone"] = out["contact_phone"].strip() or None

    d = out.get("date")
    if isinstance(d, str) and d.strip():
        s = d.strip()[:10]
        try:
            out["date"] = date.fromisoformat(s)
        except ValueError:
            pass

    t = out.get("start_time")
    if isinstance(t, str) and t.strip():
        parsed = _parse_time_string(t.strip())
        if parsed:
            out["start_time"] = parsed

    return out


def _parse_time_string(value: str) -> time | None:
    value = value.strip()
    match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", value)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
        return time(hour=h, minute=m, second=s)
    match = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)$", value, re.IGNORECASE)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        mer = match.group(3).lower()
        if mer == "pm" and h != 12:
            h += 12
        if mer == "am" and h == 12:
            h = 0
        return time(hour=h, minute=m, second=0)
    return None


def first_invalid_field(data: dict[str, Any]) -> str | None:
    data = normalize_partial_event(dict(data))
    for field in FIELD_ORDER:
        if field == "title":
            v = data.get("title")
            if not isinstance(v, str) or len(v.strip()) < 3:
                return "title"
        elif field == "date":
            v = data.get("date")
            if not isinstance(v, date):
                return "date"
        elif field == "start_time":
            v = data.get("start_time")
            if not isinstance(v, time):
                return "start_time"
        elif field == "location_name":
            v = data.get("location_name")
            if not isinstance(v, str) or len(v.strip()) < 3:
                return "location_name"
        elif field == "description":
            v = data.get("description")
            if not isinstance(v, str) or len(v.strip()) < 20:
                return "description"
        elif field == "event_url":
            v = data.get("event_url")
            if not is_loose_event_url(v):
                return "event_url"
    return None


def try_build_event_create(data: dict[str, Any], **overrides: Any) -> EventCreate:
    merged = normalize_partial_event({**data, **overrides})
    return EventCreate.model_validate(
        {
            "title": merged["title"],
            "date": merged["date"],
            "start_time": merged["start_time"],
            "end_time": merged.get("end_time"),
            "location_name": merged["location_name"],
            "description": merged["description"],
            "event_url": merged["event_url"],
            "contact_name": merged.get("contact_name"),
            "contact_phone": merged.get("contact_phone"),
            "tags": merged.get("tags", []),
            "embedding": merged.get("embedding"),
            "status": merged.get("status", "live"),
            "created_by": merged.get("created_by", "user"),
            "admin_review_by": merged.get("admin_review_by"),
        }
    )


def build_pending_review_create(data: dict[str, Any], admin_review_by: datetime) -> EventCreate:
    """Best-effort EventCreate for incomplete drafts; pads to satisfy schema minimums."""
    merged = normalize_partial_event(dict(data))
    title = (merged.get("title") or "").strip() or "Pending event"
    if len(title) < 3:
        title = "Pending event"
    loc = (merged.get("location_name") or "").strip() or "Location TBD"
    if len(loc) < 3:
        loc = "Location TBD"
    desc = (merged.get("description") or "").strip() or "Details pending team review."
    if len(desc) < 20:
        desc = "Details pending team review by our staff."
    url = (merged.get("event_url") or "").strip()
    if not is_loose_event_url(url):
        url = "https://www.lhcaz.gov/"
    d = merged.get("date")
    if not isinstance(d, date):
        d = date.today() + timedelta(days=1)
    st = merged.get("start_time")
    if not isinstance(st, time):
        st = time(12, 0, 0)
    return EventCreate(
        title=title,
        date=d,
        start_time=st,
        end_time=None,
        location_name=loc,
        description=desc,
        event_url=normalize_event_url(url),
        contact_name=merged.get("contact_name"),
        contact_phone=merged.get("contact_phone"),
        tags=merged.get("tags", []),
        embedding=merged.get("embedding"),
        status="pending_review",
        created_by="user",
        admin_review_by=admin_review_by,
    )


def apply_user_reply_to_field(field: str, message: str, partial: dict[str, Any]) -> dict[str, Any]:
    out = dict(partial)
    text = message.strip()
    if field == "title":
        out["title"] = text
    elif field == "date":
        try:
            out["date"] = date.fromisoformat(text[:10])
        except ValueError:
            low = text.lower()
            if "today" in low:
                out["date"] = date.today()
            elif "tomorrow" in low:
                out["date"] = date.today() + timedelta(days=1)
    elif field == "start_time":
        parsed = _parse_time_string(text)
        if parsed:
            out["start_time"] = parsed
    elif field == "location_name":
        out["location_name"] = text
    elif field == "description":
        out["description"] = text
    elif field == "event_url":
        out["event_url"] = text
    return normalize_partial_event(out)


# POST /api/chat (ConciergeChatRequest) — distinct from Tier 3 runtime graceful errors (handoff §3.11).
CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE = (
    "That request didn't parse — the 'query' field is required and can't be empty."
)


def _errors_touch_concierge_query_field(errors: list[dict[str, Any]]) -> bool:
    """True when validation errors target ``query`` on the JSON body (unified chat request)."""
    for err in errors:
        loc = err.get("loc")
        if not isinstance(loc, (list, tuple)) or not loc:
            continue
        if loc[-1] != "query":
            continue
        # FastAPI wraps body fields as ``('body', 'query')``; direct ``model_validate`` uses ``('query',)``.
        if len(loc) == 1 or (len(loc) >= 2 and loc[0] == "body"):
            return True
    return False


def friendly_errors(errors: list[dict[str, Any]]) -> str:
    if _errors_touch_concierge_query_field(errors):
        return CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE
    for err in errors:
        ctx = err.get("ctx")
        if ctx:
            inner = ctx.get("error")
            if isinstance(inner, ValueError):
                return str(inner)
        msg = err.get("msg", "")
        if isinstance(msg, str) and msg.startswith("Value error, "):
            return msg.replace("Value error, ", "", 1)
    return "Some event details are not valid. Please check and try again."


def friendly_validation_error(exc: ValidationError) -> str:
    return friendly_errors(exc.errors())


def has_any_contact(partial: dict[str, Any]) -> bool:
    cn = (partial.get("contact_name") or "").strip() if isinstance(partial.get("contact_name"), str) else ""
    cp = (partial.get("contact_phone") or "").strip() if isinstance(partial.get("contact_phone"), str) else ""
    return bool(cn or cp)

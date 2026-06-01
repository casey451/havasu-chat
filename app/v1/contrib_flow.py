"""Guided contribution clarify/submit logic (master spec §6)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ContributeFlow
from app.v1.contrib_extraction import extract_from_text

_URL_RE = re.compile(r"https?://\S+", re.I)


def detect_contribution_type(text: str, extraction: dict[str, Any] | None) -> str:
    ext = extraction or {}
    t = str(ext.get("type") or "").strip().lower()
    if t in ("event", "business", "tip"):
        return t
    low = (text or "").lower()
    if any(w in low for w in ("restaurant", "business", "shop", "store", "salon", "plumber")):
        return "business"
    if "tip" in low or "heads up" in low:
        return "tip"
    if any(w in low for w in ("event", "concert", "festival", "class", "workshop", "tonight")):
        return "event"
    return "event"


def _merge_payload(flow: ContributeFlow, patch: dict[str, Any]) -> dict[str, Any]:
    base = dict(flow.payload or {})
    for k, v in patch.items():
        if v is not None and str(v).strip() != "":
            base[k] = v
    return base


def _missing_for_type(contribution_type: str, payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if contribution_type == "event":
        if not payload.get("title"):
            missing.append("title")
        if not payload.get("date"):
            missing.append("date")
    elif contribution_type == "business":
        if not payload.get("title") and not payload.get("name"):
            missing.append("name")
    elif contribution_type == "tip":
        if not payload.get("notes") and not payload.get("title"):
            missing.append("notes")
    return missing


def _question_for_field(field: str) -> str:
    return {
        "title": "What's the name or title?",
        "date": "What date is it? (e.g. June 14, 2026)",
        "name": "What's the business name?",
        "notes": "What should locals know?",
    }.get(field, f"Can you share the {field}?")


def start_flow(
    db: Session,
    *,
    session_id: str,
    text: str | None,
    extraction: dict[str, Any] | None,
    image_url: str | None,
) -> ContributeFlow:
    merged_ext = dict(extraction or {})
    if text and not merged_ext:
        merged_ext = extract_from_text(text)
    ctype = detect_contribution_type(text or "", merged_ext)
    payload = {k: v for k, v in merged_ext.items() if v is not None}
    if text:
        payload.setdefault("notes", text[:2000])
        m = _URL_RE.search(text)
        if m:
            payload.setdefault("website", m.group(0))
    flow = ContributeFlow(
        session_id=session_id[:128],
        contribution_type=ctype,
        payload=payload,
        raw_text=text,
        image_url=image_url,
        extraction=merged_ext or None,
        status="in_progress",
    )
    db.add(flow)
    db.commit()
    db.refresh(flow)
    return flow


def apply_clarify(db: Session, flow: ContributeFlow, answer: str) -> ContributeFlow:
    missing = _missing_for_type(flow.contribution_type, flow.payload or {})
    field = missing[0] if missing else "notes"
    patch: dict[str, Any] = {field: answer.strip()}
    if field == "name":
        patch["title"] = patch["name"]
    flow.payload = _merge_payload(flow, patch)
    flow.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(flow)
    return flow


def flow_response(flow: ContributeFlow) -> dict[str, Any]:
    payload = flow.payload or {}
    missing = _missing_for_type(flow.contribution_type, payload)
    ready = not missing
    return {
        "flow_id": flow.id,
        "type": flow.contribution_type,
        "status": "ready" if ready else flow.status,
        "fields": payload,
        "extraction": flow.extraction,
        "image_url": flow.image_url,
        "next_question": None if ready else _question_for_field(missing[0]),
        "summary": _human_summary(flow),
    }


def _human_summary(flow: ContributeFlow) -> str:
    p = flow.payload or {}
    title = p.get("title") or p.get("name") or "your submission"
    bits = [str(title)]
    if p.get("date"):
        bits.append(f"on {p['date']}")
    if p.get("venue"):
        bits.append(f"at {p['venue']}")
    return " ".join(bits)


def flow_to_contribution_create(flow: ContributeFlow):
    from app.schemas.contribution import ContributionCreate

    p = flow.payload or {}
    et = flow.contribution_type
    entity_type = "event" if et == "event" else ("provider" if et == "business" else "tip")
    name = str(p.get("title") or p.get("name") or "Untitled")[:200]
    notes = p.get("notes") or flow.raw_text
    url = p.get("website") or p.get("organizer_url")
    ev_date: date | None = None
    ev_start: time | None = None
    if et == "event" and p.get("date"):
        try:
            ev_date = date.fromisoformat(str(p["date"])[:10])
        except ValueError:
            pass
    if et == "event" and p.get("time"):
        try:
            ts = str(p["time"])
            ev_start = time.fromisoformat(ts + ":00" if len(ts) == 5 else ts)
        except ValueError:
            pass
    return ContributionCreate(
        entity_type=entity_type,  # type: ignore[arg-type]
        submission_name=name,
        submission_url=url,  # type: ignore[arg-type]
        submission_category_hint=p.get("category"),
        submission_notes=str(notes)[:2000] if notes else None,
        event_date=ev_date,
        event_time_start=ev_start,
        source="user_submission",
    )

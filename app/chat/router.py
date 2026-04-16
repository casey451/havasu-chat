from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter

from app.core.conversation_copy import (
    ADDED_LIVE,
    CHAT_SOFT_FAIL,
    CLARIFY_DATE,
    DEAL_STUB_REPLY,
    DUPLICATE_PROMPT,
    ESCAPE_HATCH_REPLY,
    GREETING_MID_SEARCH,
    GREETING_REPLY,
    HARD_RESET_REPLY,
    MERGE_FOLLOWUP,
    MERGE_KEPT,
    MERGE_UPDATED,
    MISSING_FIELD_GLITCH,
    REJECTION_FIX,
    SERVICE_STUB_REPLY,
    SOFT_CANCEL_REPLY,
    STALE_SESSION_REPLY,
    UNCLEAR_REPLY,
    preview_event_line,
)
from app.core.dedupe import find_duplicate
from app.core.event_quality import (
    CONTACT_OPTIONAL_PROMPT,
    FIELD_PROMPTS,
    REVIEW_OFFER_MESSAGE,
    SUBMITTED_REVIEW_MESSAGE,
    apply_user_reply_to_field,
    build_pending_review_create,
    first_invalid_field,
    has_any_contact,
    normalize_partial_event,
    try_build_event_create,
)
from app.core.extraction import _embedding_input, _extract_phone, extract_event, generate_embedding
from app.core.intent import (
    ADD_EVENT,
    DEAL_SEARCH,
    GREETING,
    HARD_RESET,
    LISTING_INTENT,
    REFINEMENT,
    SEARCH_EVENTS,
    SERVICE_REQUEST,
    SOFT_CANCEL,
    UNCLEAR,
    detect_intent,
    escape_to_search,
    is_confirmation,
    is_greeting,
    is_hard_reset,
    is_rejection,
    is_skip_optional_contact,
    is_soft_cancel,
)
from app.core.search import (
    apply_audience_location_filters,
    decide_search_strategy,
    format_search_results,
    search_events,
)
from app.core.session import (
    arm_session_blocking,
    blocking_session_expired,
    clear_add_branch,
    clear_current_flow,
    clear_session_state,
    get_flow,
    get_search,
    get_session,
    set_flow_awaiting,
    soft_clear_awaits,
)
from app.core.slots import (
    extract_activity_family,
    extract_audience,
    extract_date_range,
    extract_location_hint,
    merge_activity_family,
    merge_audience,
    merge_date_range,
    merge_location_hint,
    push_recent_utterance,
)
from app.db.chat_logging import log_chat_turn
from app.db.database import get_db
from app.db.models import Event
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


def _wants_last_result_expansion(message: str) -> bool:
    m = message.lower().strip()
    return any(
        x in m
        for x in (
            "all of them",
            "all those",
            "those events",
            "these events",
            "show full details",
            "every one",
        )
    )


def _session_idle_for_greeting(session: dict) -> bool:
    flow = get_flow(session)
    if flow.get("awaiting") in ("clarify_date", "clarify_activity"):
        return False
    return not (
        session.get("awaiting_review_offer")
        or session.get("awaiting_missing_field")
        or session.get("awaiting_optional_contact")
        or session.get("awaiting_duplicate_confirmation")
        or session.get("awaiting_merge_details")
        or session.get("awaiting_confirmation")
        or session.get("partial_event")
    )


def _apply_slots_from_message(session: dict, message: str, *, listing_intent: bool) -> None:
    search = get_search(session)
    slots = search["slots"]
    lm = search.get("listing_mode", False)

    dr = extract_date_range(message)
    af = extract_activity_family(message)
    aud = extract_audience(message)
    loc = extract_location_hint(message)

    slots["date_range"] = merge_date_range(slots.get("date_range"), dr)
    slots["activity_family"] = merge_activity_family(slots.get("activity_family"), af)
    slots["audience"] = merge_audience(slots.get("audience"), aud)
    slots["location_hint"] = merge_location_hint(slots.get("location_hint"), loc)

    if listing_intent:
        search["listing_mode"] = True
    elif dr or af or aud or loc:
        search["listing_mode"] = False

    if len(message.strip()) >= 2 and not is_greeting(message):
        push_recent_utterance(search, message)


def _slot_keywords(slots: dict) -> list[str]:
    loc = (slots.get("location_hint") or "").strip()
    if not loc:
        return []
    return [w for w in re.split(r"\s+", loc.lower()) if len(w) > 2]


def _run_search_core(session: dict, db: Session, message: str, strategy: str) -> tuple[list[Event], str]:
    search = get_search(session)
    slots = search["slots"]
    utter = search.get("recent_utterances") or []
    query_message = utter[-1] if utter else message

    date_ctx = slots.get("date_range")
    if isinstance(date_ctx, dict):
        date_ctx = {"start": date_ctx["start"], "end": date_ctx["end"]}

    activity = slots.get("activity_family")
    keywords = _slot_keywords(slots)

    events = search_events(
        db=db,
        date_context=date_ctx,
        activity_type=activity,
        keywords=keywords,
        query_message=query_message,
    )
    events = apply_audience_location_filters(events, slots.get("audience"), slots.get("location_hint"))

    if _wants_last_result_expansion(message):
        ids = search.get("last_result_set", {}).get("ids") or []
        if ids:
            by_id = {e.id: e for e in events}
            ordered = [by_id[i] for i in ids if i in by_id]
            if ordered:
                events = ordered

    body = format_search_results(events, strategy, slots)
    search["last_result_set"] = {
        "ids": [e.id for e in events],
        "query_signature": query_message[:200],
    }
    return events, body


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("120/minute")
def chat(request: Request, payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    message = payload.message.strip()
    try:
        log_chat_turn(db, payload.session_id, message, "user", None)
        resp = _chat_inner(payload, message, db)
        arm_session_blocking(get_session(payload.session_id))
        log_chat_turn(db, payload.session_id, resp.response, "assistant", resp.intent)
        return resp
    except Exception:
        logging.exception("chat handler failure")
        try:
            db.rollback()
        except Exception:
            pass
        return ChatResponse(response=CHAT_SOFT_FAIL, intent="UNCLEAR", data={})


def _chat_inner(payload: ChatRequest, message: str, db: Session) -> ChatResponse:
    session_id = payload.session_id
    session = get_session(session_id)

    if blocking_session_expired(session):
        soft_clear_awaits(session)
        return ChatResponse(response=STALE_SESSION_REPLY, intent="UNCLEAR", data={})

    if is_hard_reset(message):
        clear_session_state(session_id)
        return ChatResponse(response=HARD_RESET_REPLY, intent=HARD_RESET, data={})

    if is_soft_cancel(message):
        clear_current_flow(session)
        return ChatResponse(response=SOFT_CANCEL_REPLY, intent=SOFT_CANCEL, data={})

    if session.get("awaiting_optional_contact"):
        return _handle_optional_contact_reply(session, message, db)

    if session.get("awaiting_review_offer"):
        if is_confirmation(message):
            created = _store_pending_review(session["partial_event"], db)
            clear_session_state(session_id)
            return ChatResponse(
                response=SUBMITTED_REVIEW_MESSAGE,
                intent=ADD_EVENT,
                data={"event_id": created.id, "status": "pending_review"},
            )
        if is_rejection(message):
            session["awaiting_review_offer"] = False
            session["field_retry_counts"] = {}
            inv = first_invalid_field(session["partial_event"])
            if inv:
                session["awaiting_missing_field"] = inv
                return ChatResponse(
                    response=FIELD_PROMPTS[inv],
                    intent=ADD_EVENT,
                    data={"partial_event": session["partial_event"]},
                )
            return _after_partial_update(session)

    if session.get("awaiting_missing_field"):
        return _handle_missing_field_reply(session, message, db)

    if session["awaiting_duplicate_confirmation"] and session["duplicate_candidate_event"]:
        if is_confirmation(message):
            existing_event = db.get(Event, session["duplicate_match_id"])
            session["awaiting_duplicate_confirmation"] = False
            session["awaiting_merge_details"] = True
            return ChatResponse(
                response=MERGE_FOLLOWUP.format(
                    title=existing_event.title,
                    date=existing_event.date.isoformat(),
                    time=existing_event.start_time.isoformat(),
                    location=existing_event.location_name,
                ),
                intent=ADD_EVENT,
                data={"existing_event_id": existing_event.id},
            )

        if is_rejection(message):
            created_event = _store_event(session["duplicate_candidate_event"], db)
            clear_session_state(session_id)
            return ChatResponse(
                response=ADDED_LIVE,
                intent=ADD_EVENT,
                data={"event_id": created_event.id},
            )

    if session["awaiting_merge_details"] and session["duplicate_match_id"]:
        existing_event = db.get(Event, session["duplicate_match_id"])
        if is_rejection(message):
            clear_session_state(session_id)
            return ChatResponse(
                response=MERGE_KEPT,
                intent=ADD_EVENT,
                data={"event_id": existing_event.id},
            )

        merged_event = _merge_into_existing_event(existing_event, session["duplicate_candidate_event"], message, db)
        clear_session_state(session_id)
        return ChatResponse(
            response=MERGE_UPDATED.format(title=merged_event.title),
            intent=ADD_EVENT,
            data={"event_id": merged_event.id},
        )

    if session["awaiting_confirmation"] and session["partial_event"]:
        if is_confirmation(message):
            duplicate = find_duplicate(session["partial_event"], db)
            if duplicate is not None:
                session["awaiting_confirmation"] = False
                session["awaiting_duplicate_confirmation"] = True
                session["duplicate_candidate_event"] = dict(session["partial_event"])
                session["duplicate_match_id"] = duplicate.id
                return ChatResponse(
                    response=DUPLICATE_PROMPT.format(title=duplicate.title),
                    intent=ADD_EVENT,
                    data={"duplicate_event_id": duplicate.id},
                )

            created_event = _store_event(session["partial_event"], db)
            clear_session_state(session_id)
            return ChatResponse(
                response=ADDED_LIVE,
                intent=ADD_EVENT,
                data={"event_id": created_event.id},
            )

        if is_rejection(message):
            session["awaiting_confirmation"] = False
            return ChatResponse(
                response=REJECTION_FIX,
                intent=ADD_EVENT,
                data={"partial_event": session["partial_event"]},
            )

    if escape_to_search(message) and (
        session.get("partial_event") or session.get("awaiting_confirmation")
    ):
        clear_add_branch(session)
        set_flow_awaiting(session, None)
        _apply_slots_from_message(session, message, listing_intent=False)
        session["current_intent"] = SEARCH_EVENTS
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            get_search(session)["listing_mode"],
            message,
        )
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=f"{ESCAPE_HATCH_REPLY}\n\n{body}",
            intent=SEARCH_EVENTS,
            data={"count": len(events), "search": get_search(session)},
        )

    flow_early = get_flow(session)
    if flow_early.get("awaiting") in ("clarify_date", "clarify_activity"):
        _apply_slots_from_message(session, message, listing_intent=False)
        set_flow_awaiting(session, None)
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            get_search(session)["listing_mode"],
            message,
        )
        if strategy == "CLARIFY_DATE" and not get_search(session)["slots"].get("date_range"):
            set_flow_awaiting(session, "clarify_date")
            return ChatResponse(response=CLARIFY_DATE, intent=SEARCH_EVENTS, data={"search": get_search(session)})
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        session["current_intent"] = SEARCH_EVENTS
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=body,
            intent=SEARCH_EVENTS,
            data={"count": len(events), "search": get_search(session)},
        )

    intent = detect_intent(message, session)

    if intent == GREETING:
        flow = get_flow(session)
        if flow.get("awaiting") == "narrow_followup":
            return ChatResponse(response=GREETING_MID_SEARCH, intent=GREETING, data={})
        if _session_idle_for_greeting(session):
            return ChatResponse(response=GREETING_REPLY, intent=GREETING, data={})
        return ChatResponse(response=GREETING_REPLY, intent=GREETING, data={})

    if intent == SERVICE_REQUEST:
        return ChatResponse(response=SERVICE_STUB_REPLY, intent=SERVICE_REQUEST, data={})

    if intent == DEAL_SEARCH:
        return ChatResponse(response=DEAL_STUB_REPLY, intent=DEAL_SEARCH, data={})

    if intent == LISTING_INTENT:
        clear_add_branch(session)
        _apply_slots_from_message(session, message, listing_intent=True)
        session["current_intent"] = LISTING_INTENT
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            True,
            message,
        )
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=body,
            intent=LISTING_INTENT,
            data={"count": len(events), "search": get_search(session)},
        )

    if intent == REFINEMENT:
        _apply_slots_from_message(session, message, listing_intent=False)
        session["current_intent"] = SEARCH_EVENTS
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            get_search(session)["listing_mode"],
            message,
        )
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=body,
            intent=SEARCH_EVENTS,
            data={"count": len(events), "search": get_search(session)},
        )

    if intent == ADD_EVENT:
        extracted = extract_event(message)
        session["partial_event"] = extracted
        _attach_embedding(session["partial_event"])
        session["current_intent"] = ADD_EVENT
        get_flow(session)["current"] = "add_event"
        return _after_partial_update(session)

    if session["current_intent"] == ADD_EVENT and session["partial_event"] and not session["awaiting_confirmation"]:
        extracted = extract_event(message)
        session["partial_event"] = _merge_event_updates(session["partial_event"], extracted)
        _attach_embedding(session["partial_event"])
        return _after_partial_update(session)

    if intent == UNCLEAR:
        return ChatResponse(response=UNCLEAR_REPLY, intent=intent, data={})

    if intent == SEARCH_EVENTS:
        _apply_slots_from_message(session, message, listing_intent=False)
        session["current_intent"] = SEARCH_EVENTS
        strategy = decide_search_strategy(
            get_search(session)["slots"],
            get_search(session)["listing_mode"],
            message,
        )
        if strategy == "CLARIFY_DATE":
            set_flow_awaiting(session, "clarify_date")
            return ChatResponse(response=CLARIFY_DATE, intent=SEARCH_EVENTS, data={"search": get_search(session)})
        events, body = _run_search_core(session, db, message, strategy)
        set_flow_awaiting(session, "narrow_followup" if len(events) >= 4 else None)
        get_flow(session)["current"] = "search"
        return ChatResponse(
            response=body,
            intent=SEARCH_EVENTS,
            data={"count": len(events), "search": get_search(session)},
        )

    return ChatResponse(response=UNCLEAR_REPLY, intent=UNCLEAR, data={})


def _attach_embedding(partial: dict) -> None:
    partial["embedding"] = generate_embedding(_embedding_input(partial))


def _finalize_add_flow(session: dict) -> ChatResponse:
    partial = normalize_partial_event(session["partial_event"] or {})
    session["partial_event"] = partial
    inv = first_invalid_field(partial)
    if inv:
        session["awaiting_missing_field"] = inv
        session["awaiting_confirmation"] = False
        session["awaiting_optional_contact"] = False
        return ChatResponse(
            response=FIELD_PROMPTS[inv],
            intent=ADD_EVENT,
            data={"partial_event": partial},
        )
    session["awaiting_missing_field"] = None
    if not session.get("contact_optional_answered"):
        if has_any_contact(partial):
            session["contact_optional_answered"] = True
        else:
            session["awaiting_optional_contact"] = True
            session["awaiting_confirmation"] = False
            return ChatResponse(
                response=CONTACT_OPTIONAL_PROMPT,
                intent=ADD_EVENT,
                data={"partial_event": partial},
            )
    session["awaiting_optional_contact"] = False
    session["awaiting_confirmation"] = True
    return ChatResponse(
        response=_preview_message(partial),
        intent=ADD_EVENT,
        data={"partial_event": partial},
    )


def _after_partial_update(session: dict) -> ChatResponse:
    partial = normalize_partial_event(session["partial_event"])
    session["partial_event"] = partial
    return _finalize_add_flow(session)


def _handle_missing_field_reply(session: dict, message: str, db: Session) -> ChatResponse:
    field = session["awaiting_missing_field"]
    if not field or not session["partial_event"]:
        session["awaiting_missing_field"] = None
        return ChatResponse(response=MISSING_FIELD_GLITCH, intent=ADD_EVENT, data={})

    partial = apply_user_reply_to_field(field, message, session["partial_event"])
    _attach_embedding(partial)
    session["partial_event"] = partial

    still_bad = first_invalid_field(partial) == field
    if still_bad:
        counts = session["field_retry_counts"]
        counts[field] = counts.get(field, 0) + 1
        session["field_retry_counts"] = counts
        if counts[field] >= 2:
            session["awaiting_review_offer"] = True
            session["awaiting_missing_field"] = None
            return ChatResponse(
                response=REVIEW_OFFER_MESSAGE,
                intent=ADD_EVENT,
                data={"partial_event": partial},
            )
        return ChatResponse(
            response=f"Hmm, that didn't quite work — {FIELD_PROMPTS[field]}",
            intent=ADD_EVENT,
            data={"partial_event": partial},
        )

    counts = session["field_retry_counts"]
    if field in counts:
        del counts[field]
    session["awaiting_missing_field"] = None

    next_inv = first_invalid_field(partial)
    if next_inv:
        session["awaiting_missing_field"] = next_inv
        return ChatResponse(
            response=FIELD_PROMPTS[next_inv],
            intent=ADD_EVENT,
            data={"partial_event": partial},
        )

    return _finalize_add_flow(session)


def _handle_optional_contact_reply(session: dict, message: str, db: Session) -> ChatResponse:
    partial = dict(session.get("partial_event") or {})
    if is_skip_optional_contact(message):
        session["contact_optional_answered"] = True
        session["awaiting_optional_contact"] = False
        session["awaiting_confirmation"] = True
        return ChatResponse(
            response=_preview_message(partial),
            intent=ADD_EVENT,
            data={"partial_event": partial},
        )

    extracted = extract_event(message)
    merged = _merge_event_updates(partial, extracted)
    phone = _extract_phone(message)
    if phone:
        merged["contact_phone"] = phone
    left = message
    if phone:
        left = left.replace(phone, " ")
    left = re.sub(r"\s+", " ", left).strip()
    cn = (extracted.get("contact_name") or "").strip() if extracted.get("contact_name") else ""
    if cn:
        merged["contact_name"] = cn
    elif left and len(left) > 1:
        merged["contact_name"] = left[:200]

    session["partial_event"] = merged
    _attach_embedding(merged)
    session["contact_optional_answered"] = True
    session["awaiting_optional_contact"] = False
    session["awaiting_confirmation"] = True
    return ChatResponse(
        response=_preview_message(merged),
        intent=ADD_EVENT,
        data={"partial_event": merged},
    )


def _preview_message(event: dict) -> str:
    d = event.get("date", "date TBD")
    if hasattr(d, "isoformat"):
        d = d.isoformat()
    t = event.get("start_time", "time TBD")
    if hasattr(t, "isoformat"):
        t = t.isoformat()
    lines = [
        preview_event_line(
            str(event.get("title", "Untitled")),
            str(d),
            str(t),
            str(event.get("location_name", "somewhere TBD")),
        )
        .replace("Sound right?", "")
        .strip()
    ]
    url = (event.get("event_url") or "").strip()
    if url:
        lines.append(f"Link: {url}")
    cn = (event.get("contact_name") or "").strip() if event.get("contact_name") else ""
    cp = (event.get("contact_phone") or "").strip() if event.get("contact_phone") else ""
    if cn:
        lines.append(f"Contact: {cn}")
    if cp:
        lines.append(f"Phone: {cp}")
    body = "\n".join(lines) + "\n\nSound right?"
    return body


def _merge_event_updates(existing: dict, updates: dict) -> dict:
    merged = dict(existing)
    for key, value in updates.items():
        if value:
            merged[key] = value
    return merged


def _store_event(event_data: dict, db: Session) -> Event:
    payload = try_build_event_create(event_data)
    event = Event.from_create(payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _store_pending_review(event_data: dict, db: Session) -> Event:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    deadline = now + timedelta(hours=72)
    payload = build_pending_review_create(event_data, admin_review_by=deadline)
    event = Event.from_create(payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _merge_into_existing_event(existing_event: Event, candidate_event: dict, message: str, db: Session) -> Event:
    updates = extract_event(message)

    if not existing_event.description.strip() and candidate_event.get("description"):
        existing_event.description = candidate_event["description"]

    if candidate_event.get("description") and candidate_event["description"] not in existing_event.description:
        existing_event.description = f"{existing_event.description} {candidate_event['description']}".strip()

    if updates.get("description") and updates["description"] not in existing_event.description:
        existing_event.description = f"{existing_event.description} {updates['description']}".strip()

    if candidate_event.get("event_url") and not (existing_event.event_url or "").strip():
        existing_event.event_url = str(candidate_event["event_url"]).strip()
    if candidate_event.get("contact_name") and not existing_event.contact_name:
        existing_event.contact_name = str(candidate_event["contact_name"]).strip()
    if candidate_event.get("contact_phone") and not existing_event.contact_phone:
        existing_event.contact_phone = str(candidate_event["contact_phone"]).strip()

    existing_event.embedding = candidate_event.get("embedding") or existing_event.embedding
    db.add(existing_event)
    db.commit()
    db.refresh(existing_event)
    return existing_event

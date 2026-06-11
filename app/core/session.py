from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, TypedDict

BLOCKING_SESSION_TTL_SEC = 300.0
IDLE_SESSION_RESET_SEC = 30 * 60


class SearchSlots(TypedDict):
    """Search slot memory. Values are legacy/loosely-written (None today)."""

    date_range: Any
    activity_family: Any
    audience: Any
    location_hint: Any


class LastResultSet(TypedDict):
    ids: list[Any]
    query_signature: str


class SearchState(TypedDict):
    slots: SearchSlots
    recent_utterances: list[Any]
    last_result_set: LastResultSet
    listing_mode: bool
    snapshot_stack: list[SearchSlots]


class FlowState(TypedDict):
    current: str | None
    awaiting: str | None
    awaiting_since: datetime | None


class OnboardingHints(TypedDict):
    """Onboarding + Phase 6.4 hint memory (quick taps + LLM extraction)."""

    visitor_status: str | None
    has_kids: bool | None
    age: int | None
    location: str | None


class PriorEntity(TypedDict):
    """Last resolved catalog entity for pronoun follow-ups (one deep)."""

    id: str
    name: str
    type: str
    turn_number: int


class SessionState(TypedDict, total=False):
    """In-memory chat session dict.

    ``total=False`` is honest here: sessions are built incrementally —
    ``get_session`` setdefaults the canonical keys, ``arm_session_blocking``
    pops ``blocking_mono``, and handler modules historically read keys via
    ``.get`` with defaults. ``clear_session_state`` writes the full shape.
    """

    search: SearchState
    flow: FlowState
    current_intent: Any
    partial_event: Any
    awaiting_confirmation: bool
    awaiting_duplicate_confirmation: bool
    duplicate_candidate_event: Any
    duplicate_match_id: Any
    awaiting_merge_details: bool
    awaiting_missing_field: str | None
    field_retry_counts: dict[str, int]
    awaiting_review_offer: bool
    awaiting_optional_contact: bool
    contact_optional_answered: bool
    blocking_mono: float | None
    onboarding_hints: OnboardingHints
    prior_entity: PriorEntity | None
    last_activity_at: datetime | None
    turn_number: int


sessions: dict[str, SessionState] = {}


def _default_search() -> SearchState:
    return {
        "slots": {
            "date_range": None,
            "activity_family": None,
            "audience": None,
            "location_hint": None,
        },
        "recent_utterances": [],
        "last_result_set": {"ids": [], "query_signature": ""},
        "listing_mode": False,
        "snapshot_stack": [],
    }


def _default_flow() -> FlowState:
    return {"current": None, "awaiting": None, "awaiting_since": None}


def _default_onboarding_hints() -> OnboardingHints:
    """Onboarding + Phase 6.4 hint memory (quick taps + LLM extraction)."""
    return {
        "visitor_status": None,
        "has_kids": None,
        "age": None,
        "location": None,
    }


def any_awaiting_user_reply(session: SessionState) -> bool:
    flow: Mapping[str, Any] = session.get("flow") or {}
    if flow.get("awaiting"):
        return True
    return bool(
        session.get("awaiting_confirmation")
        or session.get("awaiting_duplicate_confirmation")
        or session.get("awaiting_merge_details")
        or session.get("awaiting_missing_field")
        or session.get("awaiting_optional_contact")
        or session.get("awaiting_review_offer")
    )


def blocking_session_expired(session: SessionState) -> bool:
    start = session.get("blocking_mono")
    if start is None or not any_awaiting_user_reply(session):
        return False
    return (time.monotonic() - float(start)) > BLOCKING_SESSION_TTL_SEC


def arm_session_blocking(session: SessionState) -> None:
    if any_awaiting_user_reply(session):
        session["blocking_mono"] = time.monotonic()
    else:
        session.pop("blocking_mono", None)


def _touch_flow_awaiting(session: SessionState, awaiting: str | None) -> None:
    flow = session.setdefault("flow", _default_flow())
    flow["awaiting"] = awaiting
    if awaiting:
        flow["awaiting_since"] = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        flow["awaiting_since"] = None


def set_flow_awaiting(session: SessionState, awaiting: str | None) -> None:
    _touch_flow_awaiting(session, awaiting)


def get_flow(session: SessionState) -> FlowState:
    return session.setdefault("flow", _default_flow())


def get_search(session: SessionState) -> SearchState:
    return session.setdefault("search", _default_search())


def soft_clear_awaits(session: SessionState) -> None:
    """Clear blocking / clarification awaits; preserve search slots and listing_mode."""
    _touch_flow_awaiting(session, None)
    session["awaiting_confirmation"] = False
    session["awaiting_duplicate_confirmation"] = False
    session["awaiting_merge_details"] = False
    session["awaiting_missing_field"] = None
    session["awaiting_optional_contact"] = False
    session["awaiting_review_offer"] = False
    session.pop("blocking_mono", None)


def clear_add_branch(session: SessionState) -> None:
    """Remove in-progress add-event state; keep search block."""
    session["partial_event"] = None
    session["awaiting_confirmation"] = False
    session["awaiting_duplicate_confirmation"] = False
    session["awaiting_merge_details"] = False
    session["duplicate_candidate_event"] = None
    session["duplicate_match_id"] = None
    session["awaiting_missing_field"] = None
    session["awaiting_optional_contact"] = False
    session["awaiting_review_offer"] = False
    session["field_retry_counts"] = {}
    session["contact_optional_answered"] = False


def clear_current_flow(session: SessionState) -> None:
    """Soft cancel: drop flow awaits and add draft; keep search memory."""
    soft_clear_awaits(session)
    clear_add_branch(session)
    session["current_intent"] = None
    get_flow(session)["current"] = None


# P1-9: bound the process-local session store so a flood of client-supplied
# session_ids can't grow it without limit. This is per-worker and not durable
# across deploys / multiple workers — a shared store (Redis) is the real fix;
# this just caps memory growth within a worker.
MAX_SESSIONS = 10_000


def _evict_stale_sessions() -> None:
    """When at capacity, drop the least-recently-active sessions down to ~90%."""
    if len(sessions) < MAX_SESSIONS:
        return
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def _last_active(item: tuple[str, SessionState]) -> datetime:
        la = item[1].get("last_activity_at")
        if isinstance(la, datetime):
            return la if la.tzinfo else la.replace(tzinfo=timezone.utc)
        return epoch

    target = int(MAX_SESSIONS * 0.9)
    for sid, _ in sorted(sessions.items(), key=_last_active)[: len(sessions) - target]:
        sessions.pop(sid, None)


def clear_session_state(session_id: str) -> None:
    """Hard reset: wipe session completely."""
    if session_id not in sessions:
        _evict_stale_sessions()
    sessions[session_id] = {
        "search": _default_search(),
        "flow": _default_flow(),
        "current_intent": None,
        "partial_event": None,
        "awaiting_confirmation": False,
        "awaiting_duplicate_confirmation": False,
        "duplicate_candidate_event": None,
        "duplicate_match_id": None,
        "awaiting_merge_details": False,
        "awaiting_missing_field": None,
        "field_retry_counts": {},
        "awaiting_review_offer": False,
        "awaiting_optional_contact": False,
        "contact_optional_answered": False,
        "blocking_mono": None,
        "onboarding_hints": _default_onboarding_hints(),
        "prior_entity": None,
        "last_activity_at": None,
        "turn_number": 0,
    }


def get_session(session_id: str) -> SessionState:
    if session_id not in sessions:
        clear_session_state(session_id)
    session = sessions[session_id]
    session.setdefault("search", _default_search())
    session.setdefault("flow", _default_flow())
    session.setdefault("awaiting_missing_field", None)
    session.setdefault("field_retry_counts", {})
    session.setdefault("awaiting_review_offer", False)
    session.setdefault("awaiting_optional_contact", False)
    session.setdefault("contact_optional_answered", False)
    session.setdefault("onboarding_hints", _default_onboarding_hints())
    session.setdefault("prior_entity", None)
    session.setdefault("last_activity_at", None)
    session.setdefault("turn_number", 0)
    hints = session["onboarding_hints"]
    if isinstance(hints, dict):
        hints.setdefault("age", None)
        hints.setdefault("location", None)
    return session


def touch_session(session_id: str) -> None:
    """Update activity time; if idle >30 min, reset onboarding hints and prior_entity only."""
    session = get_session(session_id)
    now = datetime.now(timezone.utc)
    last = session.get("last_activity_at")
    if isinstance(last, datetime):
        last_aware = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        elapsed = (now - last_aware).total_seconds()
        if elapsed > IDLE_SESSION_RESET_SEC:
            session["onboarding_hints"] = _default_onboarding_hints()
            session["prior_entity"] = None
    session["last_activity_at"] = now


def update_hints_from_extraction(session_id: str, extracted: Any) -> None:
    """Merge LLM hints into ``onboarding_hints`` (latest wins per field). ``extracted`` may be None."""
    if extracted is None:
        return
    age = getattr(extracted, "age", None)
    loc = getattr(extracted, "location", None)
    if age is None and loc is None:
        return
    session = get_session(session_id)
    hints = session["onboarding_hints"]
    if not isinstance(hints, dict):
        hints = _default_onboarding_hints()
        session["onboarding_hints"] = hints
    if age is not None:
        hints["age"] = age
    if loc is not None and str(loc).strip():
        hints["location"] = str(loc).strip()


def record_entity(session_id: str, entity_name: str, turn_number: int, db: Any) -> None:
    """Store last resolved catalog entity for pronoun follow-ups (one deep)."""
    from sqlalchemy import select

    from app.db.models import Provider

    name = (entity_name or "").strip()
    if not name:
        return
    session = get_session(session_id)
    pid: str = name
    try:
        row = db.scalars(select(Provider).where(Provider.provider_name == name).limit(1)).first()
        if row is not None:
            pid = str(row.id)
    except Exception:
        logging.exception("record_entity: provider lookup failed")
    session["prior_entity"] = {
        "id": pid,
        "name": name,
        "type": "provider",
        "turn_number": int(turn_number),
    }


def push_search_snapshot(session: SessionState) -> None:
    """One-level undo stack for search slots (optional use)."""
    search = get_search(session)
    stack = search.setdefault("snapshot_stack", [])
    import copy

    snap = copy.deepcopy(search["slots"])
    stack.clear()
    stack.append(snap)


def rehydrate_session_from_logs(db: Any, session_id: str, session: SessionState) -> bool:
    """C3: rebuild durable session hints from chat_logs after a restart.

    The in-memory ``sessions`` dict dies with the process, but the hints it
    needs are already persisted one row per assistant turn (``entity_matched``,
    timestamps). When a known session_id arrives on a fresh process, read the
    turn count and the most recent matched entity back instead of starting
    blind — pronoun follow-ups ("are they open today?") keep working across
    restarts and redeploys. Freshness still applies: the prior entity is
    stamped with its real turn distance, so the existing ≤3-turn window in the
    router decays it naturally. Never raises.
    """
    try:
        from sqlalchemy import func, select

        from app.db.models import ChatLog

        total = (
            db.scalar(
                select(func.count())
                .select_from(ChatLog)
                .where(ChatLog.session_id == session_id, ChatLog.role == "assistant")
            )
            or 0
        )
        if not total:
            return False
        session["turn_number"] = int(total)
        recent = list(
            db.scalars(
                select(ChatLog)
                .where(ChatLog.session_id == session_id, ChatLog.role == "assistant")
                .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
                .limit(3)
            ).all()
        )
        for idx, row in enumerate(recent):
            name = (row.entity_matched or "").strip()
            if name:
                session["prior_entity"] = {
                    "id": name,
                    "name": name,
                    "type": "provider",
                    "turn_number": int(total) - idx,
                }
                break
        session["last_activity_at"] = datetime.now(timezone.utc)
        return True
    except Exception:
        logging.exception("session: rehydrate from chat_logs failed")
        return False

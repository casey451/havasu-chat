from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

BLOCKING_SESSION_TTL_SEC = 300.0

sessions: dict[str, dict[str, Any]] = {}


def _default_search() -> dict[str, Any]:
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


def _default_flow() -> dict[str, Any]:
    return {"current": None, "awaiting": None, "awaiting_since": None}


def _default_onboarding_hints() -> dict[str, Any]:
    """Phase 6.3 — quick-tap onboarding; values updated via ``POST /api/chat/onboarding``."""
    return {"visitor_status": None, "has_kids": None}


def any_awaiting_user_reply(session: dict[str, Any]) -> bool:
    flow = session.get("flow") or {}
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


def blocking_session_expired(session: dict[str, Any]) -> bool:
    start = session.get("blocking_mono")
    if start is None or not any_awaiting_user_reply(session):
        return False
    return (time.monotonic() - float(start)) > BLOCKING_SESSION_TTL_SEC


def arm_session_blocking(session: dict[str, Any]) -> None:
    if any_awaiting_user_reply(session):
        session["blocking_mono"] = time.monotonic()
    else:
        session.pop("blocking_mono", None)


def _touch_flow_awaiting(session: dict[str, Any], awaiting: str | None) -> None:
    flow = session.setdefault("flow", _default_flow())
    flow["awaiting"] = awaiting
    if awaiting:
        flow["awaiting_since"] = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        flow["awaiting_since"] = None


def set_flow_awaiting(session: dict[str, Any], awaiting: str | None) -> None:
    _touch_flow_awaiting(session, awaiting)


def get_flow(session: dict[str, Any]) -> dict[str, Any]:
    return session.setdefault("flow", _default_flow())


def get_search(session: dict[str, Any]) -> dict[str, Any]:
    return session.setdefault("search", _default_search())


def soft_clear_awaits(session: dict[str, Any]) -> None:
    """Clear blocking / clarification awaits; preserve search slots and listing_mode."""
    _touch_flow_awaiting(session, None)
    session["awaiting_confirmation"] = False
    session["awaiting_duplicate_confirmation"] = False
    session["awaiting_merge_details"] = False
    session["awaiting_missing_field"] = None
    session["awaiting_optional_contact"] = False
    session["awaiting_review_offer"] = False
    session.pop("blocking_mono", None)


def clear_add_branch(session: dict[str, Any]) -> None:
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


def clear_current_flow(session: dict[str, Any]) -> None:
    """Soft cancel: drop flow awaits and add draft; keep search memory."""
    soft_clear_awaits(session)
    clear_add_branch(session)
    session["current_intent"] = None
    get_flow(session)["current"] = None


def clear_session_state(session_id: str) -> None:
    """Hard reset: wipe session completely."""
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
    }


def get_session(session_id: str) -> dict[str, Any]:
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
    return session


def push_search_snapshot(session: dict[str, Any]) -> None:
    """One-level undo stack for search slots (optional use)."""
    search = get_search(session)
    stack = search.setdefault("snapshot_stack", [])
    import copy

    snap = copy.deepcopy(search["slots"])
    stack.clear()
    stack.append(snap)

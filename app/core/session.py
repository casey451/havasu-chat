from __future__ import annotations

import time
from typing import Any

BLOCKING_SESSION_TTL_SEC = 300.0

sessions: dict[str, dict[str, Any]] = {}


def any_awaiting_user_reply(session: dict[str, Any]) -> bool:
    return bool(
        session.get("awaiting_confirmation")
        or session.get("awaiting_duplicate_confirmation")
        or session.get("awaiting_merge_details")
        or session.get("awaiting_search_clarification")
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
    """Start/refresh idle deadline after we send a reply that waits on the user."""
    if any_awaiting_user_reply(session):
        session["blocking_mono"] = time.monotonic()
    else:
        session.pop("blocking_mono", None)


def get_session(session_id: str) -> dict[str, Any]:
    if session_id not in sessions:
        sessions[session_id] = {
            "current_intent": None,
            "partial_event": None,
            "awaiting_confirmation": False,
            "awaiting_duplicate_confirmation": False,
            "duplicate_candidate_event": None,
            "duplicate_match_id": None,
            "awaiting_merge_details": False,
            "search_context": {"date_context": None, "activity_type": None, "keywords": []},
            "awaiting_search_clarification": False,
            "pending_search_question": None,
            "awaiting_missing_field": None,
            "field_retry_counts": {},
            "awaiting_review_offer": False,
            "awaiting_optional_contact": False,
            "contact_optional_answered": False,
        }
    session = sessions[session_id]
    session.setdefault("awaiting_missing_field", None)
    session.setdefault("field_retry_counts", {})
    session.setdefault("awaiting_review_offer", False)
    session.setdefault("awaiting_optional_contact", False)
    session.setdefault("contact_optional_answered", False)
    session.setdefault("awaiting_narrow_followup_search", False)
    session.setdefault("blocking_mono", None)
    sc = session.get("search_context") or {}
    sc.setdefault("keywords", [])
    session["search_context"] = sc
    return session


def clear_session_state(session_id: str) -> None:
    session = get_session(session_id)
    session["current_intent"] = None
    session["partial_event"] = None
    session["awaiting_confirmation"] = False
    session["awaiting_duplicate_confirmation"] = False
    session["duplicate_candidate_event"] = None
    session["duplicate_match_id"] = None
    session["awaiting_merge_details"] = False
    session["search_context"] = {"date_context": None, "activity_type": None, "keywords": []}
    session["awaiting_search_clarification"] = False
    session["pending_search_question"] = None
    session["awaiting_missing_field"] = None
    session["field_retry_counts"] = {}
    session["awaiting_review_offer"] = False
    session["awaiting_optional_contact"] = False
    session["contact_optional_answered"] = False
    session["awaiting_narrow_followup_search"] = False
    session["blocking_mono"] = None

from __future__ import annotations

from typing import Any


sessions: dict[str, dict[str, Any]] = {}


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
            "search_context": {"date_context": None, "activity_type": None},
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
    session["search_context"] = {"date_context": None, "activity_type": None}
    session["awaiting_search_clarification"] = False
    session["pending_search_question"] = None
    session["awaiting_missing_field"] = None
    session["field_retry_counts"] = {}
    session["awaiting_review_offer"] = False
    session["awaiting_optional_contact"] = False
    session["contact_optional_answered"] = False

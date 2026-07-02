from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, TypedDict

IDLE_SESSION_RESET_SEC = 30 * 60


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

    (The Track-A add-event flow/await state machine — search/flow sub-dicts,
    the awaiting_* keys, blocking TTL — was deleted 2026-07-02: POST /chat and
    its conversational add-event flow no longer exist; only its own tests kept
    it green. What remains is what the concierge actually uses: onboarding
    hints, prior-entity memory, activity/turn bookkeeping, and eviction.)

    ``total=False`` is honest here: sessions are built incrementally —
    ``get_session`` setdefaults the canonical keys, ``arm_session_blocking``
    pops ``blocking_mono``, and handler modules historically read keys via
    ``.get`` with defaults. ``clear_session_state`` writes the full shape.
    """

    onboarding_hints: OnboardingHints
    prior_entity: PriorEntity | None
    last_activity_at: datetime | None
    turn_number: int


sessions: dict[str, SessionState] = {}




def _default_onboarding_hints() -> OnboardingHints:
    """Onboarding + Phase 6.4 hint memory (quick taps + LLM extraction)."""
    return {
        "visitor_status": None,
        "has_kids": None,
        "age": None,
        "location": None,
    }












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
        "onboarding_hints": _default_onboarding_hints(),
        "prior_entity": None,
        "last_activity_at": None,
        "turn_number": 0,
    }


def get_session(session_id: str) -> SessionState:
    if session_id not in sessions:
        clear_session_state(session_id)
    session = sessions[session_id]
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

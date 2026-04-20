from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import ChatLog


def log_unified_route(
    db: Session,
    *,
    session_id: str,
    query_text_hashed: str,
    normalized_query: str,
    mode: str,
    sub_intent: str | None,
    entity_matched: str | None,
    tier_used: str,
    latency_ms: int,
    response_text: str,
    llm_tokens_used: int | None = None,
    llm_input_tokens: int | None = None,
    llm_output_tokens: int | None = None,
    feedback_signal: str | None = None,
) -> None:
    """Persist one unified-router turn (assistant message + analytics). Never raises."""
    try:
        legacy_intent = (sub_intent or mode or "")[:64] or None
        row = ChatLog(
            session_id=session_id[:128],
            message=(response_text or "")[:48000],
            role="assistant",
            intent=legacy_intent,
            query_text_hashed=query_text_hashed[:128],
            normalized_query=(normalized_query or "")[:48000] if normalized_query else None,
            mode=mode[:32] if mode else None,
            sub_intent=sub_intent[:64] if sub_intent else None,
            entity_matched=entity_matched[:512] if entity_matched else None,
            tier_used=tier_used[:32] if tier_used else None,
            latency_ms=latency_ms,
            llm_tokens_used=llm_tokens_used,
            llm_input_tokens=llm_input_tokens,
            llm_output_tokens=llm_output_tokens,
            feedback_signal=feedback_signal[:32] if feedback_signal else None,
        )
        db.add(row)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        logging.exception("unified route chat_logs insert failed")


def log_chat_turn(db: Session, session_id: str, text: str, role: str, intent: str | None) -> None:
    """Persist one chat line. Never raises — failures are logged only."""
    try:
        row = ChatLog(
            session_id=session_id[:128],
            message=(text or "")[:48000],
            role=role if role in ("user", "assistant") else "user",
            intent=intent[:64] if intent else None,
        )
        db.add(row)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        logging.exception("chat_logs insert failed")

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import ChatLog


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

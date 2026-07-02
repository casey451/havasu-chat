"""Chat history + message alias (master spec §4.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ChatLog

router = APIRouter()


@router.get("/api/chat/history")
def chat_history(
    session_id: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    sid = session_id.strip()[:128]
    # Fetch the NEWEST `limit` rows, then flip back to chronological order.
    # Ascending-then-limit returned the oldest rows, so restoring a session
    # longer than `limit` turns replayed its beginning, not its latest turns.
    rows = list(
        db.scalars(
            select(ChatLog)
            .where(ChatLog.session_id == sid)
            .order_by(ChatLog.created_at.desc())
            .limit(limit)
        ).all()
    )
    rows.reverse()
    messages = [
        {
            "role": r.role,
            "content": r.message,
            "tier_used": r.tier_used,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            # C3 conversation restore (additive — existing consumers unaffected):
            # the user's side of the turn and the id that keys feedback thumbs.
            "id": r.id,
            "query": r.normalized_query,
        }
        for r in rows
    ]
    return {"session_id": sid, "messages": messages}

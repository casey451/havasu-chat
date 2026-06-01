from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.chat.disclosure_render import consume_decision
from app.db.models import ChatLog

if TYPE_CHECKING:
    from app.chat.audience_signal import AudienceSignal


# Lane S3: Cursor (Lane S1) is adding the ``audience_signal`` column to
# ``chat_logs`` in parallel. Until that lands, ``hasattr(ChatLog, ...)`` is
# False and the assignment is skipped. Module-level flag keeps the warning to
# one emission per process — no per-request log spam while we wait for the
# schema migration.
_audience_signal_warned_once: bool = False


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
    audience_signal: "AudienceSignal | None" = None,
    cache_status: str | None = None,
    timing_ms: dict | None = None,
) -> str | None:
    """Persist one unified-router turn (assistant message + analytics). Never raises.

    Returns the new ``chat_logs.id`` (UUID string) on success, or ``None`` on failure.
    """
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
            cache_status=cache_status[:32] if cache_status else None,
            timing_ms=timing_ms,
        )
        telemetry = consume_decision()
        if telemetry is not None:
            row.disclosure_regime = telemetry.regime.value[:32]
            row.disclosure_sponsor_id = telemetry.sponsor_id[:64] if telemetry.sponsor_id else None
            row.disclosure_tone_allowlist_passed = telemetry.tone_allowlist_passed
            row.disclosure_eligible = telemetry.eligible
        # Lane S3 defensive write: only set audience_signal when the column
        # exists on ChatLog (Lane S1 / Cursor migration). Until the schema
        # migration lands, skip silently and log a single one-shot warning so
        # ops can confirm the persistence-gap is intentional.
        if audience_signal is not None:
            if hasattr(row, "audience_signal"):
                try:
                    row.audience_signal = audience_signal.audience[:32]
                except Exception:
                    logging.exception("audience_signal assignment failed; persistence skipped")
            else:
                global _audience_signal_warned_once
                if not _audience_signal_warned_once:
                    _audience_signal_warned_once = True
                    logging.warning(
                        "audience_signal column not yet present on ChatLog; "
                        "skipping persistence. The column is added by Alembic "
                        "revision f7e8d9c0b1a2 (Lane S1, 2026-05-08). Run "
                        "`alembic upgrade head` against the production DB to "
                        "enable persistence — no environment variable required."
                    )
        db.add(row)
        db.commit()
        return str(row.id)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        logging.exception("unified route chat_logs insert failed")
        return None

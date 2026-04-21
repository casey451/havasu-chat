"""Tests for ``llm_mention_store`` (Phase 5.5)."""

from __future__ import annotations

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.llm_mention_store import (
    count_mentions,
    create_mention,
    dismiss_mention,
    get_mention,
    list_mentions,
    promote_mention,
)
from app.db.models import ChatLog, Contribution, LlmMentionedEntity


def _chat_log(db) -> ChatLog:
    row = ChatLog(session_id="m-store", message="assistant reply", role="assistant")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_create_mention_persists() -> None:
    with SessionLocal() as db:
        log = _chat_log(db)
        m = create_mention(db, str(log.id), "Test Entity Name", "ctx")
        assert m is not None
        assert m.mentioned_name == "Test Entity Name"
        assert m.chat_log_id == str(log.id)
        db.delete(m)
        db.delete(log)
        db.commit()


def test_duplicate_returns_none() -> None:
    with SessionLocal() as db:
        log = _chat_log(db)
        a = create_mention(db, str(log.id), "Dup Name", "c1")
        b = create_mention(db, str(log.id), "Dup Name", "c2")
        assert a is not None
        assert b is None
        for row in db.execute(select(LlmMentionedEntity).where(LlmMentionedEntity.chat_log_id == str(log.id))).scalars():
            db.delete(row)
        db.delete(log)
        db.commit()


def test_list_with_status_filter() -> None:
    with SessionLocal() as db:
        log = _chat_log(db)
        m1 = create_mention(db, str(log.id), "Alpha Zed", "x")
        assert m1 is not None
        dismiss_mention(db, m1.id, "noise")
        log2 = _chat_log(db)
        m2 = create_mention(db, str(log2.id), "Beta Qed", "y")
        assert m2 is not None
        unrev = list_mentions(db, status="unreviewed", limit=200, offset=0)
        ids = {x.id for x in unrev}
        assert m2.id in ids
        assert m1.id not in ids
        db.delete(get_mention(db, m2.id))
        db.delete(get_mention(db, m1.id))
        db.delete(log2)
        db.delete(log)
        db.commit()


def test_dismiss_updates_fields() -> None:
    with SessionLocal() as db:
        log = _chat_log(db)
        m = create_mention(db, str(log.id), "To Dismiss", "z")
        out = dismiss_mention(db, m.id, "not_relevant")
        assert out is not None
        assert out.status == "dismissed"
        assert out.dismissal_reason == "not_relevant"
        assert out.reviewed_at is not None
        db.delete(out)
        db.delete(log)
        db.commit()


def test_promote_links_contribution() -> None:
    with SessionLocal() as db:
        log = _chat_log(db)
        m = create_mention(db, str(log.id), "Promo Ent", "z")
        c = Contribution(
            entity_type="tip",
            submission_name="linked tip",
            source="operator_backfill",
            status="pending",
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        out = promote_mention(db, m.id, c.id)
        assert out is not None
        assert out.promoted_to_contribution_id == c.id
        assert out.status == "promoted"
        db.delete(out)
        db.delete(c)
        db.delete(log)
        db.commit()


def test_count_matches_list() -> None:
    with SessionLocal() as db:
        log = _chat_log(db)
        create_mention(db, str(log.id), "Count A", None)
        create_mention(db, str(log.id), "Count B", None)
        n = count_mentions(db, status="unreviewed")
        rows = list_mentions(db, status="unreviewed", limit=200, offset=0)
        assert n >= len([r for r in rows if r.chat_log_id == str(log.id)])
        for row in db.execute(select(LlmMentionedEntity).where(LlmMentionedEntity.chat_log_id == str(log.id))).scalars():
            db.delete(row)
        db.delete(log)
        db.commit()


def test_get_mention_by_id() -> None:
    with SessionLocal() as db:
        log = _chat_log(db)
        m = create_mention(db, str(log.id), "Getter", None)
        g = get_mention(db, m.id)
        assert g is not None
        assert g.mentioned_name == "Getter"
        db.delete(m)
        db.delete(log)
        db.commit()

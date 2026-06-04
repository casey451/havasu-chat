"""Batch publish endpoint for the ``publish_approved`` job (machine-ingest token).

When a worker claims a ``publish_approved`` job it calls ``POST /api/ingest/publish``
to promote eligible pending scraped findings in bulk. Each row funnels through the
same ``publish_contribution`` engine as the auto-at-ingest path, so behavior is
identical and idempotent. Gated by the same ``SCHEDULE_HUNT_AUTOPUBLISH`` kill-switch
(``dry_run`` previews eligibility regardless of the gate, writing nothing).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.ingest import require_ingest_token
from app.contrib.autopublish_policy import autopublish_enabled, is_eligible, meets_confidence_bar
from app.contrib.schedule_publish import publish_contribution
from app.db.contribution_store import list_contributions
from app.db.database import get_db
from app.db.models import Contribution

router = APIRouter(prefix="/api/ingest", tags=["ingest-publish"])

IngestAuth = Annotated[None, Depends(require_ingest_token)]
DbSession = Annotated[Session, Depends(get_db)]

_INGEST_SOURCE = "facebook_scrape"


class PublishRequest(BaseModel):
    contribution_ids: list[int] | None = None
    dry_run: bool = False
    limit: int = 200


def _candidates(db: Session, req: PublishRequest) -> list[Contribution]:
    if req.contribution_ids:
        rows = [db.get(Contribution, cid) for cid in req.contribution_ids]
        return [r for r in rows if r is not None]
    return list(
        list_contributions(
            db, status="pending", source=_INGEST_SOURCE, limit=max(1, min(req.limit, 500))
        )
    )


@router.post("/publish")
def publish_batch(_: IngestAuth, db: DbSession, req: PublishRequest) -> dict:
    """Promote eligible pending scraped findings. Idempotent; safe to re-run.

    ``dry_run`` (no writes): reports which candidates meet the confidence bar.
    Otherwise: if the kill-switch is off, publishes nothing; else publishes each
    eligible row and returns ``{published, skipped, errors}``.
    """
    candidates = _candidates(db, req)

    if req.dry_run:
        eligible = [c.id for c in candidates if meets_confidence_bar(c)]
        return {
            "dry_run": True,
            "autopublish_enabled": autopublish_enabled(),
            "candidates": len(candidates),
            "would_publish": len(eligible),
            "would_publish_ids": eligible,
        }

    if not autopublish_enabled():
        return {
            "published": 0,
            "skipped": len(candidates),
            "errors": 0,
            "note": "SCHEDULE_HUNT_AUTOPUBLISH disabled — nothing published.",
        }

    published = skipped = errors = 0
    published_ids: list[int] = []
    for c in candidates:
        if not is_eligible(c):
            skipped += 1
            continue
        try:
            result = publish_contribution(db, c)
        except Exception:  # noqa: BLE001 — one bad row must not abort the batch
            db.rollback()
            errors += 1
            continue
        if result.get("status") == "published":
            published += 1
            published_ids.append(c.id)
        else:
            skipped += 1
    return {
        "published": published,
        "skipped": skipped,
        "errors": errors,
        "published_ids": published_ids,
    }

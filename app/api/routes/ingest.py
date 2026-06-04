"""Machine-to-machine ingest API for the autonomous Facebook scraper (Phase A).

OpenClaw's sweep subagent curl-POSTs extracted findings here. Each finding is
written to the existing ``contributions`` queue with ``source="facebook_scrape"``
and ``status="pending"`` so it flows through the SAME review/promote pipeline as
every other contribution (admin_contributions / admin_mentions). Auth is a bearer
token (``INGEST_API_TOKEN``), deliberately distinct from the human admin-session
cookie — machines use a token, people use the cookie.
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.bootstrap_env import ensure_dotenv_loaded
from app.contrib.autopublish_policy import is_eligible
from app.contrib.schedule_publish import publish_contribution
from app.db.contribution_store import (
    create_contribution,
    has_pending_or_approved_duplicate_url,
    has_pending_or_approved_program_dup,
    normalize_submission_url,
)
from app.db.database import get_db
from app.schemas.contribution import ContributionCreate

ensure_dotenv_loaded()

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# Findings always land as this source, forced server-side so a leaked token
# can never masquerade as operator- or admin-origin content.
_INGEST_SOURCE = "facebook_scrape"


def _ingest_token_from_env() -> str | None:
    """Read INGEST_API_TOKEN at call time (correct for Railway/runtime). None disables ingest."""
    raw = os.getenv("INGEST_API_TOKEN")
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def require_ingest_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """Bearer-token gate for machine ingest.

    Secure by default: if INGEST_API_TOKEN is unset, every request is refused
    (503), so the door is never silently wide open. Constant-time comparison.
    """
    expected = _ingest_token_from_env()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingest is not configured (INGEST_API_TOKEN unset).",
        )
    prefix = "Bearer "
    presented = (
        authorization[len(prefix) :]
        if authorization and authorization.startswith(prefix)
        else ""
    )
    if not presented or not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing ingest token.",
        )


IngestAuth = Annotated[None, Depends(require_ingest_token)]
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/contribution", status_code=status.HTTP_201_CREATED)
def ingest_contribution(
    _: IngestAuth,
    payload: ContributionCreate,
    db: DbSession,
    response: Response,
) -> dict:
    """Queue one scraped finding as a pending contribution.

    Idempotent on ``submission_url``: if a pending/approved contribution already
    has that URL, returns 200 ``{"status": "duplicate"}`` without inserting. The
    scraper also dedupes on its side; this is defense-in-depth.
    """
    # Force provenance server-side regardless of what the caller sent.
    data = payload.model_copy(update={"source": _INGEST_SOURCE})

    normalized = normalize_submission_url(
        str(data.submission_url) if data.submission_url is not None else None
    )
    if normalized and has_pending_or_approved_duplicate_url(db, normalized):
        response.status_code = status.HTTP_200_OK
        return {"status": "duplicate", "submission_url": normalized}

    # Scraped class schedules carry a source_url (shared per page) but no
    # submission_url, so the URL dedup above never fires for them. Dedup the
    # program finding on (target_entity_id, proposed_record.title) so a repeated
    # daily run doesn't re-queue the same class. Distinct classes on the same
    # page differ by title and are kept.
    proposed = data.proposed_record if isinstance(data.proposed_record, dict) else {}
    finding_title = proposed.get("title")
    if (
        data.entity_type == "program"
        and data.target_entity_id
        and has_pending_or_approved_program_dup(db, data.target_entity_id, finding_title)
    ):
        response.status_code = status.HTTP_200_OK
        return {
            "status": "duplicate",
            "reason": "program_already_queued",
            "target_entity_id": data.target_entity_id,
            "title": finding_title,
        }

    row = create_contribution(db, data)

    # Auto-publish high-confidence class schedules onto their existing venue, if
    # the kill-switch is enabled. The contribution row is always kept (audit);
    # anything not eligible or that doesn't cleanly resolve stays pending for
    # manual review in /admin/contributions.
    if is_eligible(row):
        result = publish_contribution(db, row)
        if result.get("status") == "published":
            return {
                "status": "published",
                "id": row.id,
                "entity_id": result.get("entity_id"),
            }
    return {"status": "queued", "id": row.id, "contribution_status": row.status}

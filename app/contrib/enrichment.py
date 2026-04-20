"""Background enrichment for contributions (Phase 5.2)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from sqlalchemy.orm import Session

from app.contrib.places_client import lookup_provider
from app.contrib.url_fetcher import fetch_url_metadata
from app.db.models import Contribution

logger = logging.getLogger(__name__)


def enrich_contribution(
    contribution_id: int,
    session_factory: Callable[[], Session],
) -> None:
    """Fetch URL metadata + Places data; update row. Uses a fresh DB session."""
    db = session_factory()
    try:
        row = db.get(Contribution, contribution_id)
        if row is None:
            logger.info("enrichment: contribution id=%s not found", contribution_id)
            return

        if row.submission_url:
            uf = fetch_url_metadata(row.submission_url)
            row.url_title = uf.title
            row.url_description = uf.description
            row.url_fetch_status = uf.status
            row.url_fetched_at = uf.fetched_at
            db.commit()

        if row.entity_type == "provider":
            pl = lookup_provider(row.submission_name)
            if pl.status in ("success", "low_confidence"):
                row.google_place_id = pl.place_id
                row.google_enriched_data = _serialize_places_result(pl)
            else:
                row.google_place_id = None
                row.google_enriched_data = {
                    "status": pl.status,
                    "error": pl.error_message,
                }
            db.commit()
    except Exception:
        logger.exception("enrichment failed for contribution id=%s", contribution_id)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _serialize_places_result(pl: Any) -> dict[str, Any]:
    """Structured blob for ``google_enriched_data`` (operator + audit)."""
    base = pl.raw_response if isinstance(getattr(pl, "raw_response", None), dict) else {}
    out: dict[str, Any] = {
        "lookup_status": pl.status,
        "place_id": pl.place_id,
        "display_name": pl.display_name,
        "formatted_address": pl.formatted_address,
        "phone": pl.phone,
        "website_uri": pl.website_uri,
        "regular_opening_hours": pl.regular_opening_hours,
        "types": pl.types,
        "location": pl.location,
        "business_status": pl.business_status,
    }
    out = {k: v for k, v in out.items() if v is not None}
    if base:
        out["places_api_response"] = cast(dict[str, Any], base)
    return out

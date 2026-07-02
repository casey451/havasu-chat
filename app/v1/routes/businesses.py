"""GET /api/businesses* — providers as businesses (master spec §4.1)."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter, public_api_rate_limit
from app.db.database import get_db
from app.db.models import Provider
from app.providers import queries as provider_queries
from app.v1.categories import bucket_for_legacy_category
from app.v1.serializers import business_from_provider

router = APIRouter()


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


@router.get("/api/businesses")
@limiter.limit(public_api_rate_limit)
def list_businesses(
    request: Request,
    db: Session = Depends(get_db),
    category: str | None = None,
    subcategory: str | None = None,
    q: str | None = None,
    near_lat: float | None = Query(None, alias="lat"),
    near_lng: float | None = Query(None, alias="lng"),
    sort: str = Query("name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = select(Provider).where(
        Provider.is_active.is_(True),
        Provider.draft.is_(False),
    )
    if category:
        bucket = category.strip().lower()
        # Filter in Python after fetch for bucket mapping (legacy categories vary).
        pass
    if subcategory:
        # Prefer the canonical second-level column (P0 Task 2); fall back to a
        # Google-type substring match for rows not yet classified.
        sub = subcategory.strip().lower()
        stmt = stmt.where(
            (Provider.subcategory == sub)
            | (Provider.subcategory.is_(None) & Provider.google_primary_category.ilike(f"%{sub}%"))
        )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(Provider.provider_name.ilike(needle))

    # Fast path (audit 2026-07-01): with no legacy-bucket filter and no geo
    # sort, page in SQL instead of materializing the whole active catalog per
    # request — the unfiltered call was also the cheapest full-directory
    # scrape, now rate-limited above.
    if not category and (near_lat is None or near_lng is None):
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        if sort == "rating":
            stmt = stmt.order_by(Provider.google_rating.desc().nullslast())
        else:
            stmt = stmt.order_by(func.lower(Provider.provider_name).asc())
        page = list(db.scalars(stmt.offset(offset).limit(limit)).all())
        return {
            "items": [business_from_provider(p) for p in page],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    rows = list(db.scalars(stmt).all())
    if category:
        bucket = category.strip().lower()
        rows = [p for p in rows if bucket_for_legacy_category(p.category) == bucket]
    if near_lat is not None and near_lng is not None:
        scored: list[tuple[float, Provider]] = []
        for p in rows:
            if p.lat is None or p.lng is None:
                continue
            scored.append((_haversine_miles(near_lat, near_lng, p.lat, p.lng), p))
        scored.sort(key=lambda x: x[0])
        rows = [p for _, p in scored]
    elif sort == "rating":
        rows.sort(key=lambda p: (p.google_rating is None, -(p.google_rating or 0)))
    else:
        rows.sort(key=lambda p: (p.provider_name or "").lower())
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "items": [business_from_provider(p) for p in page],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/businesses/{slug}")
def get_business(slug: str, db: Session = Depends(get_db)) -> dict:
    provider = provider_queries.get_provider_by_slug(db, slug)
    if provider is None or not provider.is_active or provider.draft:
        raise HTTPException(status_code=404, detail="not_found")
    return business_from_provider(provider)

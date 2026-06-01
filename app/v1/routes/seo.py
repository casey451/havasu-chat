"""SEO URL aliases from master spec (§9) → existing routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.providers import queries as provider_queries
from app.v1.categories import BUCKET_SLUG_REDIRECTS

router = APIRouter(tags=["v1-seo"])


@router.get("/lake-havasu")
def lake_havasu_home() -> RedirectResponse:
    return RedirectResponse(url="/home", status_code=301)


@router.get("/lake-havasu/categories/{bucket}")
def lake_havasu_category(bucket: str) -> RedirectResponse:
    dest = BUCKET_SLUG_REDIRECTS.get(bucket.strip().lower())
    if not dest:
        raise HTTPException(status_code=404, detail="not_found")
    return RedirectResponse(url=dest, status_code=301)


@router.get("/lake-havasu/{slug}")
def lake_havasu_business(slug: str, db: Session = Depends(get_db)) -> RedirectResponse:
    provider = provider_queries.get_provider_by_slug(db, slug)
    if provider is None or not provider.is_active or provider.draft:
        raise HTTPException(status_code=404, detail="not_found")
    return RedirectResponse(url=f"/provider/{slug}", status_code=301)

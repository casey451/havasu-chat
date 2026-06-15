"""SEO URL aliases from master spec (§9) → existing routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.categories.router import render_cuisine_landing, render_subcategory_landing
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


@router.get("/lake-havasu/{slug}", response_model=None)
def lake_havasu_business(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    open_now: str | None = Query(None, alias="open"),
    rating: str | None = Query(None),
    sort: str | None = Query(None),
    late: str | None = Query(None),
    weekends: str | None = Query(None),
) -> HTMLResponse | RedirectResponse:
    """Subcategory SEO landing, else the business-profile alias.

    A known subcategory token (``/lake-havasu/home-services``) renders its own
    listing page with a dedicated headline + facets. Otherwise the token is
    treated as a business slug and 301s to ``/provider/{slug}``. Subcategory
    slugs and provider slugs share this namespace; subcategory wins (they are a
    small fixed set and we never mint a provider slug that collides).
    """
    landing = render_subcategory_landing(
        request,
        db,
        subcategory_slug=slug,
        open_now=open_now,
        rating=rating,
        sort=sort,
        late=late,
        weekends=weekends,
    )
    if landing is not None:
        return landing

    # A cuisine token (``/lake-havasu/mexican``) renders the Eat & Drink listing
    # filtered to that cuisine, when it clears the thin-page gate. Falls through
    # to the provider alias when it isn't a (publishable) cuisine.
    cuisine_landing = render_cuisine_landing(
        request,
        db,
        cuisine_slug=slug,
        open_now=open_now,
        rating=rating,
        sort=sort,
        late=late,
        weekends=weekends,
    )
    if cuisine_landing is not None:
        return cuisine_landing

    provider = provider_queries.get_provider_by_slug(db, slug)
    if provider is None or not provider.is_active or provider.draft:
        raise HTTPException(status_code=404, detail="not_found")
    return RedirectResponse(url=f"/provider/{slug}", status_code=301)

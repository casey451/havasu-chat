"""WP-6 provider-profile rendering: DL-4 reviews, DL-11 lock, DL-12 rating
threshold, L4 hours table/fallback, SEO JSON-LD.

These assert the rendered ``/provider/<slug>`` HTML — the template is the real
renderer for these surfaces (the view-model is unowned by WP-6), so end-to-end
checks are the honest level of coverage.
"""

from __future__ import annotations

import json
import re
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Entity, Provider
from app.main import app


def _cleanup(slug: str) -> None:
    with SessionLocal() as db:
        pr = db.query(Provider).filter_by(slug=slug).first()
        eid = pr.entity_id if pr else None
        if pr:
            db.delete(pr)
        if eid:
            en = db.get(Entity, eid)
            if en:
                db.delete(en)
        db.commit()


def _get(slug: str) -> str:
    with TestClient(app) as client:
        r = client.get(f"/provider/{slug}")
    assert r.status_code == 200
    return r.text


def _jsonld(body: str) -> dict:
    m = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', body, re.DOTALL
    )
    assert m, "LocalBusiness JSON-LD block missing"
    return json.loads(m.group(1))


# --- DL-12 / D5: rating threshold (>=3 reviews) identical across surfaces ---


def test_rating_shown_at_or_above_three_reviews() -> None:
    suf = uuid4().hex[:8]
    slug = f"wp6-rate-yes-{suf}"
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"Rated Co {suf}",
                category="home_services",
                source="test-wp6",
                slug=slug,
                draft=False,
                is_active=True,
                verified=True,
                google_rating=4.6,
                google_review_count=12,
            )
        )
        db.commit()
    try:
        body = _get(slug)
        assert "4.6" in body
        assert "(12)" in body
        assert "New / few reviews yet" not in body
        ld = _jsonld(body)
        assert ld["aggregateRating"]["ratingValue"] == 4.6
        assert ld["aggregateRating"]["reviewCount"] == 12
    finally:
        _cleanup(slug)


def test_rating_hidden_below_three_reviews_shows_new_copy() -> None:
    suf = uuid4().hex[:8]
    slug = f"wp6-rate-no-{suf}"
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"Fresh Co {suf}",
                category="home_services",
                source="test-wp6",
                slug=slug,
                draft=False,
                is_active=True,
                verified=True,
                google_rating=5.0,
                google_review_count=2,  # below threshold
            )
        )
        db.commit()
    try:
        body = _get(slug)
        assert "New / few reviews yet" in body
        # No numeric rating in the identity sub-line.
        assert "★ 5.0" not in body
        ld = _jsonld(body)
        assert ld.get("aggregateRating") is None
    finally:
        _cleanup(slug)


# --- L4: full weekly hours table + overnight Midnight display + fallback copy ---


def test_hours_table_renders_overnight_close_as_midnight() -> None:
    suf = uuid4().hex[:8]
    slug = f"wp6-hours-{suf}"
    hours = {
        "monday": [{"open": "08:00", "close": "17:00"}],
        "friday": [{"open": "20:00", "close": "23:59"}],
        "saturday": [],
        "sunday": [],
    }
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"Hours Co {suf}",
                category="home_services",
                source="test-wp6",
                slug=slug,
                draft=False,
                is_active=True,
                verified=True,
                hours_structured=hours,
            )
        )
        db.commit()
    try:
        body = _get(slug)
        assert "Friday" in body
        # 23:59 clamp displays as Midnight, not 11:59.
        assert "Midnight" in body
        assert "23:59" not in body
    finally:
        _cleanup(slug)


def test_hours_fallback_copy_when_no_hours() -> None:
    suf = uuid4().hex[:8]
    slug = f"wp6-nohours-{suf}"
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"NoHours Co {suf}",
                category="home_services",
                source="test-wp6",
                slug=slug,
                draft=False,
                is_active=True,
                verified=True,
                hours_structured=None,
                hours=None,
            )
        )
        db.commit()
    try:
        body = _get(slug)
        assert "Hours not available" in body
    finally:
        _cleanup(slug)


# --- DL-4: review excerpt clamped to ~40 words ---


def test_review_excerpt_clamped_to_forty_words() -> None:
    suf = uuid4().hex[:8]
    slug = f"wp6-rev-{suf}"
    long_text = " ".join(f"word{i}" for i in range(80))
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"Wordy Co {suf}",
                category="home_services",
                source="test-wp6",
                slug=slug,
                draft=False,
                is_active=True,
                verified=True,
                google_review_snippets=[{"author": "A", "rating": 5, "text": long_text}],
            )
        )
        db.commit()
    try:
        body = _get(slug)
        assert "From Google reviews" in body
        assert "word39" in body  # 40th word (0-indexed) is included
        assert "word40" not in body  # 41st word is clamped off
        assert "…" in body
    finally:
        _cleanup(slug)


# --- DL-11: claim/lock CTA copy + no "menu" wording outside eat-drink ---


def test_claim_lock_copy_no_menu_outside_eat_drink() -> None:
    suf = uuid4().hex[:8]
    slug = f"wp6-claim-svc-{suf}"
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"Unclaimed Plumber {suf}",
                category="home_services",
                source="test-wp6",
                slug=slug,
                draft=False,
                is_active=True,
                verified=False,
                tier="free",
            )
        )
        db.commit()
    try:
        body = _get(slug)
        assert "Claim this listing to add photos, details, and offers." in body
        # No "menu" wording in the claim CTA for a non eat-drink listing
        # (the shared header legitimately contains "mega-menu" / "menu-btn").
        assert "your menu" not in body.lower()
        assert "and menu" not in body.lower()
    finally:
        _cleanup(slug)


# --- SEO: canonical + og + valid LocalBusiness JSON-LD ---


def test_seo_block_canonical_og_and_jsonld() -> None:
    suf = uuid4().hex[:8]
    slug = f"wp6-seo-{suf}"
    with SessionLocal() as db:
        db.add(
            Provider(
                provider_name=f"SEO Co {suf}",
                category="home_services",
                source="test-wp6",
                slug=slug,
                draft=False,
                is_active=True,
                verified=True,
                description="A trustworthy local shop serving Lake Havasu City.",
            )
        )
        db.commit()
    try:
        body = _get(slug)
        assert 'rel="canonical"' in body
        assert 'property="og:title"' in body
        assert 'property="og:url"' in body
        ld = _jsonld(body)  # parses -> valid JSON
        assert ld["@type"] == "LocalBusiness"
        assert ld["@context"] == "https://schema.org"
        assert f"SEO Co {suf}" in ld["name"]
    finally:
        _cleanup(slug)

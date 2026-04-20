"""Public /contribute form (Phase 5.4)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.contribution_store import create_contribution, update_contribution_status
from app.db.database import SessionLocal
from app.db.models import Contribution
from app.main import app
from app.schemas.contribution import ContributionCreate


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_contribute_renders_form(client: TestClient) -> None:
    r = client.get("/contribute")
    assert r.status_code == 200
    assert "Submit for review" in r.text
    assert 'name="entity_type"' in r.text
    assert 'action="/contribute"' in r.text


def test_get_contribute_submitted_shows_banner(client: TestClient) -> None:
    r = client.get("/contribute?submitted=1")
    assert r.status_code == 200
    assert "review queue" in r.text.lower()


def test_post_valid_provider_schedules_enrich(client: TestClient) -> None:
    with patch("app.api.routes.contribute.enrich_contribution") as m:
        r = client.post(
            "/contribute",
            data={
                "entity_type": "provider",
                "submission_name": "Contribute Test Gym",
                "submission_url": "https://contribute-test-gym.example/about",
                "category_hint": "fitness",
                "description": "A short description so reviewers have context.",
                "submitter_email": "",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "submitted=1" in (r.headers.get("location") or "")
    assert m.call_count == 1


def test_post_provider_missing_url_shows_error(client: TestClient) -> None:
    r = client.post(
        "/contribute",
        data={
            "entity_type": "provider",
            "submission_name": "No URL Gym",
            "submission_url": "",
            "description": "Has notes but URL required for provider.",
        },
    )
    assert r.status_code == 200
    assert "URL is required" in r.text or "submission_url" in r.text.lower()


def test_post_invalid_email(client: TestClient) -> None:
    r = client.post(
        "/contribute",
        data={
            "entity_type": "tip",
            "submission_name": "Bad email tip",
            "submission_url": "",
            "description": "Enough context here without a URL.",
            "submitter_email": "not-an-email",
        },
    )
    assert r.status_code == 200
    assert "email" in r.text.lower()


def test_post_duplicate_pending_url(client: TestClient) -> None:
    db = SessionLocal()
    try:
        create_contribution(
            db,
            ContributionCreate(
                entity_type="provider",
                submission_name="Dup URL Seed",
                submission_url="https://dup-url-phase54.example/",
                source="operator_backfill",
            ),
            submitter_ip_hash=None,
        )
    finally:
        db.close()
    r = client.post(
        "/contribute",
        data={
            "entity_type": "provider",
            "submission_name": "Dup URL Public",
            "submission_url": "https://dup-url-phase54.example",
            "description": "Trying to submit duplicate.",
        },
    )
    assert r.status_code == 200
    assert "already have this" in r.text.lower()


def test_post_duplicate_rejected_url_allowed(client: TestClient) -> None:
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="provider",
                submission_name="Rejected dup seed",
                submission_url="https://rejected-dup-phase54.example/",
                source="operator_backfill",
            ),
            submitter_ip_hash=None,
        )
        cid = row.id
        update_contribution_status(db, cid, "rejected", rejection_reason="spam")
    finally:
        db.close()
    with patch("app.api.routes.contribute.enrich_contribution"):
        r = client.post(
            "/contribute",
            data={
                "entity_type": "provider",
                "submission_name": "After reject resubmit",
                "submission_url": "https://rejected-dup-phase54.example/",
                "description": "Resubmission after rejection should be allowed.",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_post_name_only_rejected(client: TestClient) -> None:
    r = client.post(
        "/contribute",
        data={
            "entity_type": "tip",
            "submission_name": "Thin tip",
            "submission_url": "",
            "description": "",
        },
    )
    assert r.status_code == 200
    assert "description or a url" in r.text.lower() or "url" in r.text.lower()


def test_post_event_persists_datetime(client: TestClient) -> None:
    u = uuid.uuid4().hex[:8]
    name = f"Public Beach Cleanup {u}"
    with patch("app.api.routes.contribute.enrich_contribution"):
        r = client.post(
            "/contribute",
            data={
                "entity_type": "event",
                "submission_name": name,
                "submission_url": "https://beach-event.example",
                "description": "Community shoreline cleanup event description text.",
                "event_date": "2026-08-10",
                "event_start_time": "09:30",
                "event_end_time": "12:00",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    db = SessionLocal()
    try:
        row = db.execute(
            select(Contribution).where(Contribution.submission_name == name).order_by(Contribution.id.desc()).limit(1)
        ).scalar_one_or_none()
        assert row is not None
        assert row.entity_type == "event"
        assert row.event_date is not None
        assert str(row.event_date) == "2026-08-10"
        assert row.event_time_start is not None
        assert row.event_time_end is not None
    finally:
        db.close()


@patch("app.api.routes.contribute.is_rate_limit_disabled", return_value=False)
@patch("app.api.routes.contribute.get_remote_address", return_value="10.255.0.234")
def test_post_rate_limit_second_submission(_mock_ip: object, _mock_rl: object, client: TestClient) -> None:
    payload = {
        "entity_type": "program",
        "submission_name": "Rate limit program A",
        "submission_url": "https://rate-limit-a-phase54.example",
        "description": "Program description text long enough here.",
    }
    with patch("app.api.routes.contribute.enrich_contribution"):
        r1 = client.post("/contribute", data=payload, follow_redirects=False)
    assert r1.status_code == 302
    r2 = client.post(
        "/contribute",
        data={
            "entity_type": "program",
            "submission_name": "Rate limit program B",
            "submission_url": "https://rate-limit-b-phase54.example",
            "description": "Second program within one hour same IP.",
        },
    )
    assert r2.status_code == 429
    assert "hour" in r2.text.lower()

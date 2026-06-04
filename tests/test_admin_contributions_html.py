"""HTML admin routes for contribution review (Phase 5.3)."""

from __future__ import annotations

import os
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.contrib.approval_service import approve_contribution_as_provider
from app.db.contribution_store import create_contribution
from app.db.database import SessionLocal
from app.db.models import Contribution
from app.main import app
from app.schemas.contribution import ContributionCreate, ProviderApprovalFields


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(c: TestClient) -> None:
    os.environ["ADMIN_PASSWORD"] = "changeme"
    r = c.post("/admin/login", data={"password": "changeme"}, follow_redirects=False)
    assert r.status_code == 303


def test_list_requires_auth(client: TestClient) -> None:
    client.cookies.clear()
    r = client.get("/admin/contributions", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location", "").startswith("/admin/login")


def test_list_authenticated_ok(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.get("/admin/contributions")
    assert r.status_code == 200
    assert "Contributions" in r.text


def test_list_filter_pending_and_entity_type(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name="html filter tip",
                source="operator_backfill",
            ),
            None,
        )
        create_contribution(
            db,
            ContributionCreate(
                entity_type="provider",
                submission_name="html filter provider",
                submission_url="https://example.com/p",
                source="operator_backfill",
            ),
            None,
        )
    finally:
        db.close()
    r = client.get("/admin/contributions?status=pending&entity_type=provider")
    assert r.status_code == 200
    assert "html filter provider" in r.text
    assert "html filter tip" not in r.text


def test_detail_missing_404(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    r = client.get("/admin/contributions/999999999")
    assert r.status_code == 404


def test_detail_sections(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="provider",
                submission_name="Detail Section Gym",
                submission_url="https://example.com/ds",
                submission_notes="Note body",
                source="user_submission",
            ),
            submitter_ip_hash="abcdef0123456789",
        )
        cid = row.id
    finally:
        db.close()
    r = client.get(f"/admin/contributions/{cid}")
    assert r.status_code == 200
    assert "Submission" in r.text
    assert "Detail Section Gym" in r.text
    assert "abcdef01" in r.text
    assert "Actions" in r.text
    assert "/admin/api/contributions/" in r.text and "/enrich" in r.text


def test_approve_get_provider_prefill(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="provider",
                submission_name="Prefill Gym Name",
                submission_url="https://prefill.example",
                source="operator_backfill",
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    r = client.get(f"/admin/contributions/{cid}/approve")
    assert r.status_code == 200
    assert 'name="name"' in r.text
    assert "Prefill Gym Name" in r.text


def test_post_approve_provider_creates_row(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="provider",
                submission_name="Post Approve Gym",
                submission_url="https://postapprove.example",
                source="operator_backfill",
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    r = client.post(
        f"/admin/contributions/{cid}/approve",
        data={
            "name": "Post Approve Gym",
            "address": "100 Water St",
            "phone": "",
            "hours": "",
            "description": "Community gym description text long enough.",
            "website": "https://postapprove.example",
            "category": "fitness",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/admin/contributions?" in r.headers.get("location", "")
    db2 = SessionLocal()
    try:
        c2 = db2.get(Contribution, cid)
        assert c2 is not None
        assert c2.status == "approved"
        assert c2.created_provider_id is not None
    finally:
        db2.close()


def test_post_approve_tip_returns_400(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name="tip row",
                source="operator_backfill",
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    r = client.post(
        f"/admin/contributions/{cid}/approve",
        data={"name": "x", "description": "y", "category": "swim"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "Phase 5.3" in r.text or "not supported" in r.text


def test_reject_get_and_post(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name="reject flow",
                source="operator_backfill",
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    g = client.get(f"/admin/contributions/{cid}/reject")
    assert g.status_code == 200
    assert "rejection_reason" in g.text or "Reason" in g.text
    r = client.post(
        f"/admin/contributions/{cid}/reject",
        data={"rejection_reason": "spam", "review_notes": "nope"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db2 = SessionLocal()
    try:
        c2 = db2.get(Contribution, cid)
        assert c2 is not None
        assert c2.status == "rejected"
        assert c2.rejection_reason == "spam"
    finally:
        db2.close()


def test_needs_info_get_and_post(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name="needs row",
                source="operator_backfill",
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    g = client.get(f"/admin/contributions/{cid}/needs-info")
    assert g.status_code == 200
    r = client.post(
        f"/admin/contributions/{cid}/needs-info",
        data={"review_notes": "Please send more detail."},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db2 = SessionLocal()
    try:
        c2 = db2.get(Contribution, cid)
        assert c2 is not None
        assert c2.status == "needs_info"
    finally:
        db2.close()


def test_post_approve_already_approved_returns_400(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="provider",
                submission_name="Double Approve",
                submission_url="https://double.example",
                source="operator_backfill",
            ),
            None,
        )
        cid = row.id
        approve_contribution_as_provider(
            db,
            cid,
            ProviderApprovalFields(
                name="Double Approve",
                description="Enough text here for provider desc field optional.",
                website="https://double.example",
            ),
            "swim",
        )
    finally:
        db.close()
    r = client.post(
        f"/admin/contributions/{cid}/approve",
        data={
            "name": "Again",
            "description": "Enough text here for provider desc field optional.",
            "website": "https://double.example",
            "category": "swim",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_enrich_form_posts_to_api_path(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name="enrich html",
                source="operator_backfill",
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    page = client.get(f"/admin/contributions/{cid}")
    assert page.status_code == 200
    m = re.search(r'action="(/admin/api/contributions/\d+/enrich)"', page.text)
    assert m, page.text[:2000]
    path = m.group(1)
    with patch("app.api.routes.admin_contributions.enrich_contribution") as mock_e:
        r2 = client.post(path, follow_redirects=False)
    assert r2.status_code == 202
    assert mock_e.call_count == 1


def test_detail_renders_proposed_record_section(client: TestClient) -> None:
    """Scraped program findings must show their schedule (proposed_record),
    confidence, target entity, and source URL on the detail page — the legacy
    event_* columns are empty for them, so without this section the reviewer
    sees a finding with no days/times at all."""
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="program",
                submission_name="Proposed Record Studio",
                source_url="https://example.com/schedule-page",
                source="facebook_scrape",
                confidence=0.7,
                target_entity_id="00000000-0000-0000-0000-000000000001",
                proposed_record={
                    "title": "Sunrise Yoga Flow",
                    "description": "Gentle all-levels morning yoga flow class.",
                    "schedule_days": ["monday", "wednesday"],
                    "schedule_start_time": "06:30",
                    "schedule_end_time": "07:30",
                    "location_name": "Proposed Record Studio",
                    "provider_name": "Proposed Record Studio",
                    "cost": "$15/class",
                    "extra_worker_key": "kept-visible",
                },
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    r = client.get(f"/admin/contributions/{cid}")
    assert r.status_code == 200
    body = r.text
    assert "Proposed record (scraped)" in body
    assert "Sunrise Yoga Flow" in body
    assert "monday, wednesday" in body
    assert "06:30" in body and "07:30" in body
    assert "$15/class" in body
    # unknown worker-sent keys are not hidden
    assert "extra_worker_key" in body and "kept-visible" in body
    # confidence + target entity + clickable source URL
    assert "0.70" in body
    assert "00000000-0000-0000-0000-000000000001" in body
    assert 'href="https://example.com/schedule-page"' in body


def test_detail_no_proposed_record_section_when_absent(client: TestClient) -> None:
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="tip",
                submission_name="No Proposed Record Tip",
                source="user_submission",
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    r = client.get(f"/admin/contributions/{cid}")
    assert r.status_code == 200
    assert "Proposed record (scraped)" not in r.text


def test_approve_form_prefills_from_proposed_record(client: TestClient) -> None:
    """The program approve form must pre-fill from the scraped proposed_record —
    otherwise the operator submits the placeholder defaults (venue name as the
    class title, monday 09:00-17:00) and garbage lands on the venue."""
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="program",
                submission_name="Prefill Studio",
                source_url="https://example.com/prefill-schedule",
                source="facebook_scrape",
                confidence=0.8,
                target_entity_id="00000000-0000-0000-0000-000000000002",
                proposed_record={
                    "title": "Moonrise Pilates",
                    "description": "Evening reformer pilates class for all levels.",
                    "schedule_days": ["tuesday", "thursday"],
                    "schedule_start_time": "18:15",
                    "schedule_end_time": "19:15",
                    "location_name": "Prefill Studio Annex",
                    "provider_name": "Prefill Studio LLC",
                    "cost": "$22/class",
                    "contact_phone": "928-555-0000",
                    "tags": ["pilates", "fitness"],
                },
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    r = client.get(f"/admin/contributions/{cid}/approve")
    assert r.status_code == 200
    body = r.text
    assert 'value="Moonrise Pilates"' in body
    assert "Evening reformer pilates class for all levels." in body
    assert 'value="tuesday,thursday"' in body
    assert 'value="18:15"' in body
    assert 'value="19:15"' in body
    assert 'value="Prefill Studio Annex"' in body
    assert 'value="Prefill Studio LLC"' in body
    assert 'value="$22/class"' in body
    assert 'value="928-555-0000"' in body
    assert 'value="pilates,fitness"' in body
    # placeholder defaults must NOT remain
    assert 'value="monday"' not in body
    assert 'value="09:00"' not in body


def test_approve_form_falls_back_without_proposed_record(client: TestClient) -> None:
    """Legacy user submissions (no proposed_record) keep the old defaults."""
    client.cookies.clear()
    _login(client)
    db = SessionLocal()
    try:
        row = create_contribution(
            db,
            ContributionCreate(
                entity_type="program",
                submission_name="Legacy Program Submission",
                source="user_submission",
            ),
            None,
        )
        cid = row.id
    finally:
        db.close()
    r = client.get(f"/admin/contributions/{cid}/approve")
    assert r.status_code == 200
    body = r.text
    assert 'value="Legacy Program Submission"' in body
    assert 'value="monday"' in body
    assert 'value="09:00"' in body
    assert 'value="17:00"' in body

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

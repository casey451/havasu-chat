"""Tests for ``app.contrib.enrichment`` (mocked fetch + places)."""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy.orm import Session

from app.contrib.enrichment import enrich_contribution
from app.contrib.places_client import PlacesLookupResult
from app.contrib.url_fetcher import UrlFetchResult
from app.db.database import SessionLocal
from app.db.models import Contribution


def _factory() -> Session:
    return SessionLocal()


def test_provider_with_url_runs_both() -> None:
    with SessionLocal() as db:
        row = Contribution(
            entity_type="provider",
            submission_name="Test Gym",
            submission_url="https://example.com/gym",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        cid = row.id
    uf = UrlFetchResult(status="success", title="T", description="D")
    pl = PlacesLookupResult(
        status="success",
        place_id="places/X",
        display_name="Test Gym",
        raw_response={"places": [{"id": "places/X"}]},
    )
    with (
        patch("app.contrib.enrichment.fetch_url_metadata", return_value=uf),
        patch("app.contrib.enrichment.lookup_provider", return_value=pl),
    ):
        enrich_contribution(cid, _factory)
    with SessionLocal() as db:
        r = db.get(Contribution, cid)
        assert r is not None
        assert r.url_fetch_status == "success"
        assert r.url_title == "T"
        assert r.google_place_id == "places/X"
        assert isinstance(r.google_enriched_data, dict)
        db.delete(r)
        db.commit()


def test_provider_without_url_only_places() -> None:
    with SessionLocal() as db:
        row = Contribution(entity_type="provider", submission_name="Solo Name")
        db.add(row)
        db.commit()
        db.refresh(row)
        cid = row.id
    pl = PlacesLookupResult(status="no_match", raw_response={"places": []})
    with (
        patch("app.contrib.enrichment.fetch_url_metadata") as m_url,
        patch("app.contrib.enrichment.lookup_provider", return_value=pl),
    ):
        enrich_contribution(cid, _factory)
    m_url.assert_not_called()
    with SessionLocal() as db:
        r = db.get(Contribution, cid)
        assert r is not None
        assert r.url_fetch_status is None
        assert r.google_enriched_data == {"status": "no_match", "error": None}
        db.delete(r)
        db.commit()


def test_provider_failing_url_still_runs_places() -> None:
    with SessionLocal() as db:
        row = Contribution(
            entity_type="provider",
            submission_name="Bad URL Co",
            submission_url="https://bad.example/x",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        cid = row.id
    uf = UrlFetchResult(status="timeout", error_message="timeout")
    pl = PlacesLookupResult(status="success", place_id="places/Y", raw_response={"places": [{}]})
    with (
        patch("app.contrib.enrichment.fetch_url_metadata", return_value=uf),
        patch("app.contrib.enrichment.lookup_provider", return_value=pl),
    ):
        enrich_contribution(cid, _factory)
    with SessionLocal() as db:
        r = db.get(Contribution, cid)
        assert r is not None
        assert r.url_fetch_status == "timeout"
        assert r.google_place_id == "places/Y"
        db.delete(r)
        db.commit()


def test_program_only_url_fetch() -> None:
    with SessionLocal() as db:
        row = Contribution(
            entity_type="program",
            submission_name="Kids camp",
            submission_url="https://example.com/camp",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        cid = row.id
    uf = UrlFetchResult(status="success", title="Camp Page")
    with (
        patch("app.contrib.enrichment.fetch_url_metadata", return_value=uf) as m_url,
        patch("app.contrib.enrichment.lookup_provider") as m_pl,
    ):
        enrich_contribution(cid, _factory)
    m_url.assert_called_once()
    m_pl.assert_not_called()
    with SessionLocal() as db:
        r = db.get(Contribution, cid)
        assert r is not None
        assert r.url_title == "Camp Page"
        assert r.google_enriched_data is None
        db.delete(r)
        db.commit()


def test_tip_no_url_skips_both() -> None:
    with SessionLocal() as db:
        row = Contribution(entity_type="tip", submission_name="tip only")
        db.add(row)
        db.commit()
        db.refresh(row)
        cid = row.id
    with (
        patch("app.contrib.enrichment.fetch_url_metadata") as m_url,
        patch("app.contrib.enrichment.lookup_provider") as m_pl,
    ):
        enrich_contribution(cid, _factory)
    m_url.assert_not_called()
    m_pl.assert_not_called()
    with SessionLocal() as db:
        r = db.get(Contribution, cid)
        assert r is not None
        assert r.url_fetch_status is None
        assert r.google_enriched_data is None
        db.delete(r)
        db.commit()


def test_contribution_missing_no_crash() -> None:
    with (
        patch("app.contrib.enrichment.fetch_url_metadata") as m_url,
        patch("app.contrib.enrichment.lookup_provider") as m_pl,
    ):
        enrich_contribution(999_999_999, _factory)
    m_url.assert_not_called()
    m_pl.assert_not_called()

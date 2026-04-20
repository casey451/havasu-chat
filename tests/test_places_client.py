"""Tests for ``app.contrib.places_client`` (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from app.contrib.places_client import PLACES_FIELD_MASK, lookup_provider


def _mock_post_response(status: int, json_body: dict | None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    return r


@patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False)
@patch("app.contrib.places_client.httpx.Client")
def test_success_matching_name(mock_cls: MagicMock) -> None:
    body = {
        "places": [
            {
                "id": "places/ChIJabc",
                "displayName": {"text": "Altitude Trampoline Park", "languageCode": "en"},
                "formattedAddress": "100 Main St, Lake Havasu City, AZ",
                "internationalPhoneNumber": "+1 928-555-0100",
                "websiteUri": "https://example.com/altitude",
                "types": ["establishment", "point_of_interest"],
                "location": {"latitude": 34.5, "longitude": -114.3},
                "businessStatus": "OPERATIONAL",
                "regularOpeningHours": {"weekdayDescriptions": ["Mon: 10–8"]},
            }
        ]
    }
    inst = MagicMock()
    inst.post.return_value = _mock_post_response(200, body)
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = None
    mock_cls.return_value = inst
    r = lookup_provider("Altitude Trampoline Park")
    assert r.status == "success"
    assert r.place_id == "places/ChIJabc"
    assert r.phone == "+1 928-555-0100"
    assert r.raw_response is not None
    inst.post.assert_called_once()
    _, kwargs = inst.post.call_args
    assert kwargs["headers"]["X-Goog-FieldMask"] == PLACES_FIELD_MASK


@patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False)
@patch("app.contrib.places_client.httpx.Client")
def test_low_confidence_display_mismatch(mock_cls: MagicMock) -> None:
    body = {
        "places": [
            {
                "id": "places/X",
                "displayName": {"text": "Totally Unrelated Name XYZ", "languageCode": "en"},
                "formattedAddress": "Somewhere",
            }
        ]
    }
    inst = MagicMock()
    inst.post.return_value = _mock_post_response(200, body)
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = None
    mock_cls.return_value = inst
    r = lookup_provider("Altitude Trampoline Park")
    assert r.status == "low_confidence"
    assert r.place_id == "places/X"


@patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False)
@patch("app.contrib.places_client.httpx.Client")
def test_no_match_empty_places(mock_cls: MagicMock) -> None:
    inst = MagicMock()
    inst.post.return_value = _mock_post_response(200, {"places": []})
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = None
    mock_cls.return_value = inst
    r = lookup_provider("Nonexistent Place ZZZ")
    assert r.status == "no_match"


@patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False)
@patch("app.contrib.places_client.httpx.Client")
def test_api_403(mock_cls: MagicMock) -> None:
    inst = MagicMock()
    inst.post.return_value = _mock_post_response(403, {"error": {"code": 403, "message": "quota"}})
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = None
    mock_cls.return_value = inst
    r = lookup_provider("Any")
    assert r.status == "error"
    assert "403" in (r.error_message or "")


@patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False)
@patch("app.contrib.places_client.httpx.Client")
def test_timeout(mock_cls: MagicMock) -> None:
    inst = MagicMock()
    inst.post.side_effect = httpx.TimeoutException("t")
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = None
    mock_cls.return_value = inst
    r = lookup_provider("Any")
    assert r.status == "error"
    assert r.error_message == "timeout"


def test_missing_api_key_no_http() -> None:
    with patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": ""}):
        with patch("app.contrib.places_client.httpx.Client") as mock_cls:
            r = lookup_provider("Some Biz")
    assert r.status == "not_attempted"
    mock_cls.assert_not_called()


@patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False)
@patch("app.contrib.places_client.httpx.Client")
def test_http_error_json(mock_cls: MagicMock) -> None:
    inst = MagicMock()
    inst.post.return_value = _mock_post_response(500, {"error": "internal"})
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = None
    mock_cls.return_value = inst
    r = lookup_provider("X")
    assert r.status == "error"

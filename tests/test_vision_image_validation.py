"""Flyer image robustness (2026-06-25): validate before sending to the model.

The live VPS flyers step logged a burst of vision-API 400s ("Failed to load image")
when the gallery served a documentID that wasn't a raster image (HTML error page,
PDF, wrong content-type). These guards sniff the magic bytes and skip non-images —
no model call, no 400 — and pass the correct sniffed mime for real images.
"""

from __future__ import annotations

import json
from datetime import date

from app.contrib import lhc_parks_rec_calendar as prc
from app.contrib import senior_center_vision as scv
from app.contrib import vision_calendar as vc

TODAY = date(2026, 6, 15)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
GIF = b"GIF89a" + b"\x00" * 40
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 40
HTML = b"<!doctype html><html><body>404 Not Found</body></html>"
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n" + b"\x00" * 40


# --------------------------------------------------------------------------- #
# sniff_image_mime
# --------------------------------------------------------------------------- #
def test_sniff_recognises_supported_rasters() -> None:
    assert vc.sniff_image_mime(PNG) == "image/png"
    assert vc.sniff_image_mime(JPEG) == "image/jpeg"
    assert vc.sniff_image_mime(GIF) == "image/gif"
    assert vc.sniff_image_mime(WEBP) == "image/webp"


def test_sniff_rejects_non_images() -> None:
    assert vc.sniff_image_mime(HTML) is None
    assert vc.sniff_image_mime(PDF) is None
    assert vc.sniff_image_mime(b"") is None
    assert vc.sniff_image_mime(b"\x89PNG") is None  # too short to be sure


# --------------------------------------------------------------------------- #
# validate_flyer_image
# --------------------------------------------------------------------------- #
def test_validate_accepts_real_image_ignoring_mislabeled_content_type() -> None:
    # Server mislabels a real PNG as octet-stream; the magic-byte sniff wins.
    mime, reason = vc.validate_flyer_image(PNG, content_type="application/octet-stream")
    assert mime == "image/png"
    assert reason == "ok"


def test_validate_rejects_html_pdf_empty() -> None:
    assert vc.validate_flyer_image(HTML, content_type="text/html") == (None, "unsupported_type")
    assert vc.validate_flyer_image(PDF, content_type="application/pdf") == (None, "unsupported_type")
    assert vc.validate_flyer_image(b"", content_type=None) == (None, "empty")


def test_validate_rejects_oversize() -> None:
    big = PNG + b"\x00" * 100
    mime, reason = vc.validate_flyer_image(big, max_bytes=50)
    assert mime is None
    assert reason == "too_large"


# --------------------------------------------------------------------------- #
# Integration: parks flyers — non-image skipped, real image sent with right mime
# --------------------------------------------------------------------------- #
_FLYER_PAGE = (
    "<html><body>"
    '<img data-src="/ImageRepository/Document?documentID=901" alt="Pizza Party">'
    '<img data-src="/ImageRepository/Document?documentID=902" alt="Dodgeball Night">'
    "</body></html>"
)
_URL_IMG = "https://www.lhcaz.gov/ImageRepository/Document?documentID=901"
_URL_BAD = "https://www.lhcaz.gov/ImageRepository/Document?documentID=902"


def _fake_call_vision(calls: list[str]):
    def _fake(image_bytes, *, system_prompt, model=None, mime="image/png", openai_symbol=None):
        calls.append(mime)
        return json.dumps(
            {
                "events": [
                    {
                        "title": "Pizza Party",
                        "date": "2026-07-15",
                        "start_time": "17:00",
                        "confidence": 0.95,
                        "source_cell": "Pizza Party Jul 15 5pm",
                    }
                ]
            }
        )

    return _fake


def test_pull_flyers_skips_non_image_and_sends_real_image(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(vc, "call_vision", _fake_call_vision(calls))

    result = prc.pull_flyers(
        html=_FLYER_PAGE,
        today=TODAY,
        write_snapshot=False,
        max_flyers=2,
        image_bytes_by_url={
            _URL_IMG: (PNG, "image/png"),
            _URL_BAD: (HTML, "text/html"),  # 404 page masquerading as a flyer
        },
    )

    # The HTML payload is skipped before any model call; the real PNG is processed.
    assert result.skipped_non_image == 1
    assert len(result.records) == 1
    assert result.records[0].title == "Pizza Party"
    # Exactly one model call, and it carried the sniffed mime (not a hardcoded one).
    assert calls == ["image/png"]
    assert result.errors == []


def test_pull_flyers_passes_sniffed_mime_for_jpeg(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(vc, "call_vision", _fake_call_vision(calls))

    result = prc.pull_flyers(
        html='<html><img data-src="/ImageRepository/Document?documentID=901" alt="x"></html>',
        today=TODAY,
        write_snapshot=False,
        max_flyers=1,
        # Content-Type lies (png) but the bytes are JPEG -> sniff corrects it.
        image_bytes_by_url={_URL_IMG: (JPEG, "image/png")},
    )
    assert result.skipped_non_image == 0
    assert calls == ["image/jpeg"]


# --------------------------------------------------------------------------- #
# Integration: senior flyers — same guard on the LeadConnector CDN path
# --------------------------------------------------------------------------- #
def test_pull_senior_flyers_skips_non_image() -> None:
    cdn = "https://media.leadconnectorhq.com/flyer-1.png"
    page = f'<html><body><img src="{cdn}"></body></html>'
    result = scv.pull_senior_flyers(
        html=page,
        max_flyers=1,
        image_bytes_by_url={cdn: (HTML, "text/html")},
    )
    assert result.skipped_non_image == 1
    assert result.records == []
    assert result.errors == []


# --------------------------------------------------------------------------- #
# The skip count is visible in the dry-run reports.
# --------------------------------------------------------------------------- #
def test_parks_notes_surface_skipped_non_image() -> None:
    from scripts.parks_rec_calendar_pull import _notes

    res = prc.CalendarPullResult(records=[], skipped_non_image=3)
    line = next(n for n in _notes(prc.FLYER_SOURCE, res, []) if "skipped non-image" in n)
    assert "3" in line


def test_senior_notes_surface_skipped_non_image() -> None:
    from scripts.senior_flyers_pull import _notes

    res = scv.SeniorFlyerPullResult(records=[], skipped_non_image=2)
    line = next(n for n in _notes(res, []) if "skipped non-image" in n)
    assert "2" in line

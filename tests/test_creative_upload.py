"""C10 — ad-creative binary image upload (Railway volume).

Covers the storage helper (real-image validation, server-side safe filenames,
size cap) and the media route (serves a saved file, 404s on traversal/missing),
plus path-traversal hardening in ``resolve_media_path``.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.portal import creative_store


def _png_bytes(color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def upload_dir(tmp_path, monkeypatch) -> str:
    d = tmp_path / "creatives"
    monkeypatch.setenv("CREATIVE_UPLOAD_DIR", str(d))
    return str(d)


def test_save_creative_image_accepts_png(upload_dir) -> None:
    url = creative_store.save_creative_image(_png_bytes(), declared_mime="image/png")
    assert url.startswith("/media/creatives/")
    name = url.rsplit("/", 1)[-1]
    assert creative_store._SAFE_NAME.match(name)
    assert (creative_store.creative_upload_dir() / name).is_file()


def test_save_creative_image_rejects_non_image(upload_dir) -> None:
    with pytest.raises(creative_store.CreativeImageError):
        creative_store.save_creative_image(b"this is not an image", declared_mime="image/png")


def test_save_creative_image_rejects_oversize(upload_dir) -> None:
    big = b"\x00" * (creative_store.MAX_IMAGE_BYTES + 1)
    with pytest.raises(creative_store.CreativeImageError):
        creative_store.save_creative_image(big, declared_mime="image/png")


def test_save_creative_image_rejects_bad_declared_mime(upload_dir) -> None:
    with pytest.raises(creative_store.CreativeImageError):
        creative_store.save_creative_image(_png_bytes(), declared_mime="application/pdf")


def test_resolve_media_path_blocks_traversal_and_unknown(upload_dir) -> None:
    assert creative_store.resolve_media_path("../secret.png") is None
    assert creative_store.resolve_media_path("evil.txt") is None
    assert creative_store.resolve_media_path("deadbeef.png") is None  # well-formed but absent


def test_media_route_serves_and_404s(upload_dir) -> None:
    url = creative_store.save_creative_image(_png_bytes(), declared_mime="image/png")
    client = TestClient(app)

    ok = client.get(url)
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("image/")

    missing = client.get("/media/creatives/00000000000000000000000000000000.png")
    assert missing.status_code == 404
    # A non-allow-listed name never resolves to a file.
    assert client.get("/media/creatives/evil.txt").status_code == 404

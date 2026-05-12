"""Phase 2B.1 — R2 client lazy init + URL join + upload headers."""

from __future__ import annotations

import pytest

import app.photos.r2_client as r2_mod


def test_get_r2_client_raises_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    r2_mod.reset_r2_client_for_tests()
    for k in (
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT_URL",
        "R2_BUCKET_NAME",
        "R2_PUBLIC_URL_BASE",
    ):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="R2 is not configured"):
        r2_mod.get_r2_client()
    r2_mod.reset_r2_client_for_tests()


def test_get_r2_client_uses_boto3_with_r2_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r2_mod.reset_r2_client_for_tests()
    calls: dict = {}

    def fake_client(*args, **kwargs):
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("boto3.client", fake_client)
    c = r2_mod.get_r2_client()
    assert c is not None
    assert calls["kwargs"]["endpoint_url"] == "https://test.r2.cloudflarestorage.com"
    assert calls["kwargs"]["region_name"] == "auto"
    r2_mod.reset_r2_client_for_tests()


def test_upload_bytes_put_object_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    r2_mod.reset_r2_client_for_tests()
    put: list[dict] = []

    class _Fake:
        def put_object(self, **kwargs):
            put.append(kwargs)

    monkeypatch.setattr(r2_mod, "get_r2_client", lambda: _Fake())
    monkeypatch.setenv("R2_BUCKET_NAME", "mybucket")
    url = r2_mod.upload_bytes("k1", b"ab", "image/jpeg")
    assert put[0]["Bucket"] == "mybucket"
    assert put[0]["Key"] == "k1"
    assert put[0]["Body"] == b"ab"
    assert put[0]["ContentType"] == "image/jpeg"
    assert "immutable" in put[0]["CacheControl"]
    assert url.endswith("/k1")
    r2_mod.reset_r2_client_for_tests()


@pytest.mark.parametrize(
    ("base", "key", "expect"),
    [
        ("https://pub-test.r2.dev", "a/b.webp", "https://pub-test.r2.dev/a/b.webp"),
        ("https://pub-test.r2.dev/", "/a/b.webp", "https://pub-test.r2.dev/a/b.webp"),
    ],
)
def test_build_public_url_joins(base: str, key: str, expect: str, monkeypatch) -> None:
    monkeypatch.setenv("R2_PUBLIC_URL_BASE", base)
    assert r2_mod.build_public_url(key) == expect

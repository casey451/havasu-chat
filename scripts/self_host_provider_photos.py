"""One-time self-host backfill for Provider Google photos.

Downloads provider photo URLs/refs, writes image files under ``app/static``,
then rewrites ``Provider.google_photo_urls`` to local ``/static/...`` URLs.

Usage:
  python -m scripts.self_host_provider_photos --dry-run
  python -m scripts.self_host_provider_photos --apply
"""

from __future__ import annotations

import argparse
import hashlib
import mimetypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.providers.photo_urls import resolve_photo_ref  # noqa: E402

_IMAGE_CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@dataclass(frozen=True)
class DownloadedImage:
    source_url: str
    content_type: str
    extension: str
    file_hash: str
    payload: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.payload)

    @property
    def filename(self) -> str:
        return f"{self.file_hash}{self.extension}"


def _iter_photo_inputs(provider: Provider) -> Iterable[str]:
    urls = provider.google_photo_urls
    refs = provider.google_photo_refs
    candidates = urls if isinstance(urls, list) and urls else refs
    if not isinstance(candidates, list):
        return ()
    out: list[str] = []
    for raw in candidates:
        if not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _resolve_source_url(candidate: str) -> str | None:
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    if candidate.startswith("places/") and "/photos/" in candidate:
        return resolve_photo_ref(candidate)
    return None


def _is_localized_photo_url(candidate: str | None, *, local_prefix: str) -> bool:
    return isinstance(candidate, str) and candidate.strip().startswith(f"{local_prefix}/")


def _infer_extension(source_url: str, content_type: str) -> str:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct in _IMAGE_CONTENT_TYPE_TO_EXT:
        return _IMAGE_CONTENT_TYPE_TO_EXT[ct]
    parsed = urlparse(source_url)
    guessed_from_path = Path(parsed.path).suffix.lower()
    if guessed_from_path in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if guessed_from_path == ".jpeg" else guessed_from_path
    guessed_from_mime = mimetypes.guess_extension(ct or "")
    if guessed_from_mime:
        return ".jpg" if guessed_from_mime == ".jpe" else guessed_from_mime
    return ".jpg"


def _download_image(client: httpx.Client, source_url: str) -> DownloadedImage | None:
    try:
        response = client.get(source_url, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    content_type = response.headers.get("content-type", "")
    if not content_type.lower().startswith("image/"):
        return None
    payload = response.content
    if not payload:
        return None
    digest = hashlib.sha256(payload).hexdigest()
    return DownloadedImage(
        source_url=source_url,
        content_type=content_type,
        extension=_infer_extension(source_url, content_type),
        file_hash=digest,
        payload=payload,
    )


def _remaining_key_url_count(db) -> int:
    rows = db.execute(select(Provider.google_photo_urls)).all()
    count = 0
    for (urls,) in rows:
        if not isinstance(urls, list):
            continue
        for url in urls:
            if isinstance(url, str) and "key=" in url:
                count += 1
    return count


def run(*, apply: bool, max_static_mb: float) -> int:
    max_static_bytes = int(max_static_mb * 1024 * 1024)
    static_root = Path("/data/biz-photos")
    local_prefix = "/static/biz-photos"

    provider_sources: dict[str, list[str | None]] = {}
    source_urls: set[str] = set()
    localized_skipped = 0

    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(Provider).where(
                    (Provider.google_photo_refs.isnot(None))
                    | (Provider.google_photo_urls.isnot(None))
                )
            ).scalars()
        )
        for provider in rows:
            current_urls = provider.google_photo_urls
            current_nonempty_urls = [
                item.strip()
                for item in current_urls
                if isinstance(item, str) and item.strip()
            ] if isinstance(current_urls, list) else []
            if (
                current_nonempty_urls
                and all(
                    _is_localized_photo_url(item, local_prefix=local_prefix)
                    for item in current_nonempty_urls
                )
            ):
                localized_skipped += 1
                continue
            resolved_for_provider: list[str | None] = []
            for candidate in _iter_photo_inputs(provider):
                source_url = _resolve_source_url(candidate)
                if not source_url:
                    continue
                resolved_for_provider.append(source_url)
                source_urls.add(source_url)
                # One image per provider keeps this one-time backfill bounded.
                break
            if resolved_for_provider:
                provider_sources[provider.id] = resolved_for_provider

    downloaded_by_source: dict[str, DownloadedImage] = {}
    with httpx.Client(timeout=20.0) as client:
        for idx, source_url in enumerate(sorted(source_urls), start=1):
            downloaded = _download_image(client, source_url)
            if downloaded:
                downloaded_by_source[source_url] = downloaded
            if idx % 100 == 0:
                print(
                    f"Progress: scanned={idx}/{len(source_urls)} "
                    f"downloaded={len(downloaded_by_source)}"
                )

    unique_hashes: dict[str, DownloadedImage] = {}
    for downloaded in downloaded_by_source.values():
        unique_hashes.setdefault(downloaded.file_hash, downloaded)
    total_bytes = sum(img.size_bytes for img in unique_hashes.values())

    print(
        "Photo measure: "
        f"providers_with_candidates={len(provider_sources)} "
        f"already_localized={localized_skipped} "
        f"source_urls={len(source_urls)} "
        f"downloaded={len(downloaded_by_source)} "
        f"unique_files={len(unique_hashes)} "
        f"total_bytes={total_bytes}"
    )

    if not apply:
        return 0

    if total_bytes > max_static_bytes:
        print(
            "ABORT: measured photo payload exceeds static threshold "
            f"({total_bytes} bytes > {max_static_bytes} bytes)."
        )
        print("Recommendation: use Railway persistent volume or object storage.")
        return 2

    static_root.mkdir(parents=True, exist_ok=True)
    hash_to_local_url: dict[str, str] = {}
    for file_hash, downloaded in unique_hashes.items():
        local_path = static_root / downloaded.filename
        if not local_path.exists():
            local_path.write_bytes(downloaded.payload)
        hash_to_local_url[file_hash] = f"{local_prefix}/{downloaded.filename}"

    providers_updated = 0
    with SessionLocal() as db:
        for provider_id, resolved_sources in provider_sources.items():
            provider = db.get(Provider, provider_id)
            if provider is None:
                continue
            rewritten: list[str | None] = []
            for source in resolved_sources:
                if not source:
                    continue
                downloaded = downloaded_by_source.get(source)
                if not downloaded:
                    continue
                rewritten.append(hash_to_local_url[downloaded.file_hash])
            if rewritten and any(
                _is_localized_photo_url(item, local_prefix=local_prefix)
                for item in rewritten
                if isinstance(item, str)
            ):
                provider.google_photo_urls = rewritten
            providers_updated += 1
        db.commit()

        remaining = _remaining_key_url_count(db)
        print(
            "Apply complete: "
            f"providers_updated={providers_updated} "
            f"already_localized={localized_skipped} "
            f"photos_saved={len(unique_hashes)} "
            f"total_bytes={total_bytes} "
            f"remaining_key_urls={remaining}"
        )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--dry-run", action="store_true", help="Measure only (default).")
    mode.add_argument("--apply", action="store_true", help="Persist files and DB rewrites.")
    parser.add_argument(
        "--max-static-mb",
        type=float,
        default=512.0,
        help="Max payload size for static-file strategy before aborting.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return run(apply=bool(args.apply), max_static_mb=args.max_static_mb)


if __name__ == "__main__":
    raise SystemExit(main())

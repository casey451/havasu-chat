"""Pillow pipeline + BackgroundTasks orchestrator for owner photo uploads."""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageOps

from app.core.background import with_retry
from app.db.database import SessionLocal
from app.db.models import Entity, Photo
from app.photos.r2_client import upload_bytes

logger = logging.getLogger(__name__)

_PROCESS_OK = object()

MIN_EDGE = 128
_VARIANT_SIZES = {
    "thumbnail": (256, 256),
    "medium": (512, 512),
    "hero": (1280, 720),
}
_WEBP_Q = 82
_JPEG_Q = 85

_FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

_EXT_CT = {"webp": "image/webp", "jpeg": "image/jpeg"}


@dataclass(frozen=True)
class ProcessingError:
    code: str


def decode_and_validate(
    content: bytes, *, declared_mime: str
) -> Image.Image | ProcessingError:
    """Decode bytes with Pillow; enforce MIME sniff + minimum dimensions."""
    dm = declared_mime.strip().lower()
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except Exception:
        return ProcessingError("decode_failed")
    fmt = (img.format or "").upper()
    if fmt not in _FORMAT_TO_MIME:
        return ProcessingError("unsafe_mime")
    if _FORMAT_TO_MIME[fmt] != dm:
        return ProcessingError("unsafe_mime")
    if img.size[0] < MIN_EDGE or img.size[1] < MIN_EDGE:
        return ProcessingError("too_small")
    gray = img.convert("L")
    ex = gray.getextrema()
    if ex[0] == ex[1] == 0 or ex[0] == ex[1] == 255:
        return ProcessingError("decode_failed")
    return img


def strip_exif(img: Image.Image) -> Image.Image | ProcessingError:
    """Re-encode to drop EXIF; normalize to RGB baseline."""
    try:
        if img.mode in ("RGBA", "P"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            rgb = bg
        elif img.mode != "RGB":
            rgb = img.convert("RGB")
        else:
            rgb = img
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        return Image.open(buf).copy()
    except Exception:
        return ProcessingError("exif_strip_failed")


def compute_hash(img: Image.Image) -> str:
    """SHA-256 of post-strip RGB pixel bytes."""
    rgb = img.convert("RGB")
    return hashlib.sha256(rgb.tobytes()).hexdigest()


def generate_variants(
    img: Image.Image,
) -> dict[str, dict[str, bytes]] | ProcessingError:
    """Three variants × WebP + JPEG (center-crop ``ImageOps.fit``)."""
    base = img.convert("RGB")
    out: dict[str, dict[str, bytes]] = {}
    try:
        for name, size in _VARIANT_SIZES.items():
            fitted = ImageOps.fit(
                base, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
            )
            wbuf = io.BytesIO()
            fitted.save(wbuf, format="WEBP", quality=_WEBP_Q, method=6)
            jbuf = io.BytesIO()
            fitted.save(jbuf, format="JPEG", quality=_JPEG_Q, optimize=True)
            out[name] = {"webp": wbuf.getvalue(), "jpeg": jbuf.getvalue()}
        return out
    except Exception:
        return ProcessingError("decode_failed")


def upload_all_variants(
    storage_key_prefix: str, variants: dict[str, dict[str, bytes]]
) -> dict[str, dict[str, str]]:
    """Upload each variant object; return nested public URL map."""
    urls: dict[str, dict[str, str]] = {}
    for vname, fmts in variants.items():
        urls[vname] = {}
        for ext, body in fmts.items():
            key = f"{storage_key_prefix}{vname}.{ext}"
            urls[vname][ext] = upload_bytes(key, body, _EXT_CT[ext])
    return urls


def finalize_photo_row(
    db: Any,
    row: Photo,
    *,
    variants_urls: dict[str, dict[str, str]],
    width_px: int,
    height_px: int,
    file_size_bytes: int,
    image_hash: str,
    storage_key_prefix: str,
) -> None:
    """Populate URLs + dimensions + hash; caller sets ``status='live'``."""
    row.storage_key = storage_key_prefix
    row.image_hash = image_hash
    row.width_px = width_px
    row.height_px = height_px
    row.file_size_bytes = file_size_bytes
    row.thumbnail_url = variants_urls["thumbnail"]["webp"]
    row.medium_url = variants_urls["medium"]["webp"]
    row.hero_url = variants_urls["hero"]["webp"]
    row.cdn_url = variants_urls["medium"]["webp"]


def _flag_row(db: Any, row: Photo, code: str) -> None:
    row.status = "flagged"
    row.processing_error = code
    db.add(row)
    db.commit()


def _process_impl(photo_id: str, content: bytes, declared_mime: str) -> None:
    with SessionLocal() as db:
        row = db.get(Photo, photo_id)
        if row is None:
            return
        if row.status == "live":
            logger.warning(
                "process_uploaded_photo: skip already live photo_id=%s", photo_id
            )
            return
        if row.status != "uploading":
            return

        img = decode_and_validate(content, declared_mime=declared_mime)
        if isinstance(img, ProcessingError):
            _flag_row(db, row, img.code)
            return

        stripped = strip_exif(img)
        if isinstance(stripped, ProcessingError):
            _flag_row(db, row, stripped.code)
            return

        h = compute_hash(stripped)
        ent = db.get(Entity, row.entity_id)
        if ent is None:
            _flag_row(db, row, "decode_failed")
            return

        dup = (
            db.query(Photo)
            .filter(
                Photo.entity_id == row.entity_id,
                Photo.image_hash == h,
                Photo.status == "live",
                Photo.id != row.id,
            )
            .first()
        )
        if dup is not None:
            _flag_row(db, row, "duplicate")
            return

        prefix = f"photos/{ent.entity_type}/{row.entity_id}/{row.id}/"
        variants = generate_variants(stripped)
        if isinstance(variants, ProcessingError):
            _flag_row(db, row, variants.code)
            return

        total_size = sum(len(b) for fmts in variants.values() for b in fmts.values())
        rgb = stripped.convert("RGB")
        w_px, h_px = rgb.size

        try:
            url_map = upload_all_variants(prefix, variants)
        except Exception:
            logger.exception("R2 upload failed photo_id=%s", photo_id)
            db.rollback()
            return

        row = db.get(Photo, photo_id)
        if row is None or row.status != "uploading":
            return

        finalize_photo_row(
            db,
            row,
            variants_urls=url_map,
            width_px=w_px,
            height_px=h_px,
            file_size_bytes=total_size,
            image_hash=h,
            storage_key_prefix=prefix,
        )
        row.status = "live"
        row.processing_error = None
        db.add(row)
        db.commit()


def _flag_uploading_as_decode_failed(photo_id: str) -> None:
    try:
        with SessionLocal() as db:
            row = db.get(Photo, photo_id)
            if row is not None and row.status == "uploading":
                row.status = "flagged"
                row.processing_error = "decode_failed"
                db.add(row)
                db.commit()
    except Exception:
        logger.exception("process_uploaded_photo: failed to flag photo_id=%s", photo_id)


def process_uploaded_photo(photo_id: str, content: bytes, declared_mime: str) -> None:
    """BackgroundTasks entry: run pipeline; flag row on handled errors."""

    def _attempt() -> object:
        _process_impl(photo_id, content, declared_mime)
        return _PROCESS_OK

    try:
        if with_retry(_attempt) is None:
            logger.error(
                "process_uploaded_photo: retry exhaustion photo_id=%s", photo_id
            )
            _flag_uploading_as_decode_failed(photo_id)
    except Exception:
        logger.exception("process_uploaded_photo: unexpected error photo_id=%s", photo_id)
        _flag_uploading_as_decode_failed(photo_id)

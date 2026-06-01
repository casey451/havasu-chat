"""Internal AZCC captcha OCR helper (feature-flag gated, default off).

pytesseract is imported lazily inside :func:`solve_captcha_image` so importing
this module never requires the Tesseract binary on PATH.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re

logger = logging.getLogger(__name__)

_TESSERACT_TRUTHY = frozenset({"1", "true", "yes"})
_ALNUM_6 = re.compile(r"^[A-Za-z0-9]{6}$")
_TESSERACT_CONFIG = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def is_tesseract_enabled() -> bool:
    """True iff AZCC_TESSERACT_ENABLED is set to 1/true/yes (case-insensitive)."""
    val = (os.getenv("AZCC_TESSERACT_ENABLED") or "").strip().lower()
    return val in _TESSERACT_TRUTHY


def get_max_retries() -> int:
    """Read AZCC_TESSERACT_MAX_RETRIES env var; default 3; hard cap 5."""
    raw = (os.getenv("AZCC_TESSERACT_MAX_RETRIES") or "").strip()
    try:
        n = int(raw) if raw else 3
    except ValueError:
        n = 3
    return max(1, min(n, 5))


def solve_captcha_image(b64_data_url: str) -> str | None:
    """Decode a base64 data URL, run OCR with preprocessing, return guess or None."""
    if not b64_data_url:
        return None

    b64_part = b64_data_url.split(",", 1)[1] if "," in b64_data_url else b64_data_url
    try:
        raw = base64.b64decode(b64_part)
    except Exception:
        return None

    try:
        from PIL import Image, ImageFilter
    except ImportError:
        logger.warning("azcc_captcha_solver.pil_missing")
        return None

    try:
        img = Image.open(io.BytesIO(raw))
    except Exception:
        return None

    grey = img.convert("L")
    thresholded = grey.point(lambda p: 255 if p > 160 else 0)
    processed = thresholded.filter(ImageFilter.MedianFilter(size=3))

    try:
        import pytesseract
    except ImportError:
        logger.info("azcc_captcha_solver.binary_missing")
        return None

    try:
        raw_guess = pytesseract.image_to_string(processed, config=_TESSERACT_CONFIG)
    except Exception:
        logger.info("azcc_captcha_solver.binary_missing")
        return None

    guess = "".join(raw_guess.split())
    valid = bool(_ALNUM_6.fullmatch(guess))
    logger.info(
        "azcc_captcha_solver.ocr_ran",
        extra={"len": len(guess), "valid": valid},
    )
    return guess if valid else None

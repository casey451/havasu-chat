"""Email + token helpers — normalization, hashing, validation."""

from __future__ import annotations

import hashlib
import re
import secrets

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(raw: str) -> str:
    return raw.strip().lower()


def is_valid_email(email: str) -> bool:
    # Lightweight validation — Resend will reject malformed addresses at send
    # time. We just block obvious garbage at the request-link step.
    if len(email) > 320:
        return False
    return bool(_EMAIL_RE.match(email))


def generate_magic_link_token() -> tuple[str, str]:
    """Return (plaintext_token, sha256_hex_hash)."""
    plaintext = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return plaintext, hashed


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def hash_request_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def hash_optional_fingerprint(value: str | None) -> str | None:
    """SHA-256 hex of a string (e.g. User-Agent); None if missing."""
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

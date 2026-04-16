from __future__ import annotations

import os

from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

load_dotenv()

COOKIE_NAME = "admin_session"
MAX_AGE_SECONDS = 86400  # 24 hours


def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("ADMIN_PASSWORD", "changeme")
    return URLSafeTimedSerializer(secret, salt="havasu-admin-session")


def sign_admin_cookie() -> str:
    return _serializer().dumps({"ok": True})


def verify_admin_cookie(value: str | None) -> bool:
    if not value:
        return False
    try:
        data = _serializer().loads(value, max_age=MAX_AGE_SECONDS)
        return data.get("ok") is True
    except (BadSignature, SignatureExpired):
        return False


def admin_password_ok(password: str) -> bool:
    return password == os.getenv("ADMIN_PASSWORD", "changeme")

"""Magic-link email sender — Resend in prod, log-only in dev.

AUTH_DEV_MODE env var (truthy values: '1', 'true', 'yes', 'on' — case-
insensitive, same convention as RATE_LIMIT_DISABLED at app/core/rate_limit.py:17)
controls behavior:

- AUTH_DEV_MODE truthy → skip the Resend API call entirely; log the magic-link
  URL at INFO level so dev can copy-paste it.
- AUTH_DEV_MODE falsy → POST to Resend's /emails endpoint with the rendered
  email body. Failures bubble up to the route handler, which 502s with a
  generic 'couldn't send email; please try again' message.

Env vars required for prod:
- RESEND_API_KEY — the secret API key from resend.com.
- RESEND_FROM_ADDRESS — verified sender (e.g., 'Hava <noreply@example.com>').
- AUTH_MAGIC_LINK_BASE_URL — public origin to embed in the link
  (e.g., 'https://havasu-chat-production.up.railway.app').

Optional:
- AUTH_DEV_EMAIL_ALLOWLIST — comma-separated list of emails that bypass
  production rate limits for test recipients (design memo §9).
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_DEV_MODE_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _dev_mode_enabled() -> bool:
    # Never enable dev mode in prod regardless of AUTH_DEV_MODE — dev mode skips
    # the real Resend send and logs the plaintext magic-link token at INFO.
    if (os.environ.get("RAILWAY_ENVIRONMENT") or "").strip():
        return False
    v = (os.environ.get("AUTH_DEV_MODE") or "").strip().lower()
    return v in _DEV_MODE_TRUTHY


def _build_magic_link_url(token_plaintext: str, *, next_path: str | None = None) -> str:
    from urllib.parse import urlencode

    base = (os.environ.get("AUTH_MAGIC_LINK_BASE_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("AUTH_MAGIC_LINK_BASE_URL not set")
    params: dict[str, str] = {"token": token_plaintext}
    if next_path:
        params["next"] = next_path
    return f"{base}/auth/callback?{urlencode(params)}"


def _render_email_body(magic_link_url: str) -> tuple[str, str]:
    """Return (html_body, text_body)."""
    text = (
        "Sign in to Havasu Chat\n\n"
        f"Click here to sign in: {magic_link_url}\n\n"
        "This link expires in 15 minutes.\n"
        "If you didn't request this, you can safely ignore this email.\n"
    )
    html = (
        "<!DOCTYPE html><html><body>"
        "<p>Sign in to <strong>Havasu Chat</strong>:</p>"
        f'<p><a href="{magic_link_url}">Click here to sign in</a></p>'
        "<p>This link expires in 15 minutes.</p>"
        "<p>If you didn't request this, you can safely ignore this email.</p>"
        "</body></html>"
    )
    return html, text


def send_magic_link(email: str, token_plaintext: str, *, next_path: str | None = None) -> None:
    """Send the magic-link email (or log it in dev mode).

    Raises RuntimeError on configuration error (missing env vars) and
    httpx.HTTPError on Resend API failure. Route handlers catch + return
    a generic 502.
    """
    url = _build_magic_link_url(token_plaintext, next_path=next_path)

    if _dev_mode_enabled():
        logger.info(
            "AUTH_DEV_MODE: skipping Resend send — magic link for %s: %s",
            email,
            url,
        )
        return

    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("RESEND_FROM_ADDRESS") or "").strip()
    if not api_key or not from_addr:
        raise RuntimeError("RESEND_API_KEY and RESEND_FROM_ADDRESS must be set in prod")

    html, text = _render_email_body(url)
    payload = {
        "from": from_addr,
        "to": [email],
        "subject": "Sign in to Havasu Chat",
        "html": html,
        "text": text,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=10.0) as client:
        response = client.post(_RESEND_API_URL, json=payload, headers=headers)
        response.raise_for_status()


def send_alert_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> None:
    """Send a Phase 8a alert email (or log it in dev mode).

    Mirrors ``send_magic_link``'s dev/prod posture:
    - ``AUTH_DEV_MODE`` truthy → skip Resend, log subject + first 200 chars
      of text body at INFO level.
    - Otherwise POST to Resend's /emails endpoint with the pre-rendered
      html + text bodies (rendered by ``app.alerts.render.render_alert_email``).

    Raises ``RuntimeError`` if RESEND_API_KEY / RESEND_FROM_ADDRESS are
    unset in prod, and ``httpx.HTTPError`` on Resend API failure. The
    dispatcher (``app.alerts.dispatcher.dispatch_alerts``) catches both
    and records ``delivery_status='failed'``.
    """
    if _dev_mode_enabled():
        logger.info(
            "AUTH_DEV_MODE: skipping Resend send — alert email for %s: %s | %s",
            to_email,
            subject,
            (text_body or "")[:200],
        )
        return

    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("RESEND_FROM_ADDRESS") or "").strip()
    if not api_key or not from_addr:
        raise RuntimeError("RESEND_API_KEY and RESEND_FROM_ADDRESS must be set in prod")

    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=10.0) as client:
        response = client.post(_RESEND_API_URL, json=payload, headers=headers)
        response.raise_for_status()

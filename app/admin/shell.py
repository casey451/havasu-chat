"""Shared shell + helpers for the Phase 5 inline-HTML admin pages.

Before this module, each ``app/admin/*_html.py`` re-declared its own ``_esc``,
timestamp formatter, and a ~60-line ``_nav_shell`` with a copy-pasted ``<head>``
+ ``<style>`` block (audit 2026-07-01). They had drifted only cosmetically
(``.wrap`` max-width, a couple of margins) but the boilerplate was the bug-prone
part — a fix to the escaping or the head had to be made in eight places.

``admin_shell(title, inner, ...)`` is the one skeleton; ``esc`` /
``fmt_compact_ts`` / ``fmt_dt`` are the two shared formatters the pages used.
The structural CSS lives in ``_BASE_CSS`` (``.wrap`` width parameterized);
page-specific rules (pills, buttons, forms, window pickers) are passed via
``css``. ``extra_head`` carries per-page ``<head>`` additions (e.g. the jobs
auto-refresh meta).

NB: the Lake Ink & Brass skin (``lake_admin.css`` + ``noindex`` +
``data-redesign``) is still injected by ``AdminLakeSkinMiddleware`` in
``app/main.py`` — it is the single injection point shared by all three admin
rendering families (these inline pages, the Jinja ``.d-admin`` templates that
extend ``base_lake.html``, and the CSS-var ``admin_portal``). Folding it in here
would only cover the inline family, so the middleware stays.
"""

from __future__ import annotations

import html
from datetime import datetime

from app.admin.nav_html import admin_phase5_nav_html


def esc(s: str | None) -> str:
    """HTML-escape (quotes included) with ``None`` → empty string."""
    return html.escape(s or "", quote=True)


def fmt_compact_ts(dt: datetime | None) -> str:
    """Compact local-ish timestamp: ``Jun 5, 3:04pm`` (``—`` when null)."""
    if dt is None:
        return "—"
    h24 = dt.hour
    h12 = h24 % 12 or 12
    ampm = "am" if h24 < 12 else "pm"
    return f"{dt.strftime('%b')} {dt.day}, {h12}:{dt.minute:02d}{ampm}"


def fmt_dt(value: datetime | None) -> str:
    """Long timestamp: ``Jun 05, 2026 03:04 PM`` (tz-stripped; ``—`` when null)."""
    if not value:
        return "—"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%b %d, %Y %I:%M %p")


# Structural CSS shared by every inline admin page. Page-specific rules (pills,
# buttons, forms, window pickers, mono/number cells) are appended after this via
# the ``css`` argument, so a page can also override a base rule if it must.
_BASE_CSS = """    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; margin: 0; padding: 16px; background: #fff; color: #212529;
      line-height: 1.45; padding-bottom: 48px; }
    .wrap { max-width: __MAX_WIDTH__; margin: 0 auto; }
    h1 { font-size: 1.35rem; margin: 0 0 8px; }
    h2 { font-size: 1.05rem; margin: 28px 0 10px; color: #343a40; }
    .sub { color: #6c757d; font-size: 0.9rem; margin-bottom: 14px; }
    .nav { margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    .nav a { color: #0d6efd; font-weight: 600; text-decoration: none; }
    .nav a:hover { text-decoration: underline; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-bottom: 12px; }
    th, td { border: 1px solid #dee2e6; padding: 8px 10px; text-align: left; vertical-align: top; }
    th { background: #f8f9fa; font-weight: 600; }
    tbody tr:nth-child(even) { background: #fcfcfc; }
    .empty { color: #6c757d; padding: 20px; text-align: center; }"""


def admin_shell(
    title: str,
    inner: str,
    *,
    css: str = "",
    max_width: str = "920px",
    extra_head: str = "",
) -> str:
    """Wrap ``inner`` in the standard admin page skeleton.

    ``css`` is appended after the shared structural CSS (so it can extend or
    override it); ``max_width`` sets the ``.wrap`` column; ``extra_head`` is
    injected into ``<head>`` after the ``<title>`` (e.g. an auto-refresh meta).
    """
    base_css = _BASE_CSS.replace("__MAX_WIDTH__", max_width)
    page_css = f"\n{css}" if css else ""
    head_extra = f"\n  {extra_head}" if extra_head else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{esc(title)}</title>{head_extra}
  <style>
{base_css}{page_css}
  </style>
</head>
<body>
  <div class="wrap">
{admin_phase5_nav_html()}
    {inner}
  </div>
</body>
</html>"""

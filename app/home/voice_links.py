"""Render Hava voice markdown links as safe HTML anchors."""

from __future__ import annotations

import re

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def render_voice_links(text: str) -> str:
    """Render ``[label](url)`` into safe ``<a>`` tags."""
    out: list[str] = []
    last = 0
    for m in _LINK_RE.finditer(text):
        out.append(_html_escape(text[last : m.start()]))
        label = _html_escape(m.group(1))
        url = m.group(2).strip()
        if url.startswith(("http://", "https://", "/")):
            out.append(
                f'<a href="{_html_escape(url)}" rel="noopener">{label}</a>'
            )
        else:
            out.append(label)
        last = m.end()
    out.append(_html_escape(text[last:]))
    return "".join(out)


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

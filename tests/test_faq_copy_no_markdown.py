"""P0 render-bug guard: directory intro + FAQ copy must be plain text.

The live site leaked literal ``**### How many…**`` into FAQ headings — markdown
emitted verbatim because the templates render copy straight into ``<h3>``/``<p>``
(there is no markdown filter, by site convention). This guard pins that the
curated intro/FAQ source carries no markdown heading (``#``) or bold (``**``)
markers, so the leak can never regress from the copy side.
"""

from __future__ import annotations

from app.categories import leaf_copy, trades

_BANNED = ("###", "**", "`")


def _copy_strings() -> list[tuple[str, str]]:
    """(label, text) for every intro + FAQ question/answer in the curated copy."""
    out: list[tuple[str, str]] = []
    for slug, lc in leaf_copy.LEAF_COPY.items():
        out.append((f"leaf:{slug}:intro", lc.intro))
        for i, (q, a) in enumerate(lc.faqs):
            out.append((f"leaf:{slug}:faq{i}:q", q))
            out.append((f"leaf:{slug}:faq{i}:a", a))
    for slug, tr in trades.TRADES.items():
        out.append((f"trade:{slug}:intro", tr.intro))
        for i, (q, a) in enumerate(tr.faqs):
            out.append((f"trade:{slug}:faq{i}:q", q))
            out.append((f"trade:{slug}:faq{i}:a", a))
    return out


def test_directory_copy_has_no_markdown_markers() -> None:
    for label, text in _copy_strings():
        for marker in _BANNED:
            assert marker not in text, f"{label} contains {marker!r}: {text[:80]!r}"
        assert not text.lstrip().startswith("#"), f"{label} starts with '#': {text[:80]!r}"

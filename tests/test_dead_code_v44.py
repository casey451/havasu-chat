"""v4.4 PR-9 — the old UX is gone and stays gone.

Guards the dead-code sweep: no live HOME_REDESIGN flag, no ad-slot / gradient-
thumbnail / clouds CSS, and (kept here for symmetry with the shell PR) no
havasuchat.com anywhere in the templates.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "app"
_STYLES = _APP / "static" / "styles"
_TEMPLATES = _APP / "templates"

# Reads of the retired flag / preview override (comments and the live
# home_redesign.html template name are fine — this matches only ACTIVE usage).
_FLAG_READ = re.compile(
    r"""getenv\(\s*["']HOME_REDESIGN"""
    r"""|environ\[\s*["']HOME_REDESIGN"""
    r"""|query_params\.get\(\s*["']home_redesign"""
    r"""|\.get\(\s*["']home_redesign["']\s*\)"""
)


def test_no_live_home_redesign_flag() -> None:
    hits = [
        str(p) for p in _APP.rglob("*.py")
        if _FLAG_READ.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not hits, f"HOME_REDESIGN flag is retired but still read in: {hits}"


def test_dead_ad_and_thumbnail_css_removed() -> None:
    css = (_STYLES / "lake_redesign.css").read_text(encoding="utf-8")
    # The rail/in-feed ad slot (PR-5), the gradient thumbnails and the event-row
    # thumbnail (plain-time-column change) are all gone.
    assert ".feature-slot{" not in css
    assert ".feature-slot " not in css
    assert ".im-sunset" not in css
    assert ".ev .ph{" not in css


def test_cloud_icon_removed() -> None:
    icons = (_TEMPLATES / "components" / "redesign_icons.html").read_text(encoding="utf-8")
    assert "'cloud'" not in icons  # clouds tile retired in PR-4


def test_no_havasuchat_com_in_templates() -> None:
    hits = [
        str(p) for p in _TEMPLATES.rglob("*.html")
        if "havasuchat.com" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not hits, f"havasuchat.com found in templates: {hits}"

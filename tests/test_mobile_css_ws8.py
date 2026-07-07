"""WS8 — mobile responsive CSS contract (M15/M16/M17).

A Playwright 320/375 matrix is the spec's ideal, but absent that harness these
assertions pin the specific rules whose ABSENCE caused the audit defects — a
silent revert (someone dropping the flex-wrap or the 430px breakpoint) fails
here. The live behavior was verified in the browser preview at 320px and 375px:
"Diesel" fully visible, the `.counts` pill row scrolls instead of clipping, and
no page scrolls horizontally.
"""

from __future__ import annotations

import re
from pathlib import Path

_CSS = (Path(__file__).resolve().parents[1] / "app/static/styles/lake_redesign.css").read_text(
    encoding="utf-8"
)


def _rule(selector: str) -> str:
    """The declaration block for the first ``selector{...}`` occurrence."""
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", _CSS)
    assert m, f"no rule for {selector!r}"
    return m.group(1)


# ── M15: gas grade selector wraps + 44px targets + 2x2 below 430px ───────────
def test_gseg_wraps_instead_of_clipping() -> None:
    assert "flex-wrap:wrap" in _rule(".gseg")


def test_gseg_lg_button_has_44px_tap_target() -> None:
    assert "min-height:44px" in _rule(".gseg.lg button")


def test_gseg_becomes_2x2_grid_below_430px() -> None:
    # The 430px media query must make each /gas grade button ~half-width (2x2).
    m = re.search(r"@media\(max-width:430px\)\{[^@]*?\.gseg\.lg button\{([^}]*)\}", _CSS)
    assert m, "no <=430px rule sizing .gseg.lg button"
    assert "flex:1 1 45%" in m.group(1)


# ── M16: pill/count row scrolls instead of clipping ──────────────────────────
def test_counts_row_scrolls_horizontally() -> None:
    block = _rule(".counts")
    assert "overflow-x:auto" in block
    assert "flex-wrap:nowrap" in block


def test_cpill_has_44px_tap_target_and_snap() -> None:
    block = _rule(".cpill")
    assert "min-height:44px" in block
    assert "scroll-snap-align:start" in block


# ── M17: time/showtime pills meet the 44px minimum ───────────────────────────
def test_tpill_has_44px_tap_target() -> None:
    block = _rule(".tpill")
    assert "min-height:44px" in block
    # the movies parity test relies on this staying in the same block
    assert "text-decoration:none" in block

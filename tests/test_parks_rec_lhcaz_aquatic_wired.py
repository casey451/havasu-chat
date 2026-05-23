"""Wiring guard: ``lhcaz_aquatic`` source is fed by the PDF adapter.

The 2026-05-22 disable ship took ``lhcaz_aquatic`` out of
``scripts.run_scrapes.SOURCES`` after the city moved the schedule from
inline HTML to two PDF downloads on the redesigned Aquatic Center
page -- the old HTML parser silently returned ``[]`` and the
``parks-rec-scrapes`` cron failed for five consecutive runs (#57-#61).

The follow-up ship restored the source and wired it to the new PDF
parser at ``app.contrib.lhcaz_aquatic_pdf``. This test pins the wiring
so a future revert that points the source back at the legacy HTML
adapter (``_pull_lhcaz_aquatic``) -- whose target URL still redirects
to the schedule-less landing page -- would fail loudly instead of
silently producing empty snapshots.

See ``outputs/lhcaz_aquatic_pdf_rewrite_carry.md`` for the full carry
narrative.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_scrapes import (  # noqa: E402
    SOURCES,
    _pull_lhcaz_aquatic_pdf,
)


def test_lhcaz_aquatic_wired_to_pdf_adapter() -> None:
    """``lhcaz_aquatic`` SOURCES entry must point at the PDF adapter,
    not the legacy HTML adapter. The HTML adapter's target URL
    (``/parks-recreation/open-swim-schedule``) now redirects to a
    schedule-less landing page; using it again would silently produce
    empty snapshots and re-trigger the failures from #57-#61.
    """
    assert "lhcaz_aquatic" in SOURCES, (
        "lhcaz_aquatic vanished from scripts/run_scrapes.py::SOURCES — "
        "if the source was disabled intentionally, update this test (or "
        "delete it). See outputs/lhcaz_aquatic_pdf_rewrite_carry.md."
    )
    assert SOURCES["lhcaz_aquatic"] is _pull_lhcaz_aquatic_pdf, (
        "lhcaz_aquatic is wired to a different adapter — the legacy "
        "HTML adapter (_pull_lhcaz_aquatic) targets a URL that now "
        "redirects to a schedule-less landing page and would silently "
        "produce empty snapshots. See "
        "outputs/lhcaz_aquatic_pdf_rewrite_carry.md."
    )
    # WebTrac stays on -- the disable was targeted, not blanket.
    assert "webtrac" in SOURCES, (
        "webtrac source vanished from SOURCES — that's a regression unrelated "
        "to the lhcaz_aquatic wiring."
    )

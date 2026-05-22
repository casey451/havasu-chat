"""Regression guard: ``lhcaz_aquatic`` source stays disabled until the
PDF-parser rewrite ships.

Why this test exists
--------------------
The Lake Havasu City open-swim schedule moved from inline HTML to two
PDF downloads sometime between 2026-05-07 and 2026-05-21. The existing
``app.contrib.lhcaz_aquatic.parse_schedule_html`` parser silently
returns ``[]`` against the new page, which propagated as
``"no snapshot found"`` errors out of
``app.contrib.parks_rec_loader.load_latest_snapshots`` and caused five
consecutive ``parks-rec-scrapes`` cron failures (#57–#61).

The 2026-05-22 ship disabled the source in
``scripts.run_scrapes.SOURCES`` and silenced the
``"no snapshot found"`` path in
``app.contrib.parks_rec_loader.load_latest_snapshots`` for the aquatic
source only. The rewrite-required follow-up is documented in
``outputs/lhcaz_aquatic_pdf_rewrite_carry.md``.

This test defends against an accidental silent re-enable. If a future
commit puts ``lhcaz_aquatic`` back into SOURCES without also shipping
the PDF parser, this test fails loudly with a pointer to the carry.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_scrapes import SOURCES  # noqa: E402


def test_lhcaz_aquatic_source_disabled_until_pdf_rewrite_ships() -> None:
    """``lhcaz_aquatic`` must stay out of SOURCES until the rewrite lands.

    See ``outputs/lhcaz_aquatic_pdf_rewrite_carry.md`` for the re-enable
    checklist (new ``app.contrib.lhcaz_aquatic_pdf`` module, test
    fixtures, restored loader else-branch).
    """
    assert "lhcaz_aquatic" not in SOURCES, (
        "lhcaz_aquatic is back in scripts/run_scrapes.py::SOURCES but the "
        "PDF-parser rewrite has not shipped — see "
        "outputs/lhcaz_aquatic_pdf_rewrite_carry.md for the re-enable "
        "checklist. If the rewrite did ship, update this test to reflect "
        "the new contract (e.g., assert 'lhcaz_aquatic_pdf' is the active "
        "key instead)."
    )
    # WebTrac stays on — the disable is targeted, not blanket.
    assert "webtrac" in SOURCES, (
        "webtrac source vanished from SOURCES — that's a regression unrelated "
        "to the lhcaz_aquatic disable."
    )

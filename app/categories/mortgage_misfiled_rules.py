"""Rules for mortgage brokers mis-shelved under ``banks-and-credit-unions``.

Audit 2026-07-06 (T3.3): the ``banks-and-credit-unions`` leaf holds ~15 mortgage
brokers / loan officers (Guild Mortgage, loanDepot, Mohave Mortgage, PNC Mortgage,
"…Mortgage Loan Officer (NMLS #…)"). A mortgage lender is not a bank; a searcher
looking for a checking account gets a wall of loan officers. These move to a
dedicated ``mortgage-lenders`` leaf (created by
``scripts/create_mortgage_leaf_2026_07_06.py``).

A name signalling mortgage / loan origination -> ``mortgage-lenders``; a real bank
or credit union returns ``None`` (left put). Word-boundaried on ``loan``/``nmls``
so a bank whose name merely contains those letters is not swept in. Used by
``scripts/recategorize_mortgage_brokers_2026_07_06.py`` (DRY-RUN by default).
"""

from __future__ import annotations

import re

_MORTGAGE_LEAF = "mortgage-lenders"
_MORTGAGE_RE = re.compile(r"mortgage|\bloan\b|\bloans\b|\bnmls\b|lending|loandepot", re.IGNORECASE)


def classify_mortgage_misfiled_leaf(name: str | None) -> str | None:
    """Return ``"mortgage-lenders"`` for a mortgage broker / loan officer currently
    shelved under ``banks-and-credit-unions``, else ``None`` (leave a real bank)."""
    return _MORTGAGE_LEAF if _MORTGAGE_RE.search(name or "") else None

"""Phase E §3.1 — kids/family-first department ordering, behind a feature flag.

Dormant by default. With ``TAXONOMY_REORG_ENABLED`` unset/false,
:func:`reorder_departments` returns its input unchanged, so every nav/index
surface keeps today's taxonomy ``sort_order``. With the flag on, the departments
named in :data:`KIDS_FIRST_DEPT_ORDER` float to the top in that order, and all
other departments follow in their original sequence — a STABLE partition, so no
department is ever dropped or duplicated.

Scope: this overlay only reorders the level-0 department list. The other Phase E
taxonomy items — re-parenting **Open Swim** under Kids & Family and splitting the
**fitness** wall into subcategories (§3.2) — are DB/taxonomy changes that the
project's own implementation plan gates on a Casey-approved proposal derived from
a dataset audit (ASK_HAVA_BUILD_FIX_IMPL_PLAN §3.2 → HALT). They are deliberately
NOT part of this code-only, dormant overlay.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import TypeVar

from app.bootstrap_env import ensure_dotenv_loaded

TAXONOMY_REORG_FLAG = "TAXONOMY_REORG_ENABLED"

# Department slugs to promote, in the order they should appear at the top.
# Family/kid-relevant departments lead; the rest keep their taxonomy order below.
KIDS_FIRST_DEPT_ORDER: tuple[str, ...] = (
    "family-and-education",
    "things-to-do-and-attractions",
    "on-the-water",
    "eat-and-drink",
)

_T = TypeVar("_T")
_TRUE = {"1", "true", "yes", "on"}


def taxonomy_reorg_enabled() -> bool:
    ensure_dotenv_loaded()
    return (os.environ.get(TAXONOMY_REORG_FLAG) or "").strip().lower() in _TRUE


def reorder_departments(items: Sequence[_T], *, slug_of: Callable[[_T], str]) -> list[_T]:
    """Return ``items`` reordered kids-first when the flag is on, else unchanged.

    ``slug_of`` extracts the department slug from each item (items may be a
    ``Category`` or a ``(Category, ...)`` tuple). The result is a stable
    partition: promoted departments first (in :data:`KIDS_FIRST_DEPT_ORDER`),
    then every other item in its original relative order.
    """
    if not taxonomy_reorg_enabled():
        return list(items)
    priority = {slug: i for i, slug in enumerate(KIDS_FIRST_DEPT_ORDER)}
    promoted = sorted(
        (it for it in items if slug_of(it) in priority),
        key=lambda it: priority[slug_of(it)],
    )
    rest = [it for it in items if slug_of(it) not in priority]
    return promoted + rest

"""Generate per-row eval probes for the confabulation harness (spec §3.2).

Template strings and ordering follow ``relay/halt1-closure-final-lexicons.md`` Section 1
literally.  ``<n>`` is replaced once with the row’s display name with no other transforms.

**Live rows** (aligned with :mod:`app.chat.tier2_db_query` / browse sampling):

- **Provider:** ``draft is False`` and ``is_active is True``.
- **Program:** ``draft is False`` and ``is_active is True``.

Providers are iterated in ``provider_name`` ascending order, then programs in ``title``
ascending order. Within each row, templates are emitted in the closure’s numbered order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select


def normalize_row_name_for_include(name: str) -> str:
    """Normalize display names for ``--include`` / ``--exclude`` matching.

    En dash (U+2013) and em dash (U+2014) are mapped to ASCII hyphen so CLI CSV
    lists match catalog titles that use typographic dashes.
    """
    s = (name or "").strip().lower()
    return s.replace("\u2014", "-").replace("\u2013", "-")
from sqlalchemy.orm import Session

from app.db.models import Program, Provider

RowType = Literal["provider", "program"]

# relay/halt1-closure-final-lexicons.md §1 — (template, stable template_id)
_PROBES_PROVIDER: tuple[tuple[str, str], ...] = (
    ("tell me about <n>", "provider_tell_me_about"),
    ("what does <n> offer", "provider_what_offer"),
    ("where is <n>", "provider_where_is"),
)

_PROBES_PROGRAM: tuple[tuple[str, str], ...] = (
    ("tell me about <n>", "program_tell_me_about"),
    ("when does <n> meet", "program_when_meet"),
    ("what is <n>", "program_what_is"),
)


@dataclass(frozen=True, slots=True)
class Probe:
    query_text: str
    row_id: str
    row_type: RowType
    template_id: str


def _apply_template(template: str, display_name: str) -> str:
    return template.replace("<n>", display_name)


def generate_probes(session: Session) -> list[Probe]:
    out: list[Probe] = []

    providers = list(
        session.scalars(
            select(Provider)
            .where(Provider.draft.is_(False), Provider.is_active.is_(True))
            .order_by(Provider.provider_name.asc())
        ).all()
    )
    for p in providers:
        name = p.provider_name
        for template, template_id in _PROBES_PROVIDER:
            out.append(
                Probe(
                    query_text=_apply_template(template, name),
                    row_id=p.id,
                    row_type="provider",
                    template_id=template_id,
                )
            )

    programs = list(
        session.scalars(
            select(Program)
            .where(Program.draft.is_(False), Program.is_active.is_(True))
            .order_by(Program.title.asc())
        ).all()
    )
    for pr in programs:
        name = pr.title
        for template, template_id in _PROBES_PROGRAM:
            out.append(
                Probe(
                    query_text=_apply_template(template, name),
                    row_id=pr.id,
                    row_type="program",
                    template_id=template_id,
                )
            )

    return out

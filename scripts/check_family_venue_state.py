"""Read-only diagnostic: why aren't the RC track + roller rink in family-fun?

Prints the live state of the two seeded venues and whether
``app/chat/family_fun.py`` would surface them. WRITES NOTHING.

    .venv\\Scripts\\python.exe -m scripts.check_family_venue_state
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select  # noqa: E402

from app.chat.family_fun import (  # noqa: E402
    _FAMILY_GOOGLE_CATEGORIES,
    _is_excluded,
    _name_has_family_keyword,
)
from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Provider  # noqa: E402

SLUGS = ("desert-hawks-rc-club", "havasu-skates-sara-park-roller-rink")
_FAM = set(_FAMILY_GOOGLE_CATEGORIES)


def main() -> int:
    with SessionLocal() as db:
        for slug in SLUGS:
            p = db.scalar(select(Provider).where(Provider.slug == slug))
            if p is None:
                print(f"\n{slug}: NOT FOUND")
                continue
            name_hit = _name_has_family_keyword(p.provider_name)
            cat_hit = (p.google_primary_category or "") in _FAM
            excluded = _is_excluded(p)
            visible = (not p.draft) and p.is_active
            shows = visible and (name_hit or cat_hit) and not excluded
            print(f"\n{p.provider_name}  (/provider/{slug})")
            print(f"  draft={p.draft}  pending_review={p.pending_review}  "
                  f"is_active={p.is_active}  verified={p.verified}")
            print(f"  category={p.category!r}  "
                  f"google_primary_category={getattr(p, 'google_primary_category', None)!r}")
            print(f"  name keyword match={name_hit}  google-cat match={cat_hit}  "
                  f"excluded={excluded}")
            print(f"  --> visible gate (draft=False & active)={visible}")
            print(f"  ==> WOULD SHOW IN FAMILY-FUN: {shows}")
            if not shows:
                reasons = []
                if p.draft:
                    reasons.append("still draft (needs admin approval)")
                if not p.is_active:
                    reasons.append("is_active=False")
                if not (name_hit or cat_hit):
                    reasons.append("no name/category match for family_fun")
                if excluded:
                    reasons.append("hit an exclude token")
                print(f"      reason(s): {', '.join(reasons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

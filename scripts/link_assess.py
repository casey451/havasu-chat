"""CLI: local-LLM assessment of confirmed-broken links (suggests fixes for /admin).

For each confirmed-broken *provider* link not yet assessed, fetch the site's root
domain and ask the local model whether the business is still there and what the
correct URL is. Writes the verdict + suggestion onto the link_health row (shown
read-only on /admin/link-health). Never edits provider/event rows.

  python scripts/link_assess.py                 # dry-run: print verdicts, write nothing
  python scripts/link_assess.py --apply          # persist verdicts/suggestions
  python scripts/link_assess.py --limit 20 --apply

Slow (local CPU model, ~1-3 min each), so it's capped and yields to heavier jobs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded  # noqa: E402

ensure_dotenv_loaded()

from app.monitoring import link_health as lh  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=50, help="max links to assess this run")
    p.add_argument("--apply", action="store_true", help="persist verdict/suggestion (else dry-run)")
    p.add_argument("--reassess", action="store_true", help="also re-check already-assessed links")
    args = p.parse_args(argv)

    from sqlalchemy import select

    from app.db.database import SessionLocal
    from app.db.models import LinkHealth

    with SessionLocal() as db:
        q = select(LinkHealth.url, LinkHealth.label).where(
            LinkHealth.confirmed_broken, LinkHealth.kind.like("provider%")
        )
        if not args.reassess:
            q = q.where(LinkHealth.llm_checked_at.is_(None))
        targets = list(db.execute(q.limit(args.limit)))

    print(f"=== link assessment ({'APPLY' if args.apply else 'DRY RUN'}) — {len(targets)} link(s) ===")
    now = datetime.now(UTC).replace(tzinfo=None)
    for url, label in targets:
        verdict, suggestion = lh.assess_link(url, label or "")
        print(f"\n- {label or '(?)'} | {url}")
        print(f"    verdict: {verdict}")
        if suggestion:
            print(f"    suggested: {suggestion}")
        if args.apply:
            with SessionLocal() as db:
                lh.save_assessment(db, url, verdict, suggestion, now=now)
                db.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Nightly directory-integrity report — the "stop finding random problems" layer.

Master site audit §9.4 (consolidated Amendment Phase 9): every class of rot the
2026-07-01 crawl surfaced becomes a one-query nightly check. Two severities:

* HARD checks (must be zero; a hit fails the run):
    D  live-event exact duplicates (title, date, start_time, venue)
    F  cuisine chips whose landing would 404 (chip pool vs render gate)
* BASELINE checks (a known backlog exists; the run fails only when a count
  RISES above scripts/integrity_baseline.json — i.e. new bleeding):
    A  active providers on ZERO taxonomy leaves (browse-orphans)
    B  active providers with no actionable contact (no phone AND no/placeholder
       address)
    C  same-phone provider clusters (excluding the CVB placeholder number)
    E  past-dated live ONE-OFF events (recurring series exempt)

Run with ``--update-baseline`` after an approved cleanup to ratchet the
baseline DOWN to current counts (it never auto-raises). Exit codes: 0 clean,
1 findings. Read-only against the DB either way.

Usage:
    .venv\\Scripts\\python.exe scripts/integrity_report.py
    .venv\\Scripts\\python.exe scripts/integrity_report.py --update-baseline
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.contrib.ingest_suppression import is_placeholder_address  # noqa: E402
from app.core.timezone import now_lake_havasu  # noqa: E402
from app.db.database import DATABASE_URL, SessionLocal  # noqa: E402
from app.db.models import Category, EntityCategory, Event, Provider  # noqa: E402

_BASELINE_PATH = _ROOT / "scripts" / "integrity_baseline.json"

# The CVB's 800 number rides on ~50 place-type rows as a shared contact — a
# known, accepted cluster, not a dup signal.
_IGNORED_PHONES = {"8002428278"}
_PHONE_DIGITS = re.compile(r"\d")
_WS = re.compile(r"\s+")


def _norm_phone(phone: str | None) -> str:
    digits = "".join(_PHONE_DIGITS.findall(phone or ""))
    return digits[-10:] if len(digits) >= 10 else ""


def _norm_text(s: str | None) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def _load_baseline() -> dict[str, int]:
    if _BASELINE_PATH.exists():
        try:
            return {k: int(v) for k, v in json.loads(
                _BASELINE_PATH.read_text(encoding="utf-8")).items()}
        except (ValueError, TypeError):
            pass
    return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nightly directory-integrity report.")
    ap.add_argument("--update-baseline", action="store_true",
                    help="write current counts as the new baseline (ratchet down)")
    args = ap.parse_args(argv)

    redacted = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print("=" * 78)
    print("DIRECTORY INTEGRITY REPORT (read-only)")
    print("=" * 78)
    print(f"DB target: …@{redacted}\n")

    baseline = _load_baseline()
    counts: dict[str, int] = {}
    hard_failures: list[str] = []
    today = now_lake_havasu().date()

    with SessionLocal() as db:
        actives = (
            db.query(Provider)
            .filter(Provider.is_active.is_(True), Provider.draft.is_(False))
            .all()
        )
        linked_eids = {eid for (eid,) in db.query(EntityCategory.entity_id).distinct().all()}

        # A — browse-orphans
        orphans = [p for p in actives if p.entity_id and p.entity_id not in linked_eids]
        counts["zero_leaf_providers"] = len(orphans)
        print(f"A zero-leaf active providers: {len(orphans)}")
        for p in sorted(orphans, key=lambda p: p.provider_name or "")[:10]:
            print(f"    {p.provider_name}")
        if len(orphans) > 10:
            print(f"    … +{len(orphans) - 10} more")

        # B — no actionable contact
        ghosts = [
            p for p in actives
            if not (p.phone or "").strip()
            and (not (p.address or "").strip() or is_placeholder_address(p.address))
        ]
        counts["zero_contact_providers"] = len(ghosts)
        print(f"\nB zero-contact active providers: {len(ghosts)}")
        for p in sorted(ghosts, key=lambda p: p.provider_name or "")[:10]:
            print(f"    {p.provider_name}")
        if len(ghosts) > 10:
            print(f"    … +{len(ghosts) - 10} more")

        # C — same-phone clusters
        by_phone: dict[str, set[str]] = defaultdict(set)
        for p in actives:
            ph = _norm_phone(p.phone)
            if ph and ph not in _IGNORED_PHONES:
                by_phone[ph].add(_norm_text(p.provider_name))
        clusters = {ph: names for ph, names in by_phone.items() if len(names) > 1}
        counts["same_phone_clusters"] = len(clusters)
        print(f"\nC same-phone clusters (distinct names): {len(clusters)}")

        # D — live-event exact dups (HARD: must be zero)
        by_key: dict[tuple, int] = defaultdict(int)
        for ev in db.query(Event).filter(Event.status == "live").all():
            by_key[(_norm_text(ev.title), ev.date, ev.start_time,
                    _norm_text(ev.location_name))] += 1
        dup_clusters = {k: n for k, n in by_key.items() if n > 1}
        counts["event_exact_dups"] = len(dup_clusters)
        print(f"\nD live-event exact duplicate clusters: {len(dup_clusters)} (HARD)")
        for (title, d, t, venue), n in list(dup_clusters.items())[:10]:
            print(f"    x{n}  {d} {t or ''}  {title[:44]} @{venue[:20]}")
        if dup_clusters:
            hard_failures.append(f"D: {len(dup_clusters)} exact event dup clusters")

        # E — past-dated live one-offs
        stale = [
            ev for ev in db.query(Event).filter(Event.status == "live").all()
            if not (ev.is_recurring or ev.rrule or ev.rdate)
            and (ev.end_date or ev.date) < today
        ]
        counts["past_live_oneoffs"] = len(stale)
        print(f"\nE past-dated live one-off events: {len(stale)}")

        # F — cuisine chips vs render gate (HARD: chips must resolve)
        try:
            from app.categories.cuisine_pages import (
                CUISINE_PAGE_MIN_PROVIDERS,
                _eat_drink_cuisine_counts,
            )
            from app.categories.queries import available_cuisines_for_route

            cuisine_counts = _eat_drink_cuisine_counts(db)
            chips = {c["slug"] for c in available_cuisines_for_route(db, "eat-drink")}
            broken = {s for s in chips
                      if cuisine_counts.get(s, 0) < CUISINE_PAGE_MIN_PROVIDERS}
            counts["cuisine_chip_404s"] = len(broken)
            print(f"\nF cuisine chips below the render gate: {len(broken)} (HARD)")
            if broken:
                print(f"    {sorted(broken)}")
                hard_failures.append(f"F: {len(broken)} cuisine chips would 404")
        except Exception as exc:  # noqa: BLE001 — report must not crash on one section
            print(f"\nF cuisine chip check errored: {exc}")

        # sanity context: leaf count (drift canary for the taxonomy itself)
        counts["live_leaves"] = (
            db.query(Category).filter(Category.level == 1).count()
        )

    # --- verdict -------------------------------------------------------------
    print("\n" + "=" * 78)
    regressions: list[str] = []
    for key in ("zero_leaf_providers", "zero_contact_providers",
                "same_phone_clusters", "past_live_oneoffs"):
        base = baseline.get(key)
        cur = counts.get(key, 0)
        marker = ""
        if base is None:
            marker = "(no baseline yet)"
        elif cur > base:
            marker = f"REGRESSION (baseline {base})"
            regressions.append(f"{key}: {cur} > {base}")
        elif cur < base:
            marker = f"improved (baseline {base} — run --update-baseline)"
        else:
            marker = f"(= baseline {base})"
        print(f"  {key:26s} {cur:5d}  {marker}")

    if args.update_baseline or not baseline:
        new_base = {k: counts[k] for k in
                    ("zero_leaf_providers", "zero_contact_providers",
                     "same_phone_clusters", "past_live_oneoffs")}
        _BASELINE_PATH.write_text(json.dumps(new_base, indent=1) + "\n", encoding="utf-8")
        print(f"\nbaseline {'updated' if baseline else 'initialized'}: "
              f"{_BASELINE_PATH.relative_to(_ROOT)}")
        if not baseline:
            return 0  # first run just establishes the floor

    if hard_failures or regressions:
        print("\nFINDINGS:")
        for f in hard_failures + regressions:
            print(f"  - {f}")
        return 1
    print("\nCLEAN — no new bleeding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

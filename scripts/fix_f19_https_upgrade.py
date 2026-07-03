"""F19: upgrade provider website links from http:// to https:// WHEN AVAILABLE.

The directory has ~680 active providers whose ``website`` is ``http://``. Many
sites also serve https; some are http-only. We must NOT blindly rewrite the
scheme — sending a user to a broken-cert or non-existent https page is worse
than the working http link. So this probes each site's https candidate with a
VALID TLS cert and confirms the response stays on https (no downgrade / redirect
to another host), and only upgrades the ones that genuinely resolve.

Gated prod-data op (CLAUDE.md): dry-run -> show counts -> Casey approves -> apply.

    python scripts/fix_f19_https_upgrade.py            # dry-run (default), no writes
    python scripts/fix_f19_https_upgrade.py --apply     # writes Provider.website

ASCII-only output by project convention.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.contrib.url_fetcher import is_blocked_target  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import Provider  # noqa: E402
from app.monitoring.link_health import USER_AGENT  # noqa: E402

_TIMEOUT = 12.0
_WORKERS = 24


def _https_candidate(url: str) -> str | None:
    u = (url or "").strip()
    if not u.lower().startswith("http://"):
        return None
    return "https://" + u[len("http://") :]


def probe_https(candidate: str) -> tuple[bool, str]:
    """True when the https candidate resolves with a valid cert AND the final
    URL is still https (no downgrade / cross-host bounce). Returns (ok, detail)."""
    blocked, reason = is_blocked_target(candidate)
    if blocked:
        return (False, f"blocked: {reason}")
    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(
            timeout=_TIMEOUT, follow_redirects=True, headers=headers, verify=True
        ) as c:
            r = c.get(candidate)
    except httpx.HTTPError as exc:
        return (False, f"{type(exc).__name__}: {exc}".strip()[:120])
    final = str(r.url)
    if not final.lower().startswith("https://"):
        return (False, f"HTTP {r.status_code} -> downgraded to {final[:60]}")
    if r.status_code >= 400:
        return (False, f"HTTP {r.status_code}")
    return (True, f"HTTP {r.status_code}")


def main() -> int:
    ap = argparse.ArgumentParser(description="F19: http->https provider links (gated)")
    ap.add_argument("--apply", action="store_true", help="write upgrades (default: dry-run)")
    args = ap.parse_args()
    dry_run = not args.apply

    print(f"DB host={engine.url.host} db={engine.url.database} dry_run={dry_run}\n")
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Provider.id, Provider.provider_name, Provider.website)
            .where(
                Provider.website.ilike("http://%"),
                Provider.is_active.is_(True),
                Provider.draft.is_(False),
            )
        ).all()
        print(f"active non-draft providers with http:// website: {len(rows)}\n")

        candidates = [
            (r.id, r.provider_name, r.website, _https_candidate(r.website))
            for r in rows
        ]
        candidates = [c for c in candidates if c[3]]

        results: dict[str, tuple[bool, str, str, str, str]] = {}

        def _work(item):
            pid, name, url, cand = item
            ok, detail = probe_https(cand)
            return pid, (ok, name, url, cand, detail)

        with ThreadPoolExecutor(max_workers=_WORKERS) as ex:
            futs = [ex.submit(_work, c) for c in candidates]
            for i, fut in enumerate(as_completed(futs), 1):
                pid, val = fut.result()
                results[pid] = val
                if i % 100 == 0:
                    print(f"  probed {i}/{len(candidates)}...")

        upgradable = {pid: v for pid, v in results.items() if v[0]}
        http_only = {pid: v for pid, v in results.items() if not v[0]}
        print(f"\nRESULT: upgradable(https OK)={len(upgradable)}  "
              f"http-only(no valid https)={len(http_only)}  total={len(results)}")

        print("\nsample UPGRADABLE (name -> https):")
        for _pid, (_ok, name, _url, cand, _d) in list(upgradable.items())[:12]:
            print(f"  {name[:34]:34} -> {cand[:60]}")
        print("\nsample HTTP-ONLY (kept; reason):")
        for _pid, (_ok, name, _url, _cand, d) in list(http_only.items())[:12]:
            print(f"  {name[:34]:34} | {d}")

        snap = Path(__file__).resolve().parents[1] / "scripts" / "_snapshots"
        snap.mkdir(exist_ok=True)
        out = snap / "f19_https_upgradable.tsv"
        with out.open("w", encoding="utf-8") as fh:
            fh.write("provider_id\tname\told\tnew\n")
            for pid, (_ok, name, url, cand, _d) in upgradable.items():
                fh.write(f"{pid}\t{name}\t{url}\t{cand}\n")
        print(f"\nwrote upgradable list -> {out}")

        if dry_run:
            print("\n[dry-run] no DB writes. Re-run with --apply after approval.")
            return 0

        n = 0
        for pid, (_ok, _name, _url, cand, _d) in upgradable.items():
            p = db.get(Provider, pid)
            if p is not None and (p.website or "").lower().startswith("http://"):
                p.website = cand
                n += 1
        db.commit()
        print(f"\nAPPLIED: upgraded {n} provider websites to https.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

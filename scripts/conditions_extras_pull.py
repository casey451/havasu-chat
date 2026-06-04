"""
CLI: dry-run the source-expansion conditions/outdoors sources.

Build-only / inert: fetch + parse, prints a dry-run summary, writes nothing.

  python scripts/conditions_extras_pull.py --source nws_extras
  python scripts/conditions_extras_pull.py --source rise        # needs FEATURE_FLAG_WATER_TEMP_RISE_6127
  python scripts/conditions_extras_pull.py --source wildfire
  python scripts/conditions_extras_pull.py --source az511       # event API needs AZ511_API_KEY; WZDx keyless
  python scripts/conditions_extras_pull.py --source azgfd       # uses proxy env for Cloudflare
  python scripts/conditions_extras_pull.py --source nws_extras --apply  # guarded
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.conditions import az511, nws_extras, rise_water_temp, wildfire  # noqa: E402
from app.contrib import azgfd_fishing  # noqa: E402
from app.contrib.scrape_dryrun import apply_guard, print_dry_run_report  # noqa: E402


def _run_nws_extras() -> None:
    payload = nws_extras.fetch_gridpoint_extras()
    covered = nws_extras.lake_wind_advisory_zone_covered()
    print("=== nws_extras — DRY RUN (no writes) ===")
    print(json.dumps(payload, indent=2, default=str))
    print(f"Lake Wind Advisory zone {nws_extras.LAKE_WIND_ADVISORY_ZONE} covered by alert filter: {covered}")
    if not covered:
        print("note: GAP — add AZZ036 to LHC_NWS_ZONE_ID so lake wind advisories are caught.")


def _run_rise() -> None:
    payload = rise_water_temp.fetch_rise_water_temp()
    print("=== rise_water_temp — DRY RUN (no writes) ===")
    print(json.dumps(payload, indent=2, default=str))
    if not payload.get("feature_enabled"):
        print("note: feature flag FEATURE_FLAG_WATER_TEMP_RISE_6127 is OFF — no HTTP made.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", choices=["nws_extras", "rise", "wildfire", "az511", "azgfd"], required=True)
    p.add_argument("--apply", action="store_true", help="(guarded) attempt live ingestion")
    args = p.parse_args(argv)

    if args.apply:
        apply_guard(f"conditions:{args.source}")

    if args.source == "nws_extras":
        _run_nws_extras()
    elif args.source == "rise":
        _run_rise()
    elif args.source == "wildfire":
        incidents = wildfire.fetch_incidents()
        print_dry_run_report(wildfire.SOURCE, incidents, sample_fn=wildfire.incident_sample)
    elif args.source == "az511":
        events = az511.fetch_events() + az511.fetch_wzdx()
        print_dry_run_report(az511.SOURCE, events, sample_fn=az511.event_sample)
    elif args.source == "azgfd":
        reports = azgfd_fishing.fetch_bulletins()
        print_dry_run_report(
            azgfd_fishing.SOURCE,
            reports,
            sample_fn=azgfd_fishing.report_sample,
            notes=["Cloudflare source — set AZGFD_SCRAPE_PROXY_URL/GAS_SCRAPE_PROXY_URL. NEEDS_PROD_VERIFY."],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

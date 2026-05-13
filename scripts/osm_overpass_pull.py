"""Operator-runnable Layer-2 OSM Overpass discovery script.

Phase 4.3 proof: single-category run (default leisure=dog_park).
"""

from __future__ import annotations

import argparse
import sys

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.osm_overpass_client import OsmOverpassClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="leisure")
    parser.add_argument("--value", default="dog_park")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    client = OsmOverpassClient()
    payloads = client.run({"tag": args.tag, "value": args.value})
    print(f"Discovered {len(payloads)} {args.tag}={args.value} payloads from OSM")
    if args.dry_run:
        for p in payloads[:5]:
            print(f"  {p.name} @ ({p.lat}, {p.lng})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

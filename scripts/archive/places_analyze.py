"""Quick post-sweep analysis of discovery output.

Reads scripts/output/places_pull/discovery_unique.jsonl and prints:
  - Total unique places
  - ZIP distribution (LHC ZIPs vs spillover)
  - City distribution (catches Parker / Topock / Bullhead spillover)
  - Cross-category overlap histogram
  - Top primaryType values

Used after the dry-run gate and after the full sweep. Read-only — no API
calls, no writes.

Usage:
    python -m scripts.places_analyze
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

UNIQUE_PATH = Path("scripts/output/places_pull/discovery_unique.jsonl")

LHC_ZIPS = {"86403", "86404", "86405", "86406"}  # 86405 sometimes appears in USPS data


def main() -> None:
    if not UNIQUE_PATH.exists():
        raise SystemExit(f"missing: {UNIQUE_PATH}")

    text = UNIQUE_PATH.read_text(encoding="utf-8")
    places = [json.loads(line) for line in text.splitlines() if line.strip()]
    print(f"Total unique places: {len(places)}")

    # ZIP distribution
    zips: collections.Counter[str] = collections.Counter()
    no_zip = 0
    for p in places:
        addr = p.get("formattedAddress", "") or ""
        m = re.search(r"\b(8\d{4})\b", addr)
        if m:
            zips[m.group(1)] += 1
        else:
            no_zip += 1

    print()
    print("ZIP distribution:")
    for z, c in zips.most_common():
        marker = " (LHC)" if z in LHC_ZIPS else " (SPILLOVER)"
        print(f"  {z}: {c}{marker}")
    if no_zip:
        print(f"  no-zip-found: {no_zip}")

    in_lhc = sum(c for z, c in zips.items() if z in LHC_ZIPS)
    spillover = sum(c for z, c in zips.items() if z not in LHC_ZIPS)
    print()
    print(f"In-LHC: {in_lhc}   Spillover: {spillover}   No ZIP: {no_zip}")

    # City spillover signal — even when ZIP is missing, the city name catches Parker etc.
    cities: collections.Counter[str] = collections.Counter()
    for p in places:
        addr = p.get("formattedAddress", "") or ""
        m = re.search(r",\s*([A-Za-z][A-Za-z\s\-]+),\s*[A-Z]{2}\s+\d", addr)
        if m:
            cities[m.group(1).strip()] += 1
        else:
            cities["(unknown)"] += 1

    print()
    print("City distribution:")
    for city, n in cities.most_common():
        print(f"  {city}: {n}")

    # Cross-category overlap
    hist = collections.Counter(len(p.get("_seen_categories", [])) for p in places)
    print()
    print("Cross-category overlap (places seen in N categories):")
    for k in sorted(hist):
        print(f"  {k} categor{'y' if k == 1 else 'ies'}: {hist[k]} places")

    # Top primary types
    types: collections.Counter[str] = collections.Counter(
        p.get("primaryType", "(none)") for p in places
    )
    print()
    print("Top 15 primaryType values:")
    for t, n in types.most_common(15):
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()

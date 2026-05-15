"""Operator-runnable Layer-2 OSM Overpass discovery script.

Writes a wrapper-line JSONL to ``scripts/output/osm_pull/osm_elements.jsonl``
(matches :data:`scripts.osm_overpass_load.DEFAULT_INPUT_PATH`) so the load
step can ingest it.

Phase 5.2 unblocker: prior to this change the pull only printed in-memory
``EntityPayload`` objects; the load script could not find the JSONL it
expected, breaking the documented runbook chain
``pull --tag X --value Y`` → ``load --tag X --value Y``.

The wrapper-line shape (`{"elements": [...]}` on a single line) is what
:func:`scripts.osm_overpass_load._iter_feature_elements` natively handles,
with the load's ``--tag``/``--value`` flags performing the same tag filter
the pull did. The pull's per-element view (``RawHit.raw["element"]``)
preserves the full Overpass element (lat/lon for nodes, center for ways,
geometry array when present) so the load's ``_element_lat_lng`` resolver
has all the information it needs.

Usage:
    python -m scripts.osm_overpass_pull --tag leisure  --value marina
    python -m scripts.osm_overpass_pull --tag man_made --value pier
    python -m scripts.osm_overpass_pull --tag natural  --value beach

    # dry-run: discover + print first 5, no JSONL written
    python -m scripts.osm_overpass_pull --tag leisure --value marina --dry-run

    # explicit output path (default matches the load's DEFAULT_INPUT_PATH)
    python -m scripts.osm_overpass_pull --tag leisure --value marina \\
        --output scripts/output/osm_pull/marinas.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

from app.contrib.osm_overpass_client import OsmOverpassClient  # noqa: E402

# Mirror scripts.osm_overpass_load.DEFAULT_INPUT_PATH so a bare
# ``pull`` followed by a bare ``load`` chains end-to-end without flags.
DEFAULT_OUTPUT_PATH = Path(__file__).parent / "output" / "osm_pull" / "osm_elements.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="leisure")
    parser.add_argument("--value", default="dog_park")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "JSONL output path; default matches "
            "scripts.osm_overpass_load.DEFAULT_INPUT_PATH so the load can "
            "pick it up without an --input flag."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover only; print payload count and first 5, do not write JSONL.",
    )
    args = parser.parse_args()

    client = OsmOverpassClient()
    hits = client.discover({"tag": args.tag, "value": args.value})
    print(f"Discovered {len(hits)} {args.tag}={args.value} elements from OSM")

    for hit in hits[:5]:
        print(f"  {hit.name} @ ({hit.lat}, {hit.lng})")

    if args.dry_run:
        print("[osm_overpass_pull] dry-run: no JSONL written")
        return 0

    elements = [hit.raw["element"] for hit in hits]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Wrapper-line shape — one line, single JSON object with "elements" array.
    # scripts.osm_overpass_load._iter_feature_elements iterates obj["elements"]
    # and filters by --tag/--value at load time (so a multi-pair workflow can
    # share a single JSONL if desired; the default per-run overwrite keeps the
    # runbook's pair-by-pair sequence simple).
    with args.output.open("w") as f:
        f.write(json.dumps({"elements": elements}) + "\n")
    print(f"Wrote {len(elements)} elements -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

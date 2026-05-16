"""Google Places Layer-1 client conforming to :class:`BaseIngestClient`.

Extracted from ``scripts/places_discovery.py`` and ``scripts/places_enrichment.py``
(Phase 4.2). Same JSONL outputs, log lines, pagination, dedupe-by-place-id,
and rate limits: discovery uses :data:`GOOGLE_PLACES_LIMITER` (4 QPS); enrichment
uses a dedicated 6.5 QPS limiter matching the pre-refactor script.

HTTP uses ``httpx`` directly (same as the legacy scripts), not
``app.contrib.places_client`` — that module remains the Phase 5.2
provider-enrichment client.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx

from app.contrib.google_types_mapping import map_google_types_to_slug_and_place_type
from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, EntityPayload, RawHit
from app.contrib.rate_limiter import GOOGLE_PLACES_LIMITER, SourceLimiter

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Discovery field mask (unchanged from legacy ``places_discovery.py``).
DISCOVERY_FIELD_MASK: Final = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.types",
        "nextPageToken",
    ]
)

# Enrichment field mask (unchanged from legacy ``places_enrichment.py``).
ENRICHMENT_FIELD_MASK: Final = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "addressComponents",
        "nationalPhoneNumber",
        "websiteUri",
        "regularOpeningHours",
        "primaryType",
        "types",
        "location",
        "rating",
        "userRatingCount",
        "reviews",
        "photos",
    ]
)

PAGINATION_SLEEP_S = 2.0
MAX_PAGES_PER_CATEGORY = 3
QUERY_SUFFIX = " in Lake Havasu City, AZ"
_RETRY_EXHAUSTED_STATUSES: Final = frozenset({429, 500, 502, 503, 504})

DRY_RUN_LABELS: Final = frozenset(
    {
        "restaurants",
        "coffee shops",
        "hair salons",
        "auto repair",
        "boat rentals",
    }
)

# Tier-1 taxonomy slug → ``places_categories.json`` ``domain`` values.
DISCOVERY_CATEGORY_TO_DOMAINS: dict[str, frozenset[str]] = {
    "eat-drink": frozenset({"food_drink"}),
    "home-property-services": frozenset({"home_services"}),
    "health-wellness-care": frozenset({"health_medical", "fitness_sports"}),
    "on-the-water": frozenset({"lake_recreation"}),
    "auto-rv-fuel": frozenset({"auto"}),
    "shopping-essentials": frozenset({"retail"}),
    "outdoors-parks-trails": frozenset({"fitness_sports", "entertainment_attractions"}),
    "lodging-vacation-rentals": frozenset({"lodging", "lake_recreation"}),
    "pets": frozenset({"pets"}),
    "events": frozenset({"entertainment_attractions"}),
    "classes-sports-recreation": frozenset({"childcare_education", "fitness_sports"}),
    "public-civic-resources": frozenset({"religion_community"}),
}

# Enrichment uses 6.5 QPS — distinct from discovery's shared limiter.
_ENRICHMENT_LIMITER: Final = SourceLimiter("google_places_enrichment", qps=6.5)

PROGRESS_EVERY = 50


def load_categories_for_discovery(
    path: Path,
    *,
    dry_run: bool,
    category_slug: str | None,
) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cats: list[dict[str, str]] = data["categories"]
    if category_slug is not None:
        domains = DISCOVERY_CATEGORY_TO_DOMAINS.get(category_slug)
        if domains is None:
            known = ", ".join(sorted(DISCOVERY_CATEGORY_TO_DOMAINS))
            raise SystemExit(
                f"Unknown --category {category_slug!r}. Expected one of: {known}"
            )
        cats = [c for c in cats if c.get("domain", "") in domains]
    if dry_run:
        if category_slug is None:
            cats = [c for c in cats if c["label"] in DRY_RUN_LABELS]
            missing = DRY_RUN_LABELS - {c["label"] for c in cats}
            if missing:
                raise SystemExit(
                    f"Dry-run sample missing from categories file: {sorted(missing)}"
                )
        else:
            # When --category is specified, dry-run samples the first 2 labels
            # of the category's filtered set. The legacy ``DRY_RUN_LABELS``
            # frozenset is hand-picked for the no-``--category`` 5-category
            # sample and rarely overlaps with a single category's labels
            # (e.g. ``home-property-services`` has zero overlap), so applying
            # it on top of ``--category`` produced an empty intersection and
            # silently zeroed the dry-run. This branch makes ``--dry-run
            # --category <slug>`` deterministically preview the first 2
            # labels of the slug — small budget, real signal.
            cats = cats[:2]
    return cats


class GooglePlacesClient(BaseIngestClient):
    """Layer-1 Google Places Text Search + Place Details."""

    source_name = "google_places"

    def __init__(
        self,
        *,
        discovery_limiter: SourceLimiter | None = None,
        enrichment_limiter: SourceLimiter | None = None,
    ) -> None:
        self._discovery_limiter = discovery_limiter or GOOGLE_PLACES_LIMITER
        self._enrichment_limiter = enrichment_limiter or _ENRICHMENT_LIMITER
        self._active_api_key: str | None = None

    def request_text_search(
        self, api_key: str, query: str, page_token: str | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"textQuery": query}
        if page_token:
            body["pageToken"] = page_token
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": DISCOVERY_FIELD_MASK,
        }
        with httpx.Client(timeout=30) as client:
            resp = self._discovery_limiter.call_with_retry(
                lambda: client.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=body)
            )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in _RETRY_EXHAUSTED_STATUSES:
            raise RuntimeError(
                f"Places API: retries exhausted for query={query!r} "
                f"(last status {resp.status_code})"
            )
        raise RuntimeError(
            f"Places API error {resp.status_code} on query={query!r}: {resp.text[:500]}"
        )

    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        """Paginated Text Search for one ``textQuery`` (plus metadata in *query*)."""
        api_key = query["api_key"]
        text_query = query["textQuery"]
        label = str(query.get("category_label", ""))
        domain = str(query.get("category_domain", ""))
        hits: list[RawHit] = []
        page_token: str | None = None
        for page_idx in range(MAX_PAGES_PER_CATEGORY):
            payload = self.request_text_search(api_key, text_query, page_token)
            for place in payload.get("places", []) or []:
                pid = place.get("id")
                if not pid:
                    continue
                disp = place.get("displayName") or {}
                name = disp.get("text") or ""
                loc = place.get("location") or {}
                raw = dict(place)
                raw["_discovery_category_label"] = label
                raw["_discovery_category_domain"] = domain
                raw["_discovery_page_index"] = page_idx
                hits.append(
                    RawHit(
                        source=self.source_name,
                        source_stable_id=pid,
                        name=name,
                        lat=loc.get("latitude"),
                        lng=loc.get("longitude"),
                        raw=raw,
                    )
                )
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
            time.sleep(PAGINATION_SLEEP_S)
        return hits

    def request_place_details(self, api_key: str, place_id: str) -> dict[str, Any]:
        url = PLACE_DETAILS_URL.format(place_id=place_id)
        headers = {
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": ENRICHMENT_FIELD_MASK,
        }
        with httpx.Client(timeout=30) as client:
            resp = self._enrichment_limiter.call_with_retry(
                lambda: client.get(url, headers=headers)
            )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return {"_error_status": 404, "_place_id": place_id}
        if resp.status_code in _RETRY_EXHAUSTED_STATUSES:
            raise RuntimeError(
                f"Places API: retries exhausted for place_id={place_id!r} "
                f"(last status {resp.status_code})"
            )
        raise RuntimeError(
            f"Places API error {resp.status_code} on place_id={place_id!r}: "
            f"{resp.text[:500]}"
        )

    def enrich(self, hit: RawHit) -> EnrichedHit:
        api_key = hit.raw.get("_api_key") or self._active_api_key
        if not api_key:
            raise RuntimeError(
                "GooglePlacesClient.enrich requires api_key on the hit raw dict "
                "('_api_key') or _active_api_key set (run_enrichment path)."
            )
        detail = self.request_place_details(api_key, hit.source_stable_id)
        return EnrichedHit(raw_hit=hit, enriched=detail)

    def dedupe_key(self, hit: RawHit) -> str:
        return hit.source_stable_id

    def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
        raw = hit.raw_hit.raw
        types = list(hit.enriched.get("types") or raw.get("types") or [])
        category_slug, place_type = map_google_types_to_slug_and_place_type(types)
        entity_kind = place_type if place_type in {"commercial", "place"} else "commercial"
        disp = hit.enriched.get("displayName") or raw.get("displayName") or {}
        name = disp.get("text") if isinstance(disp, dict) else None
        if not name:
            name = hit.raw_hit.name
        loc = hit.enriched.get("location") or raw.get("location") or {}
        editorial = hit.enriched.get("editorialSummary")
        desc: str | None = None
        if isinstance(editorial, dict):
            desc = editorial.get("text")
        elif isinstance(editorial, str):
            desc = editorial
        return EntityPayload(
            name=name,
            entity_type=entity_kind,
            lat=loc.get("latitude", hit.raw_hit.lat),
            lng=loc.get("longitude", hit.raw_hit.lng),
            address=hit.enriched.get("formattedAddress") or raw.get("formattedAddress"),
            phone=hit.enriched.get("nationalPhoneNumber"),
            website=hit.enriched.get("websiteUri"),
            description=desc,
            category_slug=category_slug,
            google_place_id=hit.raw_hit.source_stable_id,
            source=self.source_name,
            extension_payloads={"place_type": place_type},
        )

    def sweep_discovery(
        self,
        api_key: str,
        categories: list[dict[str, str]],
        output_dir: Path,
    ) -> dict[str, Any]:
        """Write discovery JSONL + summary (legacy ``sweep`` behavior)."""
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = output_dir / "discovery_raw.jsonl"
        unique_path = output_dir / "discovery_unique.jsonl"
        summary_path = output_dir / "discovery_summary.json"

        seen: dict[str, dict[str, Any]] = {}
        request_count = 0
        page_count_by_category: dict[str, int] = {}
        place_count_by_category: dict[str, int] = {}
        started_at = datetime.now(UTC).isoformat()

        with raw_path.open("w", encoding="utf-8") as raw_f:
            for cat in categories:
                label = cat["label"]
                domain = cat.get("domain", "")
                text_query = label + QUERY_SUFFIX
                page_token: str | None = None
                pages = 0
                cat_unique_added = 0

                for page_idx in range(MAX_PAGES_PER_CATEGORY):
                    body: dict[str, Any] = {"textQuery": text_query}
                    if page_token:
                        body["pageToken"] = page_token
                    headers = {
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": api_key,
                        "X-Goog-FieldMask": DISCOVERY_FIELD_MASK,
                    }
                    with httpx.Client(timeout=30) as client:
                        resp = self._discovery_limiter.call_with_retry(
                            lambda: client.post(
                                PLACES_TEXT_SEARCH_URL, headers=headers, json=body
                            )
                        )
                    request_count += 1
                    pages += 1
                    if resp.status_code != 200:
                        if resp.status_code in _RETRY_EXHAUSTED_STATUSES:
                            raise RuntimeError(
                                f"Places API: retries exhausted for query={text_query!r} "
                                f"(last status {resp.status_code})"
                            )
                        raise RuntimeError(
                            f"Places API error {resp.status_code} on query={text_query!r}: "
                            f"{resp.text[:500]}"
                        )
                    payload = resp.json()

                    raw_f.write(
                        json.dumps(
                            {
                                "ts": datetime.now(UTC).isoformat(),
                                "category_label": label,
                                "category_domain": domain,
                                "query": text_query,
                                "page_index": page_idx,
                                "response": payload,
                            }
                        )
                        + "\n"
                    )

                    for place in payload.get("places", []) or []:
                        pid = place.get("id")
                        if not pid:
                            continue
                        if pid not in seen:
                            seen[pid] = {
                                **place,
                                "_first_seen_category": label,
                                "_first_seen_domain": domain,
                                "_seen_categories": [label],
                            }
                            cat_unique_added += 1
                        else:
                            cats_seen: list[str] = seen[pid]["_seen_categories"]
                            if label not in cats_seen:
                                cats_seen.append(label)

                    page_token = payload.get("nextPageToken")
                    if not page_token:
                        break
                    time.sleep(PAGINATION_SLEEP_S)

                page_count_by_category[label] = pages
                place_count_by_category[label] = cat_unique_added
                print(
                    f"  [{label:30s}] {cat_unique_added:4d} new unique  "
                    f"({pages} page{'s' if pages != 1 else ''})",
                    flush=True,
                )

        with unique_path.open("w", encoding="utf-8") as unique_f:
            for place in seen.values():
                unique_f.write(json.dumps(place) + "\n")

        finished_at = datetime.now(UTC).isoformat()
        summary = {
            "started_at": started_at,
            "finished_at": finished_at,
            "request_count": request_count,
            "unique_place_count": len(seen),
            "categories_run": len(categories),
            "page_count_by_category": page_count_by_category,
            "unique_count_by_category": place_count_by_category,
            "raw_path": str(raw_path),
            "unique_path": str(unique_path),
        }
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        summary["summary_path"] = str(summary_path)
        return summary

    def run_discovery(
        self,
        *,
        category: str | None,
        dry_run: bool,
        categories_path: Path,
        output_dir: Path,
        api_key: str,
    ) -> dict[str, Any]:
        """Entry point for ``scripts.places_discovery`` — writes JSONL + summary."""
        categories = load_categories_for_discovery(
            categories_path, dry_run=dry_run, category_slug=category
        )
        return self.sweep_discovery(api_key, categories, output_dir)

    @staticmethod
    def extract_zip(addr_components: list[dict[str, Any]] | None) -> str | None:
        if not addr_components:
            return None
        for comp in addr_components:
            types = comp.get("types", []) or []
            if "postal_code" in types:
                return comp.get("longText") or comp.get("shortText")
        return None

    @staticmethod
    def flatten_review(review: dict[str, Any]) -> dict[str, Any]:
        text_field = review.get("text")
        if isinstance(text_field, dict):
            text = text_field.get("text")
        else:
            text = text_field
        author = review.get("authorAttribution") or {}
        return {
            "author": author.get("displayName"),
            "rating": review.get("rating"),
            "text": text,
            "publish_time": review.get("publishTime"),
        }

    def build_enriched_row(
        self,
        place_id: str,
        payload: dict[str, Any],
        discovery_meta: dict[str, Any],
    ) -> dict[str, Any]:
        location = payload.get("location") or {}
        return {
            "place_id": place_id,
            "display_name": (payload.get("displayName") or {}).get("text"),
            "formatted_address": payload.get("formattedAddress"),
            "zip": self.extract_zip(payload.get("addressComponents")),
            "phone": payload.get("nationalPhoneNumber"),
            "website": payload.get("websiteUri"),
            "primary_type": payload.get("primaryType"),
            "types": payload.get("types") or [],
            "lat": location.get("latitude"),
            "lng": location.get("longitude"),
            "rating": payload.get("rating"),
            "review_count": payload.get("userRatingCount"),
            "review_snippets": [
                self.flatten_review(r) for r in (payload.get("reviews") or [])
            ],
            "photo_refs": [p.get("name") for p in (payload.get("photos") or [])],
            "regular_opening_hours": payload.get("regularOpeningHours"),
            "address_components": payload.get("addressComponents"),
            "_seen_categories": discovery_meta.get("_seen_categories", []),
            "_first_seen_category": discovery_meta.get("_first_seen_category"),
            "_first_seen_domain": discovery_meta.get("_first_seen_domain"),
        }

    def load_processed_ids(self, enriched_path: Path) -> set[str]:
        if not enriched_path.exists():
            return set()
        ids: set[str] = set()
        for line in enriched_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                pid = row.get("place_id")
                if pid:
                    ids.add(pid)
            except json.JSONDecodeError:
                continue
        return ids

    def run_enrichment(
        self,
        *,
        input_path: Path,
        output_dir: Path,
        limit: int | None,
        api_key: str,
    ) -> dict[str, Any]:
        """Entry point for ``scripts.places_enrichment`` — append JSONL + summary."""
        places = [
            json.loads(line)
            for line in input_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if limit is not None:
            places = places[:limit]
        prev = self._active_api_key
        self._active_api_key = api_key
        try:
            return self.enrich_places_to_disk(api_key, places, output_dir)
        finally:
            self._active_api_key = prev

    def enrich_places_to_disk(
        self,
        api_key: str,
        places: list[dict[str, Any]],
        output_dir: Path,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = output_dir / "enrichment_raw.jsonl"
        enriched_path = output_dir / "enrichment_enriched.jsonl"
        summary_path = output_dir / "enrichment_summary.json"

        already_done = self.load_processed_ids(enriched_path)
        if already_done:
            print(
                f"[enrichment] resume: {len(already_done)} place(s) already enriched, "
                "skipping those",
                flush=True,
            )

        started_at = datetime.now(UTC).isoformat()
        success = 0
        skipped = 0
        errors_404 = 0
        other_errors = 0

        with raw_path.open("a", encoding="utf-8") as raw_f, enriched_path.open(
            "a", encoding="utf-8"
        ) as enriched_f:
            for idx, place in enumerate(places, start=1):
                pid = place.get("id")
                if not pid:
                    continue
                if pid in already_done:
                    skipped += 1
                    continue

                try:
                    payload = self.request_place_details(api_key, pid)
                except Exception as exc:
                    other_errors += 1
                    raw_f.write(
                        json.dumps(
                            {
                                "ts": datetime.now(UTC).isoformat(),
                                "place_id": pid,
                                "_error": str(exc),
                            }
                        )
                        + "\n"
                    )
                    raw_f.flush()
                    if idx % PROGRESS_EVERY == 0:
                        print(
                            f"  [{idx:4d}/{len(places)}] success={success} "
                            f"errors={other_errors + errors_404} skipped={skipped}",
                            flush=True,
                        )
                    continue

                if payload.get("_error_status") == 404:
                    errors_404 += 1
                    raw_f.write(
                        json.dumps(
                            {
                                "ts": datetime.now(UTC).isoformat(),
                                "place_id": pid,
                                "_error_status": 404,
                            }
                        )
                        + "\n"
                    )
                    raw_f.flush()
                    continue

                success += 1
                raw_f.write(
                    json.dumps(
                        {
                            "ts": datetime.now(UTC).isoformat(),
                            "place_id": pid,
                            "response": payload,
                        }
                    )
                    + "\n"
                )
                raw_f.flush()

                row = self.build_enriched_row(pid, payload, place)
                enriched_f.write(json.dumps(row) + "\n")
                enriched_f.flush()

                if idx % PROGRESS_EVERY == 0:
                    print(
                        f"  [{idx:4d}/{len(places)}] success={success} "
                        f"errors={other_errors + errors_404} skipped={skipped}",
                        flush=True,
                    )

        finished_at = datetime.now(UTC).isoformat()
        summary = {
            "started_at": started_at,
            "finished_at": finished_at,
            "input_count": len(places),
            "success_count": success,
            "skipped_count": skipped,
            "errors_404": errors_404,
            "other_errors": other_errors,
            "raw_path": str(raw_path),
            "enriched_path": str(enriched_path),
        }
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        summary["summary_path"] = str(summary_path)
        return summary


def enrichment_row_to_entity_payload(row: dict[str, Any]) -> EntityPayload:
    """Map ``enrichment_enriched.jsonl`` row dict to :class:`EntityPayload` for reconciler.

    Used by :mod:`scripts.places_load` before catalog writes (Phase 4.3).
    """
    types = list(row.get("types") or [])
    name = str(row.get("display_name") or "")
    pid = str(row.get("place_id") or "")
    lat = row.get("lat")
    lng = row.get("lng")
    raw: dict[str, Any] = {
        "types": types,
        "displayName": {"text": name},
        "location": {"latitude": lat, "longitude": lng},
        "formattedAddress": row.get("formatted_address"),
    }
    enriched: dict[str, Any] = {
        "types": types,
        "displayName": {"text": name},
        "location": {"latitude": lat, "longitude": lng},
        "formattedAddress": row.get("formatted_address"),
        "nationalPhoneNumber": row.get("phone"),
        "websiteUri": row.get("website"),
        "editorialSummary": None,
    }
    raw_hit = RawHit(
        source="google_places",
        source_stable_id=pid,
        name=name,
        lat=lat,
        lng=lng,
        raw=raw,
    )
    return GooglePlacesClient().to_entity_payload(
        EnrichedHit(raw_hit=raw_hit, enriched=enriched)
    )

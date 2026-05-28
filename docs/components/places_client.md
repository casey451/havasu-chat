# places_client

`app/contrib/places_client.py` (~192 lines)

## Purpose

Thin **Google Places API (New) Text Search** client used for **provider contribution enrichment**: resolve a submitted business name (plus fixed Arizona location bias) to a **`place_id`**, normalized fields, and optional **`regularOpeningHours`** JSON for admin review and downstream **`hours_helper`** structuring.

## Public surface

**`PLACES_SEARCH_URL`** — POST endpoint **`https://places.googleapis.com/v1/places:searchText`**.

**`PLACES_FIELD_MASK`** — Explicit field mask string (no wildcard) limiting billed/exposed fields: id, displayName, formattedAddress, internationalPhoneNumber, regularOpeningHours, websiteUri, types, location, businessStatus.

**`PlacesLookupResult` dataclass** — Stable result envelope:

- **`status`**: `"success"` \| `"no_match"` \| `"low_confidence"` \| `"error"` \| `"not_attempted"`
- Populated place fields when search succeeds (`place_id`, `display_name`, `formatted_address`, `phone`, `website_uri`, `regular_opening_hours`, `types`, `location`, `business_status`)
- **`raw_response`** — Dict snapshot when useful for audit/debug
- **`error_message`** — Human/diagnostic string on failure paths
- **`queried_at`** — Naive UTC-ish timestamp via **`_naive_utc_now()`**

**`lookup_provider(name: str, location_context: str = "Lake Havasu City, AZ", *, timeout_seconds: float = 15.0) -> PlacesLookupResult`** — Builds **`textQuery = "{name} {location_context}"`**, POSTs with API key + field mask, picks **first** result, scores display-name similarity.

## Inputs and outputs

**Happy path.** HTTP 2xx JSON with non-empty **`places`** list → flatten first element → compute **normalized Levenshtein distance** between submission name and Places display name → **`success`** if **distance < 0.3**, else **`low_confidence`**.

**Empty API key.** Logs warning, returns **`not_attempted`**.

**Empty name.** Returns **`no_match`** with empty marker in **`raw_response`**.

**HTTP/network failures.** Maps timeouts, transport errors, non-JSON, and HTTP status outside 2xx into **`error`** with coded **`error_message`**.

## Internal structure

- **`_display_name_text(place)`** — Unwraps **`displayName.text`** or string fallback.
- **`_place_to_flat`** — Shallow copy helper for edge fallback payloads.
- **`rapidfuzz.distance.Levenshtein.normalized_distance`** — Confidence gate vs submission query string.

## Conventions

**Cost discipline.** Field mask is explicit — expanding fields requires updating **`PLACES_FIELD_MASK`** and reviewing billing/PII posture.

**First-hit bias.** Always trusts **`places[0]`** — query quality depends on Places ranking.

**Naive timestamps.** **`queried_at`** strips tzinfo to align with DB TIMESTAMP-without-time-zone patterns elsewhere.

## Known limitations

**Single-result heuristic.** No disambiguation UI when multiple venues match.

**Levenshtein threshold `0.3`** is a magic constant — tuning affects **`low_confidence`** vs **`success`** and thus **`enrichment_suggests_verified`** in **`approval_service`**.

**No caching / rate limiting** — Every call hits the network; background enrichment multiplies traffic.

## Configuration

**`GOOGLE_PLACES_API_KEY`** — Read at call time via **`os.getenv`**. Empty → **`not_attempted`**.

**Photo URLs:** Browser-renderable Google photo URLs for provider hero/gallery are built at read time by **`app/providers/photo_urls.py`** (`google_photo_url`), which constructs Places Photo Media URLs from stored `google_photo_refs` resource names. No server-side HTTP fetch — the browser follows Google's redirect to the CDN.

## Related

**Direct callers:**

- **`app/contrib/enrichment.py`** — **`lookup_provider`** for provider contributions.

**Tests:** **`tests/test_places_client.py`** (HTTP mocking).

**Downstream:** **`docs/components/hours_helper.md`**, **`docs/components/enrichment.md`**, **`docs/components/approval_service.md`**, **`app/providers/photo_urls.py`** (Photo Media URL helper for provider images).

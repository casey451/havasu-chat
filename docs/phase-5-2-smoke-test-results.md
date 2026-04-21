# Phase 5.2 — Production smoke test results

**Date:** 2026-04-20  
**How it was run:** `railway run .\.venv\Scripts\python.exe scripts/smoke_phase52_contributions.py` so `ADMIN_PASSWORD` and `GOOGLE_PLACES_API_KEY` were injected from the linked Railway service.

---

## Results

| Step | Outcome |
|------|--------|
| Admin login | OK (`302` + session cookie) |
| `POST /admin/contributions` | **201** — created contribution **`id=1`** |
| After **8s** wait | `GET /admin/contributions/1` returned **200** |

### Enrichment fields (after wait)

- **`url_fetch_status`:** `'error'` — HTTP metadata fetch did not succeed (`url_title` / `url_description` remained `None`; `url_fetched_at` was set).
- **`google_place_id`:** Populated (`ChIJU0RYTjDv0YARo3_aGhU_j_8`).
- **`google_enriched_data`:** Populated with expected keys: `lookup_status`, `place_id`, `display_name`, `formatted_address`, `phone`, `website_uri`, `regular_opening_hours`, `types`, `location`, `business_status`, `places_api_response`.

**Interpretation:** **Google Places on production works end-to-end** after deploy. The URL branch failed once (typical causes: site blocking datacenter IPs, TLS/SNI quirks, or a non-HTML response). Check Railway logs if you need the exact fetch failure; it does not invalidate Places verification.

---

## Reusable smoke script

**Path:** `scripts/smoke_phase52_contributions.py`

**Defaults**

- Base URL: `https://havasu-chat-production.up.railway.app`
- Wait after create: **8** seconds (`HAVASU_SMOKE_WAIT`)

**Environment**

- **`ADMIN_PASSWORD`** — required (provided automatically under `railway run`).
- **`GOOGLE_PLACES_API_KEY`** — optional for the script; enrichment degrades if unset.

**Overrides**

- `HAVASU_SMOKE_BASE` — alternate base URL  
- `HAVASU_SMOKE_WAIT` — seconds to wait before `GET`

**Run again**

```bash
railway run .\.venv\Scripts\python.exe scripts/smoke_phase52_contributions.py
```

(On Unix-style shells, adjust the path to the venv Python as needed.)

---

## Request body used (reference)

```json
{
  "entity_type": "provider",
  "submission_name": "Altitude Trampoline Park",
  "submission_url": "https://altitudetrampolinepark.com/lake-havasu-city",
  "source": "operator_backfill"
}
```

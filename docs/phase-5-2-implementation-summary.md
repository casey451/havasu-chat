# Phase 5.2 — Implementation summary (for Claude / owner review)

**Date:** 2026-04-20  
**Status:** Implemented locally; **not committed** until you reply `approved, commit and push`.

---

## Pre-flight

| Check | Result |
|--------|--------|
| **1** | **PASS** — `200f545 Phase 5.1: Contribution data model + admin backend` appears in the last 20 commits on `main`. |
| **2** | **PASS** — All six enrichment columns exist on `Contribution` in `app/db/models.py` (`url_title`, `url_description`, `url_fetch_status`, `url_fetched_at`, `google_place_id`, `google_enriched_data`). |
| **3** | **PASS** — `GOOGLE_PLACES_API_KEY` is read with `(os.getenv(...) or "").strip()`, same pattern as `ANTHROPIC_API_KEY` in `tier3_handler.py`. |
| **4** | **PASS** — **`httpx`** and **`beautifulsoup4`** are already in `requirements.txt`; **no new dependencies**. |

---

## What was built

- **`app/contrib/url_fetcher.py`** — `fetch_url_metadata()`: 10s timeout, up to 3 redirects, private/reserved IP blocking (SSRF), 5 MB body cap, only `text/html` and `application/xhtml+xml`, OpenGraph → `<title>` / meta description, length caps (300 / 1000), fixed User-Agent string.
- **`app/contrib/places_client.py`** — `lookup_provider()`: POST to `https://places.googleapis.com/v1/places:searchText` with `X-Goog-Api-Key` and `X-Goog-FieldMask` exactly as specified (comma-separated, no spaces). Uses **RapidFuzz Levenshtein normalized distance &lt; 0.3** vs. `displayName.text` for **success** vs **low_confidence**. Missing API key → **`not_attempted`**, warning log, **no HTTP**.
- **`app/contrib/enrichment.py`** — `enrich_contribution(contribution_id: int, session_factory)`: DB primary key is **integer** (spec text said `str`; implementation matches ORM). Runs URL enrichment if `submission_url` is set; runs Places only if `entity_type == "provider"`. Fresh DB session per task; commits after the URL step and again after the Places step.
- **`app/api/routes/admin_contributions.py`** — Injects **`BackgroundTasks`** on `POST /admin/contributions` to schedule enrichment after the row is created. Adds **`POST /admin/contributions/{id}/enrich`** returning **202** with JSON `{"contribution_id", "enrichment": "scheduled"}`.

---

## Tests

- **`tests/test_url_fetcher.py`** — 9 cases (mocked `httpx`).
- **`tests/test_places_client.py`** — 7 cases (mocked `httpx`).
- **`tests/test_enrichment.py`** — 6 cases (mocked fetch + places, real DB session).
- **`tests/test_admin_contributions_api.py`** — 3 new cases (background task scheduled, manual enrich, 404 on missing id).

All external HTTP is **mocked** in tests.

---

## Verification

| Command | Result |
|---------|--------|
| `pytest tests/` | **577 passed** (552 baseline + 25 new). |
| `scripts/run_query_battery.py` | **116 / 120** matches (four `"match": false` — same pattern as prior baseline on the script’s production URL). |

---

## Notes / STOP-and-ask (documented)

1. **Contribution ID type:** Prompt used `contribution_id: str` for the background task; the database uses an **integer** PK — implementation uses **`int`** everywhere for that ID.
2. **Place Details vs Text Search:** The prompt title mentioned “Place Details”; the behavioral section only specified **Text Search (New)** with a field mask — implementation is **searchText only** (rich fields come from the search response).

---

## Related doc

A longer report (field mask string, sample `google_enriched_data` JSON, file list, intended commit message) lives in:

**`docs/phase-5-2-completion-report.md`**

---

## Next step (owner)

When satisfied, reply:

**`approved, commit and push`**

Commit message (verbatim):

```text
Phase 5.2: URL validation + Google Places integration
```

Then a single push to `main`, leaving the `Made-with: Cursor` trailer unchanged (no amends, no hook bypass).

Phase **5.3** should only start after you separately confirm production is ready.

# enrichment

`app/contrib/enrichment.py` (~78 lines)

## Purpose

**Background contribution enrichment:** after a `Contribution` row exists, asynchronously fetch **URL metadata** (title/description) and, for **provider** submissions, run a **Google Places text search** by submission name. Persists results onto the same `Contribution` (`url_*`, `google_place_id`, `google_enriched_data`). Intended for operator review quality (`admin_contributions_html`) and for `enrichment_suggests_verified` inside **`approval_service`**.

## Public surface

**`enrich_contribution(contribution_id: int, session_factory: Callable[[], Session]) -> None`** — Side-effect-only entry. Opens a **fresh** SQLAlchemy session via `session_factory()`, loads the contribution by id, applies enrichment steps, commits incrementally, then closes the session. Does **not** return a value; callers use FastAPI `BackgroundTasks` or equivalent fire-and-forget scheduling.

**`_serialize_places_result(pl) -> dict[str, Any]`** — Module-private helper building the JSON-serializable blob stored in `google_enriched_data` from a **`PlacesLookupResult`** (duck-typed: expects `.status`, `.place_id`, `.display_name`, `.formatted_address`, `.phone`, `.website_uri`, `.regular_opening_hours`, `.types`, `.location`, `.business_status`, optional `.raw_response`). Drops `None` fields; may nest raw Places payload under `"places_api_response"` when available.

## Inputs and outputs

**Inputs.**

- `contribution_id` — PK of `Contribution`; missing rows log at INFO and return early.
- `session_factory` — Typically **`SessionLocal`** from `app.db.database` so background work does not reuse the request-scoped session.

**Outputs / side effects.**

1. If `submission_url` is non-empty: **`fetch_url_metadata`** → writes `url_title`, `url_description`, `url_fetch_status`, `url_fetched_at`; **`db.commit()`**.
2. If `entity_type == "provider"`: **`lookup_provider(submission_name)`** → on `"success"` or `"low_confidence"` writes `google_place_id` and structured **`google_enriched_data`**; otherwise writes a small error/status dict with **no** `place_id`; **`db.commit()`**.

**Failure behavior.** Any unexpected exception: **`logger.exception`**, **`db.rollback()`** (best-effort), session closed in **`finally`**. Partial progress may remain committed from an earlier successful step within the same call.

## Internal structure

Linear orchestration in one try-block:

1. `db.get(Contribution, contribution_id)` guard.
2. URL branch → **`url_fetcher.fetch_url_metadata`**.
3. Provider-only Places branch → **`places_client.lookup_provider`** → **`_serialize_places_result`** or error-shaped dict.

No classes; logging uses module **`__name__`** logger.

## Conventions

**Separate session per invocation.** Background tasks must not hold onto HTTP request sessions.

**Two commits per successful path.** URL enrichment commits before Places starts — Places failure can leave URL fields populated.

**Places status acceptance mirrors approval helper.** `"success"` and `"low_confidence"` both produce catalog-grade enrichment blobs; other statuses still persist diagnostic JSON.

## Known limitations

**Programs/events skip Places.** Only `entity_type == "provider"` triggers **`lookup_provider`**.

**No idempotency guard.** Re-running enrichment overwrites fields; callers should gate externally if duplicates matter.

**Tip approvals skip this module** — enrichment targets submission URLs and provider names, not free-form tips without URLs.

## Configuration

Indirect only:

- **`fetch_url_metadata`** — no env vars in enrichment; SSRF and HTTP caps live in **`url_fetcher`**.
- **`lookup_provider`** — **`GOOGLE_PLACES_API_KEY`** via **`places_client`**.

## Related

**Direct callers:**

- **`app/api/routes/contribute.py`** — schedules enrichment after public **`ContributionCreate`**.
- **`app/api/routes/admin_contributions.py`** — POST enrich endpoint + post-create hook.
- **`app/api/routes/admin_mentions.py`** — after mention promotion creates a contribution.
- **`app/admin/mentions_html.py`** — promote POST schedules enrichment.

**Dependencies:**

- **`docs/components/url_fetcher.md`**, **`docs/components/places_client.md`**
- **`docs/components/approval_service.md`** — consumes enrichment signals via **`enrichment_suggests_verified`**.

**Tests:** **`tests/test_enrichment.py`**.

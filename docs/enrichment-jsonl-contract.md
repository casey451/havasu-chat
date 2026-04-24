# Enrichment JSONL contract (v1)

## 1. Purpose and scope

This document is the **interface contract** between the external `havasu-enrichment` pipeline and the chat app’s Google bulk ingest (`app/contrib/google_bulk_ingest.py`, invoked via `scripts/google_bulk_ingest.py`). It defines field names, types, required vs optional fields, null semantics, matching and idempotency rules, and columns the ingest must not overwrite. The **executable** behavior (including edge cases) lives in the Python module; this file is the **reviewable** spec for humans and for emitters. **Current version: v1.**

## 2. Versioning

**Doc-level versioning only** for v1. Breaking changes to this contract **bump the version** and are reflected in this file. There is **no** `schema_version` field in the JSONL at v1; add one in a later version if needed.

## 3. File format

- **One JSON object per line** (JSONL).
- **UTF-8** encoding.
- **Empty lines** are skipped.
- **Malformed lines** (invalid JSON) or **non-object** lines (e.g. JSON `null` or an array) are **logged to stderr and skipped** without aborting the run.

## 4. Required fields

| Column | Type | Constraint |
|--------|------|------------|
| `google_place_id` | string | Non-empty after leading/trailing whitespace is stripped. |
| `provider_name` | string | Non-empty after strip. |
| `category` | string | Non-empty after strip. |

Rows that fail required-field validation are **skipped** and counted in `skipped_missing_required` (see the ingest run summary).

## 5. Optional fields

| Column | Type | Target `Provider` column | Notes |
|--------|------|---------------------------|--------|
| `description` | string or null | `description` | |
| `address` | string or null | `address` | |
| `phone` | string or null | `phone` | |
| `email` | string or null | `email` | |
| `website` | string or null | `website` | |
| `facebook` | string or null | `facebook` | |
| `hours` | string or null | `hours` | |
| `hours_structured` | object or null | `hours_structured` (JSON) | **Must be a JSON object or null.** The reference ingest stores non-dict, non-null values as-is; emitters must still emit only objects or null. See [known-issues](known-issues.md). |
| `lat` | number or null | `lat` | |
| `lng` | number or null | `lng` | |
| `match_confidence` | number or null | `match_confidence` | |
| `enrichment_version` | string or null | `enrichment_version` | |
| `raw_enrichment_json` | object or null | `raw_enrichment_json` (JSON) | **Same rule as `hours_structured`:** object or null only per spec. |

## 6. Unknown fields

Keys **outside** the allowlist in sections 4–5 are **silently dropped** by the ingest. This is **intentional** forward-compatibility: emitters may attach extra keys for their own pipeline without breaking ingestion. **Do not** rely on unknown fields being persisted in Postgres.

## 7. Idempotency and matching

Processing order for each **accepted** line (after required-field validation and in-file de-dupe by `google_place_id`):

1. If a `Provider` row exists with the same `google_place_id` → **update** that row.
2. Else if a `Provider` row exists with a **matching normalized** `provider_name` (same algorithm as seed normalization) → **update** that row and set `google_place_id` from the JSONL line.
3. Else → **insert** a new `Provider` with `source="google_bulk_import"`, `draft=False`, `verified=False`, `is_active=True`, `pending_review=False`.

## 8. Duplicates within a file

**First** occurrence of a given `google_place_id` wins. Later lines with the same id are **skipped** and counted in `skipped_duplicate_in_file`.

## 9. Protected columns

The ingest **never** writes the following columns from JSONL, regardless of keys present: `embedding`, `id`, `created_at`, `draft`, `verified`, `is_active`, `pending_review`, `tier`, `sponsored_until`, `featured_description`, `admin_review_by`.

`updated_at` is **always** updated when a row is applied. **`embedding`** is filled by the Phase **8.11c** backfill script (`scripts/google_bulk_embed.py`), not by the ingest.

## 10. Error handling

Each row is processed inside a **per-row** `try`/`except` with a **nested** transaction. Row-level failures increment an **`errors`** counter, print a **traceback to stderr**, and do **not** stop the run. Coercion failures (e.g. `float()` on `lat` / `lng` / `match_confidence` when a non-numeric value is provided) follow this error path.

## 11. Example row

```json
{"google_place_id":"ChIJN1t_tDeuEmsRUsoyG83frY4","provider_name":"Example Coffee Roasters","category":"Dining & Drinks","description":"Local roaster and pour-over bar.","address":"201 English Village, Lake Havasu City, AZ 86403","phone":"+1 928-555-0100","email":null,"website":"https://example.com","facebook":null,"hours":"Mon–Sat 7am–2pm; Sun closed","hours_structured":{"weekdayDescriptions":["Monday: 7:00\u202fAM \u2013 2:00\u202fPM"]},"lat":34.4689,"lng":-114.3215,"match_confidence":0.92,"enrichment_version":"havasu-enrichment-2026-04","raw_enrichment_json":{"source":"google_places","fetched":"2026-04-24"}}
```

## 12. Cross-references

- **Implementation:** `app/contrib/google_bulk_ingest.py` — parser, allowlist, apply logic, counters, and commits.
- **Drift / backlog:** `docs/known-issues.md` — current notes where spec and code may differ or where related docs are outdated.

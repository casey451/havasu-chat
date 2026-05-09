# Business enrichment template

This folder is for the operator-driven enrichment sprint. Each row in
`business_enrichment_template.csv` represents one Lake Havasu business that
will be inserted or updated in the catalog.

If you can fill out a spreadsheet, you can do this. Read this once before
your first batch.

## How to fill the template

1. Open `business_enrichment_template.csv` in Excel, Google Sheets, or any
   spreadsheet tool.
2. Delete the example comment row near the top (the two lines starting with
   `#`). Keep the header row.
3. Add one row per business. Save back as CSV (UTF-8).
4. Don't rename columns. Don't reorder them. Extra columns will be ignored.

## What each column means

- **provider_name** — the business name as it should appear to readers.
  Capitalize it normally ("Havasu Pool Pros", not "HAVASU POOL PROS").
- **category** — pick exactly one slug from the allowed list below.
- **address** — full street address with city and zip. Example:
  `2200 N McCulloch Blvd, Lake Havasu City, AZ 86403`. Required.
- **phone** — 10 digits, North American format. You can paste with or without
  punctuation; the validator strips it. `(928) 555-0133`, `928-555-0133`,
  and `9285550133` all work.
- **owner_email** — a real, monitored inbox for the owner or manager. Used
  for the claim flow once we ship it. Standard email shape.
- **website** — full URL with `https://` (or `http://`). Optional but
  encouraged.
- **hours** — free-text, human-readable. Example: `Mon-Fri 8am-5pm; Sat 9am-1pm`.
  We'll structure these later. Keep it short.
- **hava_voice_description** — 2 to 3 sentences in Hava's voice. Plain,
  warm, specific. Mention what they actually do and one local detail
  (neighborhood, how long they've been around, what they're known for).
  Must be between 80 and 400 characters total.
- **last_verified_at** — the date and time you confirmed the info, in
  ISO-8601 format with a timezone offset. Example: `2026-05-08T09:30:00-07:00`.
  Lake Havasu is `-07:00` year round (no daylight saving). Cannot be in
  the future.
- **verification_method** — exactly one of:
  - `phone_call` — you called the business and confirmed verbally
  - `in_person` — you visited the business
  - `web_form_submission` — the owner filled out a verification form
  - `email_confirmation` — the owner replied to your email confirming details

  The database CHECK constraint allows these four operator values **plus**
  legacy catalog values (`manual`, `scraper`, `owner_confirmed`,
  `npi_registry`, `none`). Ingest writes your CSV value to the database
  verbatim so phone vs in-person (etc.) stays auditable.

## Allowed category slugs

Use the exact lowercase slug. Common ones for this sprint:

- `food_drink` — restaurants, bars, cafes
- `home_services` — plumbers, HVAC, pool service, cleaning, contractors
- `auto` — auto repair, tire shops, body shops
- `boat_repair` — boat repair shops
- `boat_rental` — boat rentals
- `health_medical` — urgent care, clinics, dentists
- `professional_services` — anything that doesn't fit elsewhere
- `retail`, `lake_recreation`, `beauty_personal_care`, `religion_community`,
  `fitness_sports`, `general_contractor`, `real_estate`, `insurance`,
  `financial`, `legal`, `event_venue`, `lodging`, `tourism`, `education`,
  `pet`

If you're unsure, leave a note and ask.

## What the validator will reject

The validator checks every row before any database write. It will REJECT a
row and refuse to ingest the file if any of these are true:

- A required column is missing or empty.
- `phone` doesn't have exactly 10 digits, OR it matches the NANP
  placeholder pattern `(NXX) 555-01XX` (those are reserved fake numbers).
- `category` isn't in the allowed list above.
- `address` is empty.
- `last_verified_at` doesn't parse as ISO-8601 OR is in the future.
- `verification_method` isn't one of the four allowed values.
- `hava_voice_description` is shorter than 80 characters or longer than 400.
- `owner_email` doesn't match a basic `name@host.tld` shape.

The validator prints a per-row PASS or FAIL report. If anything fails,
nothing gets written to the database — fix the rows and re-run.

## How to run the validator

From the repo root:

```
python scripts/ingest/validate_enrichment_csv.py path/to/your_filled.csv
```

Exit code is 0 if everything passes, non-zero if anything failed. Read the
output and fix the flagged rows.

## How to run the ingest

Once the validator passes cleanly, run the ingest. It calls the validator
again as a safety check; if validation fails, ingest refuses to run.

Dry run first (no DB writes — just prints what it would do):

```
python scripts/ingest/ingest_enrichment_csv.py path/to/your_filled.csv --dry-run
```

For real:

```
python scripts/ingest/ingest_enrichment_csv.py path/to/your_filled.csv
```

The ingest is idempotent — running the same file twice is safe. The script
matches existing Providers by `provider_name` + `category` (case-insensitive).
If a match exists, the enrichment fields are updated. If not, a new
Provider is inserted.

Every row prints one of: `INSERT`, `UPDATE`, or `SKIP-NOOP`, along with
the Provider id. If any row errors, the entire transaction rolls back so
your database is never left half-updated.

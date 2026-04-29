# Multi-day events — Step 5 backfill (design)

Design-only document: local backfill approach for `events.end_date` / `contributions.event_end_date` from the first `Date:` line. No production commands, no backfill runs, no commits — for implementation after review.

**References:** `docs/multiday-events-design-step1.md`, `app/contrib/river_scene.py` (`_format_date_heading`, `normalize_to_contribution`), `scripts/approve_pending_river_scene.py`, `app/chat/tier2_db_query.py` (overlap on `coalesce(Event.end_date, Event.date)`).

---

## Protocol — agent confirmation (session rules)

- **Production / Railway:** No `railway` (or any deployed touch) unless the human types **approved** or **go** first; propose first for reads on deployed if the session protocol requires it.
- **Git:** No `commit` or `push` without explicit human approval; staging and proposed message may be drafted, then stop.
- **Local files:** Inspecting the repo (read, search) is free; **changing** files needs a proposed change set and approval.
- **Schema/data on production:** Migration and production backfill are run by the operator; agent drafts commands only.
- **Empty or surprising command output** is a finding, not success.
- **Steps do not chain** unless the human approves the next step.

---

## Context (read for Step 5)

- **Backfill** is a **separate script** (not in Alembic). Critical path is **`events.end_date`** parsed from the first `Date:` line. **`contributions.event_end_date`** is optional but recommended for consistency.
- **Canonical text shapes** from `_format_date_heading`: single day; same month multi-day with en-dash `–` between day numbers; cross-month with two full month-day-year segments.
- **Models:** `Event` has `date` + nullable `end_date`; `Contribution` has `event_date` + nullable `event_end_date`.
- **Retrieval** already uses range overlap; multi-day is wrong until `events.end_date` is populated for historical rows.

---

# Step 5 design proposal

### 1. Format survey approach

- **Universe:** Rows to characterize: **`events` with `source = 'river_scene_import'`** (local count may be ~71 or per seed). Approved events store the same prose in **`Event.description`** as historical **`submission_notes`**, and the first **`Date:`** line is the target. In current normalizer output, that line is the **first line** of the notes.
- **Method (read-only):**
  - Extract the first line matching `^Date:\s*(.+)\s*$` (case-insensitive for `Date:`) from `events.description` (or join `contributions` on `created_event_id` and use `submission_notes` — they should match; mismatches are a finding).
  - **Bucket** the string after `Date: ` for duplicate detection: e.g. `GROUP BY` normalized “shape” (single full date vs. `Month d–d, Y` vs. cross-month `...–...`) and **count**; list **rare** buckets and any rows with no `Date:` line or empty payload.
  - **Sample:** For each bucket, keep **1–2 examples** (ids/titles) plus any **unclassified** lines.
  - **Optional hygiene:** Count ASCII `-` vs Unicode en-dash `–` in the range part and whitespace variants — informs tokenizer rules without hand-reading every full description.

This remains **read-only** and only characterizes what the parser must accept.

### 2. Parser design

- **Input:** The first **`Date:`** line’s value, or `description` with “take first `Date:` line.”
- **Formats to handle (aligned with `_format_date_heading` + drift):**
  - **Single day:** `May 7, 2026` (tolerate spacing / padding quirks in legacy rows).
  - **Same month, same year, day span:** `May 7–9, 2026` — en-dash, hyphen, or space-dash variants.
  - **Cross-month (and cross-year if needed):** `May 31, 2026 – June 2, 2026` — two full `Month d, Y` parts; normalize separator in a pre-pass.
- **Output:** Inclusive **(start_date, end_date)**; for backfill, **inclusive `end_date`**. If the range is a single calendar day, the script may set **`end_date = NULL`** to match the **single-day amendment** (NULL when end equals start, not a duplicate of `date`).
- **Validation:** Require **`end_parsed >= start_parsed`**. Cross-check start against `events.date` (prefer **DB `events.date` as source of truth** if text disagrees; log and skip or reconcile explicitly).
- **Failure modes:** On missing line, unparseable text, or failed validation: **no update**; log event id, title snippet, raw line, reason. Do not overwrite a correct existing `end_date` without an explicit **force** flag (see idempotency).

### 3. Backfill script structure

- **Primary table:** **`events`:** `UPDATE` **`end_date`** so retrieval sees the range. Inclusive end **after** `events.date` becomes non-NULL; single-day events stay **NULL** per amendment.
- **Contributions:** For matching rows (`contributions.created_event_id = events.id`), set **`event_end_date`** to the same value as the event (NULL for single-day).
- **Scope:** Filter **`source = 'river_scene_import'`**; optionally only rows where `end_date IS NULL` or only when computed end differs from current.
- **Idempotency:** Recompute desired `end_date`; if **already equal, skip**. Failed parses leave DB unchanged. No deletes. Optional **`--dry-run`**: print actions, no writes.

### 4. Verification plan

- **Data spot-checks (local):** After backfill, verify **Won Bass Havasu**, **Pro Watercross**, and a cross-month example: **`events.date`**, **`events.end_date`**, and **`contributions.event_end_date`** where linked.
- **Retrieval (Tier 2):**
  - **Pre-backfill** (overlap code in place, `end_date` still NULL for old multi-day): a **middle day** in a known range should **not** surface the event (or match pre-fix “miss” behavior).
  - **Post-backfill:** the **same** date/query should **include** the event.
- **How:** Local stack, unified router → Tier 2, date-specific question; unit coverage in **`tests/test_tier2_db_query.py`** (middle-day / multi-day) is the behavioral contract; manual chat is a smoke on top.

---

**HALT:** Step 5 implementation (survey tool, parser, backfill script, local run) begins after human review and approval; commit/push follow the project’s explicit approval gates.

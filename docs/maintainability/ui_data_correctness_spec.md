# UI Data Correctness — Phase 1 Half-Sprint Spec

**Status:** RESOLVED — all four fixes shipped 2026-05-08; ship-logs in `docs/BACKLOG.md` (Lane C, Lane A, Lane B, Sponsor Phase 2B migration restore).
**Source of truth for:** the four homepage data-correctness fixes named in the *Ask Hava — Detailed Plan* (Phase 1, §2.1, "half-sprint UI-data-correctness pass").
**Audience:** any agent (Cowork / Claude Code / Cursor) executing one of the four fix slices.
**Companion docs:** `CRITIQUE_AND_REDESIGN.md` (failure-mode evidence), `HAVA_CONCIERGE_HANDOFF.md` (architecture), `docs/persona-brief.md` (voice).

**Lessons learned (parallel-agent coordination):** Three agents using `Write` (full-file overwrite) on the same file (`app/home/queries.py`) repeatedly truncated each other's work — at one point the integrated state was at 361 lines mid-statement when concurrent writes landed on top of each other. The same pattern broke `tests/test_home_queries.py` (truncated mid-test at `remainin`), `docs/BACKLOG.md` (mid-sentence), and `alembic/versions/2a3b4c5d6e7f_evolve_sponsors_*.py` (mid-string, stalled 2 hours). **Future parallel runs against shared files must use anchored `Edit` operations only — never `Write` — and reports must come back as text for the primary to integrate.** This is now the §6 Lane Map convention for any spec that fans out to multiple agents.

---

## 0. Why this spec exists

The homepage currently leaks three different kinds of unfinished plumbing into the surface:

1. *Tonight* row shows pre-dawn events because the query filters `Event.date == today` with no time-of-day cut.
2. Spotlight and "new on Hava" provider cards render `{{ biz.category }}` raw — a `CATEGORY_LABELS` map exists in `app/home/queries.py` but isn't applied to those cards.
3. Several spotlight phones are NANP-reserved `(928) 555-01XX` placeholders rendered as `tel:` links.
4. Some event cards still print URL-truncated, label-prefixed (`Date: …\nVenue: …`) blurbs because the sanitizer in `_card_blurb` doesn't strip those shapes.

None of these are catalog-density problems. All four ship independently of any inventory work. They remove the "this product isn't finished" tax that currently undercuts every other Phase 1 deliverable.

The four fixes are scoped to be **independently shippable** — each one is a separate PR, separate test, separate close criterion. They can run in parallel across multiple agents/sessions because they touch mostly disjoint code paths (see §6 Lane Map).

---

## 1. Fix #1 — `Tonight` query: time-of-day filter, label switch, venue diversity

### 1.1 Current behavior

`app/home/queries.py::tonight()` (lines ~156–189):

```python
rows = (
    db.query(Event)
    .filter(Event.date == today, Event.status == "live")
    .order_by(Event.featured.desc(), Event.start_time.asc())
    .limit(limit)
    .all()
)
```

Failure modes observed on production `/home` (per `CRITIQUE_AND_REDESIGN.md` §A2):

- 5 AM lap swim renders as the hero card under a "Tonight" label.
- Three rows of pool schedules at the same venue (Aquatic Center) dominate the row.
- Section header says *Tonight* even at 8 AM.

### 1.2 Target behavior

Three changes, applied in `tonight()`:

**(a) Time-of-day filter.** Add a lower-bound on the event's start time:

```
filter(
    Event.date == today,
    Event.status == "live",
    or_(
        Event.start_time.is_(None),                  # all-day events still surface
        Event.start_time >= effective_floor,         # see (b)
    ),
)
```

`effective_floor` is computed from the current local time (`now_lake_havasu()`) and the label regime in (b):

| Local time | Label | `effective_floor` |
|---|---|---|
| 00:00 – 11:00 | "Today" | `now.time()` (drops past events; keeps anything that hasn't started) |
| 11:00 – 16:00 | "Today" | `now.time()` |
| 16:00 – 23:59 | "Tonight" | `max(now.time(), 16:00)` |

Rationale: before 4 PM the row is forward-looking from now; after 4 PM the row is "evening starting at 4 PM, including events that started at 4:30 if it's now 4:45."

**(b) Label switch.** New helper:

```python
def tonight_or_today_label(now: datetime) -> str:
    """Return 'Tonight' after 4 PM local, else 'Today'."""
    return "Tonight" if now.hour >= 16 else "Today"
```

The builder returns `(rows, label)` where `label` is one of `"Tonight"` / `"Today"`; the home view (`app/home/views.py` or wherever `tonight()` is consumed) passes it to the template as `tonight_label`. The template renders `<h2>{{ tonight_label }}</h2>` instead of a literal `Tonight`.

**Backward compatibility note:** existing callers expect a list of dicts. Either (i) change `tonight()` to return `dict(rows=[...], label="...")` and update all callers, or (ii) keep the list shape and add a sibling `tonight_label(now)` function. Prefer (ii) — fewer caller edits.

**(c) Venue diversity.** Soft de-dup on `Event.location_name` so the row doesn't show three Aquatic Center entries when other venues exist. Algorithm:

```
1. Pull 3× the limit (i.e., `limit * 3`) candidate rows ordered by featured desc, start_time asc.
2. Walk in order, accept events one per location until limit reached.
3. If we don't reach `limit` (only one venue today), backfill from rejected rows in original order.
```

This preserves "if there genuinely are only Aquatic Center events today, we still fill the row" while preventing visual monotony when alternatives exist.

### 1.3 File-level changes

| File | Change |
|---|---|
| `app/home/queries.py` | Rewrite `tonight()` per §1.2. Add `tonight_or_today_label(now)` helper. |
| `app/home/views.py` (or the route handler that calls `tonight()`) | Pass `tonight_label = tonight_or_today_label(now_lake_havasu())` into the template context. |
| `app/templates/home.html` | Replace literal *Tonight* in the section heading with `{{ tonight_label }}`. |
| `tests/test_home_queries.py` (new or existing) | Cases per §1.4. |

### 1.4 Test plan

| Test | Setup | Expected |
|---|---|---|
| `test_tonight_drops_past_events` | now = 14:00; event.start_time = 05:00 today | event excluded |
| `test_tonight_keeps_future_events_today` | now = 14:00; event.start_time = 19:00 today | event included |
| `test_tonight_label_today_before_4pm` | now = 14:00 | label == "Today" |
| `test_tonight_label_tonight_after_4pm` | now = 17:00 | label == "Tonight" |
| `test_tonight_floor_applies_4pm_after_4pm` | now = 17:00; event.start_time = 12:00 today | event excluded |
| `test_tonight_includes_all_day_events` | event.start_time is None, event.date == today | event included |
| `test_tonight_venue_diversity` | 5 events, 3 at Aquatic Center, 2 at other venues | row has 1 Aquatic Center, 2 others (limit=3) |
| `test_tonight_diversity_backfill_when_single_venue` | 5 events all at Aquatic Center | row has 3 Aquatic Center (no alternatives) |

### 1.5 Close criteria

- All eight tests pass.
- Live `/home` at any hour of day shows zero events whose `start_time` is in the past for today.
- Manual smoke check at 5 AM, 12 PM, 5 PM Lake Havasu time confirms label switches correctly.

---

## 2. Fix #2 — Category labels: stop leaking raw enum slugs

### 2.1 Current behavior

`CATEGORY_LABELS` already exists at `app/home/queries.py:27-38` and is correctly applied inside `categories()` (line 425).

The leak is on **provider cards**, not category chips:

| Site | Code | Issue |
|---|---|---|
| `app/templates/home.html:165` | `{{ biz.category }}` | renders raw enum on Spotlight cards |
| `app/home/queries.py:325` | `"meta_text": prov.category or "Local pro"` | raw enum becomes the meta line on `new_on_hava` provider rows |
| `app/home/queries.py:384` | `"category": prov.category or "Local pro"` | raw enum on Spotlight cards |

### 2.2 Target behavior

**Single rule: the template never sees a raw category slug. Builders pre-resolve to display label.**

**(a) Add a helper.** In `app/home/queries.py`:

```python
def _category_label(category: str | None) -> str:
    """Return the human-readable label for a Provider.category enum.

    Falls back to a sentence-cased version of the slug if the category
    isn't in the canonical map. Empty/None returns the generic "Local pro"
    so cards never render a blank meta line.
    """
    if not category:
        return "Local pro"
    if category in CATEGORY_LABELS:
        return CATEGORY_LABELS[category]
    # Defensive fallback: replace underscores, sentence case
    return category.replace("_", " ").capitalize()
```

**(b) Apply it at every provider-card builder site.** Replace:

```python
"category": prov.category or "Local pro"
"meta_text": prov.category or "Local pro"
```

with:

```python
"category": _category_label(prov.category)
"meta_text": _category_label(prov.category)
```

**(c) Widen the canonical map.** Audit live values of `Provider.category` against the keys of `CATEGORY_LABELS`. Any value that appears in the DB but not in the map is a hole the fallback covers — but the fallback is a code smell, not a feature. Add explicit entries for every value present in production. Suggested additions to consider (verify against DB):

```python
"general_contractor":   "Contractors",
"real_estate":          "Real estate",
"insurance":            "Insurance",
"financial":            "Financial",
"legal":                "Legal",
"event_venue":          "Venues",
"lodging":              "Lodging",
"tourism":              "Tourism",
```

**(d) Don't render category on the template directly anywhere.** Grep for `{{ biz.category }}` and `{{ prov.category }}` and confirm zero hits remain after this fix. The contract: if a card needs a category line, it reads from a builder-provided field that already contains the human label.

### 2.3 File-level changes

| File | Change |
|---|---|
| `app/home/queries.py` | Add `_category_label()`. Replace three (or more) raw-category usages. Widen `CATEGORY_LABELS` to cover all live `Provider.category` values. |
| `app/templates/home.html` | No change strictly required after builder fix — but add a comment near `{{ biz.category }}` (which becomes the label by then) noting the contract. |
| `tests/test_home_queries.py` | Cases per §2.4. |

### 2.4 Test plan

| Test | Setup | Expected |
|---|---|---|
| `test_category_label_known_slug` | `_category_label("home_services")` | `"Home services"` |
| `test_category_label_unknown_slug` | `_category_label("frobnicator_fix")` | `"Frobnicator fix"` (fallback) |
| `test_category_label_empty` | `_category_label(None)` and `_category_label("")` | `"Local pro"` |
| `test_spotlights_uses_human_label` | Provider with `category="religion_community"` in spotlight | `card["category"] == "Community"` |
| `test_new_on_hava_uses_human_label` | Provider with `category="health_medical"` | `card["meta_text"] == "Health & medical"` |

### 2.5 Close criteria

- Five tests pass.
- `grep -nE '\\{\\{\\s*\\w+\\.category\\s*\\}\\}' app/templates/` returns zero matches in any rendering of provider/business cards.
- Live `/home` shows no underscore characters in the visible category text.

---

## 3. Fix #3 — Placeholder phones: NANP-reserved range guard + data cleanup

### 3.1 Current behavior

Per `CRITIQUE_AND_REDESIGN.md` §A1: all three Spotlight phone numbers are `(928) 555-01XX`, a NANP-reserved range. The numbers don't appear in the codebase as literals (verified by grep) — they're in the database, almost certainly from sample sponsor data loaded in development or staging.

The phones render as `<a class="phone" href="tel:{{ biz.phone_raw }}">{{ biz.phone }}</a>` (template line 171), so they're tappable on mobile, which makes the placeholder hostile rather than just embarrassing.

### 3.2 Target behavior

**Two layers of defense:**

**(a) Runtime guard in `_format_phone`.** Update `app/home/queries.py:78`:

```python
# NANP-reserved placeholder range: (NXX) 555-01XX where NXX is any area code.
# These numbers are guaranteed-non-routable per FCC, and any of them in
# production data is a placeholder slip from seed/sample loading.
_PLACEHOLDER_PHONE_RE = re.compile(r"^\d{3}55501\d{2}$")


def _format_phone(raw: str | None) -> tuple[str, str] | tuple[None, None]:
    """Return (display, raw_digits) or (None, None) when unusable.

    Returns (None, None) for NANP-reserved 555-01XX placeholder numbers
    so they never render as a tappable tel: link. The card's footer
    falls back to "Phone on profile" or hides the phone row entirely
    (template responsibility).
    """
    if not raw:
        return None, None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if _PLACEHOLDER_PHONE_RE.match(digits):
        return None, None
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}", digits
    return raw, digits or None
```

**(b) Template fallback.** Update `app/templates/home.html` lines around 171:

```jinja
{% if biz.phone %}
  <a class="phone" href="tel:{{ biz.phone_raw }}">{{ biz.phone }}</a>
{% else %}
  <span class="phone phone-missing">Phone on profile</span>
{% endif %}
```

The `.phone-missing` class is `--ink-3` colored, no underline, no tappable affordance — render-only meta.

**(c) Data cleanup.** New script `scripts/cleanup/null_placeholder_phones.py`:

```python
"""One-shot cleanup: null Provider.phone for any NANP-reserved 555-01XX value.

Idempotent — safe to re-run. Logs every change with provider id and old value
to a timestamped file in scripts/cleanup/logs/.

Usage:
    python -m scripts.cleanup.null_placeholder_phones --dry-run
    python -m scripts.cleanup.null_placeholder_phones --apply
"""
```

Log every match. Apply in production only after dry-run review.

**Note: not an Alembic migration.** This is data, not schema. Alembic for schema, ad-hoc cleanup script for data — same convention as `scripts/cleanup/` already established in the repo.

### 3.3 File-level changes

| File | Change |
|---|---|
| `app/home/queries.py` | Add `_PLACEHOLDER_PHONE_RE`; update `_format_phone` to return `(None, None)` for matches. |
| `app/templates/home.html` | Conditional render of `.phone` block; `.phone-missing` fallback. |
| `app/static/styles/home.css` | New `.phone-missing` style: `color: var(--ink-3); font-size: var(--t-meta);` no underline. |
| `scripts/cleanup/null_placeholder_phones.py` | New cleanup script. |
| `scripts/cleanup/logs/.gitkeep` | New (or just gitignored). |
| `tests/test_home_queries.py` | Cases per §3.4. |

### 3.4 Test plan

| Test | Setup | Expected |
|---|---|---|
| `test_format_phone_strips_placeholder_nanp` | `_format_phone("(928) 555-0100")` | `(None, None)` |
| `test_format_phone_strips_placeholder_other_areacode` | `_format_phone("(212) 555-0199")` | `(None, None)` |
| `test_format_phone_keeps_real_number` | `_format_phone("(928) 855-1234")` | `("(928) 855-1234", "9288551234")` |
| `test_format_phone_keeps_real_555_outside_01xx` | `_format_phone("(928) 555-1234")` | normal format (only 555-01XX is reserved) |
| `test_format_phone_handles_already_digits` | `_format_phone("9285550100")` | `(None, None)` |
| Cleanup script dry-run | DB seeded with 3 placeholder + 2 real | reports 3 matches; nullifies 0 |
| Cleanup script apply | same | nullifies 3; idempotent on re-run |

### 3.5 Close criteria

- All seven tests pass.
- Live `/home` Spotlight row shows zero `(NXX) 555-01XX` numbers.
- Cleanup script logged; production DB confirmed via spot query that no Provider phone matches the placeholder regex.

---

## 4. Fix #4 — Event blurb sanitizer hardening

### 4.1 Current behavior

`_card_blurb` at `app/home/queries.py:59` already strips URLs and collapses whitespace. The remaining failure modes (per `CRITIQUE_AND_REDESIGN.md` §A1):

- **Labelled-field dumps**: `"Date: May 09, 2026\nTime: 12:00 – 12:00\n\n\nVenue: 2144 McCulloch…\nOrganizer: Havasu Together\nCategories: Farmer's Market"` — none of these labels get stripped; the card shows the labels themselves as if they were body copy.
- **Truncated-mid-character**: when a description ends mid-URL ("…schedule.com/op…"), the URL strip leaves a dangling fragment.
- **Repeated boilerplate**: six cards on the page contain the identical templated string about lap swim at the Aquatic Center because that's literally what the source description is. The sanitizer doesn't dedupe boilerplate but it should at least flag when an event's blurb is identical to another event in the same render.

### 4.2 Target behavior

**Tighten the sanitizer to recognize and strip three additional shapes:**

**(a) Labelled-field lines.** Add a regex pass that drops lines matching `^\s*(Date|Time|Venue|Address|Organizer|Categories|Tags|Cost|Price|Phone|Website|URL|Link)\s*:\s*` (case-insensitive) before the URL strip. Drop the entire matched line, not just the label.

**(b) Trailing fragment after URL strip.** After stripping URLs, if the remaining text ends with an alphanumeric-only token of < 6 chars (i.e., a fragment of a URL the regex left behind), trim it. Conservative: only trim if preceded by whitespace and the fragment doesn't start a new sentence (no leading capital after a period).

**(c) Empty-after-sanitize fallback.** If sanitization produces an empty string, return a one-line venue+time fallback: `"At {location_name} on {date}"` rather than empty. The card has a place to render it; an empty blurb just leaves a hole.

```python
_LABEL_LINE_RE = re.compile(
    r"^\s*(Date|Time|Venue|Address|Organizer|Categories?|Tags?|Cost|Price|Phone|Website|URL|Link)\s*:\s*.*$",
    re.IGNORECASE | re.MULTILINE,
)


def _card_blurb(event_or_provider) -> str:
    """Extract a clean one-line blurb. Strips URLs, labelled fields, ISO dates,
    multiple newlines. Takes the first sentence, truncates at 140 chars at word
    boundary. Falls back to venue+date sentence if nothing usable remains.
    """
    if getattr(event_or_provider, "summary", None):
        return event_or_provider.summary
    raw = (event_or_provider.description or "").strip()
    raw = _LABEL_LINE_RE.sub("", raw)             # NEW: drop labelled rows
    raw = _URL_RE.sub("", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.sub(r"\b\w{1,5}$", "", raw).strip()  # NEW: trim trailing fragments
    if not raw:
        # NEW: fallback for Events with location_name + date
        if hasattr(event_or_provider, "location_name") and getattr(event_or_provider, "date", None):
            loc = event_or_provider.location_name or "a Havasu venue"
            return f"At {loc} on {event_or_provider.date.strftime('%b %-d')}"
        return ""
    first = raw.split(". ")[0].strip().rstrip(".")
    if len(first) > 140:
        first = first[:137].rsplit(" ", 1)[0] + "…"
    return first
```

**(d) Confirm all event-card render paths flow through `_card_blurb`.** Verify in `tonight()`, `this_week()`, `new_on_hava()` — all already call `_card_blurb(ev)`. No other code path should bypass it. Grep for `event.description` and `ev.description` direct usages in views/templates and remove any.

### 4.3 File-level changes

| File | Change |
|---|---|
| `app/home/queries.py` | Add `_LABEL_LINE_RE`. Update `_card_blurb` per §4.2. |
| `tests/test_home_queries.py` | Cases per §4.4. |

### 4.4 Test plan

| Test | Input | Expected |
|---|---|---|
| `test_card_blurb_strips_labelled_fields` | `"Date: May 9, 2026\nVenue: foo\nA real sentence."` | `"A real sentence"` |
| `test_card_blurb_handles_csv_dump` | `"Date: …\nTime: …\nVenue: …\nOrganizer: …\nCategories: …"` | venue+date fallback |
| `test_card_blurb_strips_trailing_url_fragment` | `"Schedule at https://example.com/op"` after URL strip leaves `"Schedule at op"` | `"Schedule at"` |
| `test_card_blurb_empty_falls_back_to_venue_date` | description="", location_name="Aquatic Center", date=2026-05-09 | `"At Aquatic Center on May 9"` |
| `test_card_blurb_real_description_passes_through` | normal sentence | unchanged (existing case) |

### 4.5 Close criteria

- Five tests pass (plus existing `_card_blurb` tests if any).
- Live `/home` shows zero cards containing `Date:`, `Time:`, `Venue:`, `Organizer:`, or `Categories:` labels in body text.
- Spot check on the Farmers Market card specifically.

---

## 5. Cross-cutting acceptance

A single-batch `pytest -q` after all four fixes ship green. No regression on existing tests. Manual `/home` smoke check confirms:

- *Today* / *Tonight* label correct for current local time.
- Zero pre-dawn events under either label.
- Zero raw enum slugs in body text.
- Zero `(NXX) 555-01XX` phones in tappable links.
- Zero labelled-field dumps in event blurbs.

Update `docs/STATE.md` close-out narrative when all four ship. Update `docs/BACKLOG.md` with the four ship-log entries.

---

## 6. Lane Map (parallelism guide)

The four fixes touch mostly disjoint surfaces. Recommended split for parallel agents:

| Lane | Fixes | Primary files | Owner |
|---|---|---|---|
| A | #2 (category labels) + #4 (blurb sanitizer) | `app/home/queries.py` (helpers + builders) | — |
| B | #1 (Tonight query) | `app/home/queries.py::tonight()`, view, `home.html` heading | — |
| C | #3 (placeholder phones) | `app/home/queries.py::_format_phone`, `home.html` phone block, `home.css`, `scripts/cleanup/` | — |

**Conflict surface:** all three lanes touch `app/home/queries.py` and (B + C) touch `app/templates/home.html`. Mitigations:

- Each lane confines its `queries.py` changes to clearly bounded sections (different functions for B and C; helper additions for A). Final merge conflict, if any, is mechanical.
- Each lane writes its tests in a clearly named block within `tests/test_home_queries.py` (suggested headings: `# --- Fix 1 (tonight) ---`, etc.).
- Land lanes serially in this order if conflicts emerge: A → C → B (smallest helper-add → template-touch → biggest function rewrite).

---

## 7. Out of scope (do not expand)

- Hours parsing — `_hours_status` placeholder behavior is already TODO'd at `queries.py:148` for a separate ship. Do not pull it in here.
- Photo sourcing — `_provider_image_url` returning `None` is intentional per BUILD.md "Photography sourcing." Out of scope.
- Redesign palette / layout — `CRITIQUE_AND_REDESIGN.md` Part B is a separate ship. This spec is content-correctness only.
- Visitor-mode UI — Phase 2 deliverable.
- Disclosure renderer — Phase 1 keystone, separate spec.

---

## 8. Doc/PR hygiene checklist (per WORKING_AGREEMENT)

For each lane's PR:

- Commit message references the fix number (e.g., `ui-data-correctness #1: Tonight query time-of-day filter`).
- `docs/BACKLOG.md` ship-log entry appended.
- `docs/STATE.md` close-out narrative updated when all four land.
- This spec marked `RESOLVED` at the top once Fix #4 ships green.

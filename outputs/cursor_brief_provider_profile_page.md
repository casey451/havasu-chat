# Cursor Brief — Provider Profile Page (`/provider/<slug>`)

> **Operator note:** paste to a fresh Cursor chat AFTER the `Provider.slug` Cursor lane has shipped and been committed. This brief's §0 hard-halts if `Provider.slug` doesn't exist. Authored 2026-05-13 by Cowork primary. Source of truth for copy + layout: `outputs/chatgpt_response_provider_profile_ux_spec.md` (saved this session) — read it through once before starting; this brief specifies implementation choices only and assumes you have that spec next to you.

---

## §0 Baseline confirmation + prerequisite check (do this FIRST and report before touching code)

1. `git log --oneline -5` — report the top 5 SHAs. The most recent commit should be the slug-lane commit (`Provider.slug field + backfill migration`). If you see only `11b248f` (cold-pitch) at top, the slug lane has not shipped yet — **HALT** and report.
2. `git status` — should be clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — record the count. Should be ≥1429 + however many tests the slug lane added.
4. `python -m alembic heads` — should be a single head, the slug-lane revision (chained off `e7f8a9b0c1d2`). Report the revision id.
5. **Prerequisite verification:** open `app/db/models.py` and confirm the Provider class has a `slug` column (type `String(120)`, with a unique index, nullable in the model annotation, NOT NULL at the DB layer post-migration). If absent, **HALT** and report.
6. **Prerequisite verification 2:** confirm `app/utils/slug.py` exists and exports `slugify` + `make_unique_slug`. If absent, **HALT**.

Report all values back before proceeding. Do not start §1 until baseline is confirmed.

---

## §1 Why this lane exists

The Provider profile page (`/provider/<slug>`) is the gating piece for the Verified Presence ($79/mo) sponsor package. It renders the structured profile for a single provider with verification stamps, action buttons, photos, hours, service details, and contextual claim/upgrade CTAs. End-users see a clean directory listing with working actions; merchants see a visible demonstration of what their $79/mo unlocks.

This brief covers the **public-facing render**. Out of scope: account-lite auth, the claim flow itself, the upgrade payment flow, owner-edit affordances (route exists, but the page only conditionally renders the affordances when a `viewer_is_owner` flag is true — wiring the flag to a real auth session is downstream work). Map embed is a placeholder for V1; Leaflet+OSM integration is a follow-up.

---

## §2 Locked design decisions (don't relitigate)

The UX spec at `outputs/chatgpt_response_provider_profile_ux_spec.md` has 8 open questions in §11. The following decisions are locked by the operator on 2026-05-13:

| # | Question | Decision |
|---|---|---|
| 1 | Free-tier Google snippets | **Visible across all tiers** (matches the §2 tier-delta table in the spec; the §11 question is a contradiction that resolves to the table). |
| 2 | Ask Hava UX | **Navigate to `/chat` with prefilled query.** Not a modal/sheet. |
| 3 | Logos as separate type | **Defer to Phase 2.** Hero-selection priority (§7 of spec) handles it implicitly. |
| 4 | Address visibility | **Owner-toggle for service-area-only.** New `attributes` key: `service_area_only: bool` (default: false if `google_place_id` is present, true otherwise). When true, hide street address and render the `service_area` list instead (also from `attributes`, list of strings). |
| 5 | Sponsor hero pin | **Sponsor can pin via `attributes.hero_pin_photo_url: str` (V1 lives in `attributes` JSON, promoted to a column if it becomes load-bearing).** Hero-selection priority becomes: `attributes.hero_pin_photo_url` → owner-uploaded (not yet wired; treat as absent for V1) → first `google_photo_refs` → placeholder. |
| 6 | Holiday hours toggle | **Defer to Phase 2.** Owner edits `hours_structured` directly when wired. |
| 7 | "Hava's pick" badge | **Render a subtle editorial badge when `Provider.featured=True`**, visually distinct from sponsor disclosure. Plain text label `Hava's pick`; place near the verification cluster (not in the actions row). Different color/iconography from sponsor labels (the brief leaves the specific visual to your judgment — just keep it operationally honest, not loud). |
| 8 | `years_in_business` as column | **Defer.** Stays in `attributes` JSON for V1. |

**Three more implementation-side adjustments** I noticed in spec review that override the spec text:

- **Hours rendering must be timezone-aware** (`America/Phoenix`, no DST). Use `app/core/timezone.py::now_lake_havasu()` for "is this business open right now" determinations. Do not use `datetime.now()` without a tz.
- **Call button: hybrid behavior.** On both mobile AND desktop, render the button as a `<a href="tel:...">` element (works on desktop too — opens FaceTime / Skype / default tel: handler). ADDITIONALLY include a small "copy number" affordance next to the button (small icon + click-to-copy). Don't ship desktop-as-clipboard-only; that loses the tel: shortcut for desktop users who do have a handler.
- **The spec's §5 example "Verified Presence subscriber" copy is a sample**, not a literal string. The actual sponsor disclosure label comes from `app/chat/disclosure_render.py::DISCLOSURE_WORD` rendered via the existing disclosure_renderer pipeline. Do not hardcode "Verified Presence subscriber" anywhere — render via the existing API.

---

## §3 Module structure

Create a new module at `app/providers/` (sibling to `app/home/`). Files to create:

```
app/providers/
├── __init__.py             # empty
├── router.py               # FastAPI router with @router.get("/provider/{slug}")
├── queries.py              # DB queries for the profile
└── view_models.py          # Pydantic dataclasses for template context
```

New template:

```
app/templates/provider_profile.html
```

Wire the router in `app/main.py`. Search for an existing `include_router` call for `app.home.router` and add an analogous `include_router(app.providers.router.router)` line immediately after it. Anchored Edit only.

Why a separate module instead of folding into `app/home/`: the `home/` module is the homepage surface; the `providers/` module is the directory front door's per-record view. Keeping them separate matches the post-pivot "three front doors" framing (homepage, directory profile, chat) and gives the category-page lane a clear sibling to land in (`app/categories/` when that ships).

---

## §4 Route + view-model

### `app/providers/router.py`

```python
"""Provider profile page route (POST-PIVOT directory V1).

Renders /provider/{slug} via Jinja. Source of truth for copy/layout is
outputs/chatgpt_response_provider_profile_ux_spec.md (Cowork-primary-
polished). All sponsor labeling routes through app.chat.disclosure_render.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.chat.disclosure_render import DISCLOSURE_WORD
from app.db.database import get_db
from app.providers import queries, view_models

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["providers"])


@router.get("/provider/{slug}", response_class=HTMLResponse)
def serve_provider_profile(
    slug: str, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    provider = queries.get_provider_by_slug(db, slug)
    if provider is None or not provider.is_active:
        raise HTTPException(status_code=404, detail="Provider not found")

    vm = view_models.build(provider, db=db, viewer_is_owner=False)
    return templates.TemplateResponse(
        request=request,
        name="provider_profile.html",
        context={"vm": vm, "disclosure_word": DISCLOSURE_WORD},
    )
```

Notes:
- `viewer_is_owner=False` is hardcoded for V1. When account-lite ships, replace with a session-derived check. Leave the parameter in `view_models.build()` so the template can branch on it now.
- Return 404 for missing or inactive providers (no soft-message page). End-users get the standard 404 surface; merchant onboarding is a separate flow.

### `app/providers/view_models.py`

A `ProviderProfileVM` dataclass (Pydantic v2 model or `@dataclass` — match whatever the rest of `app/` uses; check `app/home/` for the project's preferred pattern). Fields:

```
ProviderProfileVM:
  provider_name: str
  category_label: str            # mapped via queries.category_label_for(provider)
  district: str | None
  verified: bool
  last_verified_at: datetime | None
  verification_method_copy: str  # mapped per UX spec §5 method-to-copy table
  freshness_band: str            # "fresh" / "acceptable" / "aging" / "stale" / "none"
  freshness_copy: str            # per UX spec §5 freshness-band table
  is_sponsored: bool             # tier == "sponsored" AND sponsored_until > now
  is_featured: bool              # Provider.featured (Hava's pick badge)
  sponsor_disclosure_label: str | None  # rendered via disclosure_render (None if not sponsored)
  google_rating: float | None
  google_review_count: int | None
  call_phone: str | None         # display + tel: link source
  directions_url: str | None     # google maps url; None if no address and no lat/lng
  website_url: str | None
  ask_hava_url: str              # /chat?q=<prefilled> (always present)
  hero_photo_url: str | None     # resolved via §2 hero-selection priority
  gallery_photo_urls: list[str]  # additional photos beyond hero
  description: str | None        # featured_description if present, else description
  service_chips: list[str]       # built from attributes per UX spec §6
  service_area: list[str]        # from attributes.service_area when service_area_only=True
  service_area_only: bool        # from attributes.service_area_only
  address: str | None            # None when service_area_only=True
  hours_structured: dict | None
  hours_freetext: str | None
  is_open_now: bool | None       # computed via now_lake_havasu()
  open_status_copy: str | None   # "Open now / Closes at 5 PM" etc.
  google_review_snippets: list[dict]
  show_claim_cta: bool           # tier == "free" AND verified == False
  show_upgrade_cta: bool         # claimed but not sponsored
  viewer_is_owner: bool          # owner-edit affordances flag
  data_inconsistency_flag: bool  # tier=="sponsored" but verified==False (UX spec §9)
```

`view_models.build(provider, db, viewer_is_owner)` is a pure function (apart from the `db` arg used for sponsor lookup). It centralizes ALL the conditional logic so the template stays dumb. The template should have zero `if`-on-business-logic — only `if vm.show_claim_cta` style flag checks.

### `app/providers/queries.py`

```
def get_provider_by_slug(db: Session, slug: str) -> Provider | None
def category_label_for(provider: Provider) -> str  # use existing CATEGORY_LABELS or category_ref.name
def is_open_now(provider: Provider, *, now: datetime | None = None) -> tuple[bool, str | None]
def derive_directions_url(provider: Provider) -> str | None
def derive_hero_photo(provider: Provider) -> str | None
def derive_gallery(provider: Provider, exclude_hero: bool = True) -> list[str]
def derive_freshness(provider: Provider, *, now: datetime | None = None) -> tuple[str, str]
def derive_service_chips(provider: Provider) -> list[str]
def derive_ask_hava_url(provider: Provider) -> str  # /chat?q=Tell+me+about+...
```

The `is_open_now`, `derive_freshness`, and any other time-dependent functions accept an optional injected `now` parameter for testability (matches the project's pattern; see `now_lake_havasu()` callers).

Mirror the pattern in `app/home/queries.py` — simple ORM SELECTs, helper functions return primitives, no caching for V1.

---

## §5 Template (`app/templates/provider_profile.html`)

Implementation guidance, not full HTML. Use whatever the project's existing Jinja conventions are (check `app/templates/home.html` for tone). The template should:

1. Extend the project base template if one exists; otherwise create a self-contained page that mirrors `home.html`'s `<head>` structure.
2. Render top-to-bottom per UX spec §2 (regions 1–11). Each region is its own `<section>` with a clear `data-region="..."` attribute for test/debug visibility.
3. Use only `vm.*` and `disclosure_word` from context — no business logic in the template.
4. **Sponsor disclosure rendering:** if `vm.is_sponsored`, render `{{ disclosure_word }}` (which comes from `DISCLOSURE_WORD`) in a small label near the verification cluster. Follow the existing pattern in `app/templates/home.html` where the sponsor card uses the disclosure word — match the visual treatment.
5. **Hava's pick badge:** if `vm.is_featured`, render a small badge with the text "Hava's pick" near the verification cluster. Visually distinct from the sponsor disclosure (different color, no "Sponsored" word). Keep it understated.
6. **Action buttons:** render exactly the buttons whose source data is non-None (Call, Directions, Website, Ask Hava). Ask Hava always renders. See §6 below for the hybrid call button.
7. **Trust strip:** render per UX spec §5 with the freshness-band copy from `vm.freshness_copy`. If sponsored AND stale, render BOTH the sponsor disclosure AND the stale freshness copy (UX spec §5 "sponsored + stale handling").
8. **Photos:** if `vm.hero_photo_url` is None, render the "No business photos available yet" placeholder. Otherwise hero + optional gallery below.
9. **Service chips:** loop `vm.service_chips`; hide the row entirely if empty.
10. **Hours:** prefer `vm.hours_structured`; fallback to `vm.hours_freetext`; hide section if both None. The "Open now / Closes at 5 PM" line uses `vm.open_status_copy` (computed in queries with timezone awareness).
11. **Address / service area:** if `vm.service_area_only`, render `Serves: ` followed by the comma-separated `vm.service_area` list. Otherwise render `vm.address`. Map embed is a placeholder `<div>` for V1 (no Leaflet integration in this lane).
12. **CTAs:** `{% if vm.show_claim_cta %}...{% elif vm.show_upgrade_cta %}...{% endif %}` near the bottom. Use the exact copy from UX spec §10.
13. **Edge-case flag:** if `vm.data_inconsistency_flag`, render "Sponsored listing" instead of the verified badge (UX spec §9 "verified=False but tier=sponsored" — no green check, just sponsor disclosure).

### Copy bank (lift directly from UX spec §10)

Implement every entry from the spec's §10 table. Do not paraphrase or improvise — operators care about consistency.

---

## §6 Implementation-specific details (the bits the UX spec doesn't fully resolve)

### §6.1 Hybrid Call button

```html
<a class="profile-action profile-action-call" href="tel:{{ vm.call_phone }}">
  <span>Call</span>
  <span class="profile-action-number">{{ vm.call_phone_display }}</span>
</a>
<button class="profile-action-copy" data-clipboard="{{ vm.call_phone }}"
        aria-label="Copy phone number">
  <!-- small icon -->
</button>
```

Display format: format the phone number for human reading (e.g. `(928) 555-1212`); the `href="tel:..."` URI uses the digits-only form. Add a small inline JS handler for the copy button that writes to clipboard and surfaces "Phone number copied" for 2 seconds. Keep the JS tiny and inline — no new bundler dependencies.

### §6.2 Ask Hava URL construction

`vm.ask_hava_url` is `/chat?q=<urlencoded("Tell me about {provider_name} in Lake Havasu City")>`. Use Python's `urllib.parse.quote` at view-model build time, not in the template. Validate that the existing `/chat` route accepts a `q` query param for prefill — if it doesn't, file a follow-up note in the final report (don't try to add prefill support here).

### §6.3 Hava's pick badge

When `Provider.featured=True`, render a small badge near the verification cluster:

```html
<span class="profile-badge profile-badge-featured" title="Editorially recommended by Hava">
  <!-- subtle icon -->
  Hava's pick
</span>
```

Visual treatment: should NOT use the same color as the sponsor disclosure. The sponsor disclosure already exists in the project's CSS (see `home.html`); pick a different accent color (project owner can refine later). Don't ship it as red/yellow/orange — those read as warning. Plain dark accent is fine.

### §6.4 Service-area-only mode

In `queries.derive_service_chips` or similar:

```python
attrs = provider.attributes or {}
service_area_only = bool(attrs.get("service_area_only", False))
# Default: True when google_place_id is null (no commercial premise),
# False when google_place_id is set (commercial premise).
if "service_area_only" not in attrs:
    service_area_only = provider.google_place_id is None
```

The `service_area` list comes from `attrs.get("service_area", [])`. If `service_area_only=True` but the list is empty, render an empty-state line: `Service area not specified` (add to copy bank).

### §6.5 Hero photo selection

```python
def derive_hero_photo(provider: Provider) -> str | None:
    attrs = provider.attributes or {}
    pinned = attrs.get("hero_pin_photo_url")
    if pinned:
        return pinned
    # owner-uploaded photos: V1 not wired; placeholder for Phase 2
    google_photos = provider.google_photo_refs or []
    if google_photos:
        return google_photos[0]
    return None
```

### §6.6 Freshness bands

```python
def derive_freshness(provider, *, now=None):
    if provider.last_verified_at is None:
        return ("none", "")  # template hides the trust-strip line in this case
    now = now or now_lake_havasu()
    age_days = (now - provider.last_verified_at).days
    if age_days <= 30:
        return ("fresh", f"Last verified {provider.last_verified_at.strftime('%B %-d, %Y')}")
    if age_days <= 90:
        months = max(1, age_days // 30)
        return ("acceptable", f"Verified {months} month{'s' if months != 1 else ''} ago")
    if age_days <= 180:
        return ("aging", "Verification may be outdated")
    return ("stale", "Business information may have changed")
```

Note: `%-d` is Linux/Mac only; use `%d` and strip leading zero manually or use `f"{dt.month}/{dt.day}/{dt.year}"`-style formatting if cross-platform matters here.

### §6.7 Data inconsistency edge case

```python
data_inconsistency_flag = (
    provider.tier == "sponsored"
    and provider.sponsored_until is not None
    and provider.sponsored_until > now_lake_havasu()
    and not provider.verified
)
```

When True, the template renders "Sponsored listing" (copy bank addition) instead of a verified badge. Log this server-side as a warning so operators can correct the row (use whatever logger pattern `app/` already uses; no new logging infrastructure).

---

## §7 Tests

New tests under `tests/test_provider_profile.py`:

1. `test_route_returns_200_for_valid_slug` — seed a Provider, GET `/provider/<slug>`, assert 200.
2. `test_route_returns_404_for_unknown_slug` — GET `/provider/no-such-slug`, assert 404.
3. `test_route_returns_404_for_inactive_provider` — seed with `is_active=False`, assert 404.
4. `test_view_model_freshness_fresh_band` — Provider verified yesterday → `freshness_band == "fresh"`.
5. `test_view_model_freshness_aging_band` — Provider verified 120 days ago → `freshness_band == "aging"`, copy matches.
6. `test_view_model_freshness_stale_band` — Provider verified 200 days ago → `freshness_band == "stale"`.
7. `test_view_model_freshness_none_band` — `last_verified_at=None` → `freshness_band == "none"`.
8. `test_view_model_data_inconsistency_flag` — `tier="sponsored"`, `sponsored_until` in future, `verified=False` → `data_inconsistency_flag=True`.
9. `test_view_model_ask_hava_url_prefilled` — assert URL contains `q=Tell%20me%20about%20Acme...` (urlencoded).
10. `test_view_model_hero_pin_wins_over_google_photo` — `attributes.hero_pin_photo_url` set + `google_photo_refs` non-empty → hero is the pin.
11. `test_view_model_service_area_only_default_for_no_google_place_id` — Provider with no `google_place_id` and no explicit `service_area_only` attr → `service_area_only=True`.
12. `test_view_model_service_area_only_override` — Provider with `google_place_id` set + `attributes.service_area_only=True` → `service_area_only=True` (explicit override beats default).
13. `test_template_renders_hava_pick_badge_when_featured` — render template with `vm.is_featured=True`, assert "Hava's pick" string in output.
14. `test_template_omits_hava_pick_badge_when_not_featured` — opposite.
15. `test_template_renders_sponsor_disclosure_when_sponsored` — `vm.is_sponsored=True`, assert `DISCLOSURE_WORD` appears.
16. `test_template_renders_claim_cta_for_free_unclaimed` — assert claim CTA copy present.
17. `test_template_renders_upgrade_cta_for_claimed_not_sponsored` — assert upgrade CTA copy present.
18. `test_open_status_respects_lake_havasu_timezone` — pin `is_open_now` against a known `hours_structured` + injected `now` in America/Phoenix.

Pattern-match `tests/test_directory_schema.py` for fixture style (the schema lane that shipped clean is the right reference).

Run the full test suite at the end. Expected: prior count + 18 new tests.

---

## §8 Phased commit boundaries (recommended)

This lane is large enough that two commits are sane (operator's call — you can also ship as one if you want):

**Phase A — data layer + route + view model.** Files: `app/providers/__init__.py`, `app/providers/router.py`, `app/providers/queries.py`, `app/providers/view_models.py`, wire-up in `app/main.py`, tests #1–12 from §7. Commit message subject: `feat(providers): /provider/<slug> route + view model + queries (no template yet)`. Acceptance: route returns 200 with a minimal JSON-shaped response or stub template, all 12 tests pass.

**Phase B — template + visual rendering + remaining tests.** Files: `app/templates/provider_profile.html`, tests #13–18. Commit message: `feat(providers): provider_profile.html template + region rendering`. Acceptance: template renders end-to-end for a seeded provider in each of {free, verified, sponsored, sponsored+stale, featured} cases.

If you ship as a single commit, that's also fine — just message-subject it `feat(providers): /provider/<slug> page (route + template + tests)`.

---

## §9 What NOT to do

- **No `git add` / `git commit` / `git push`.** Report when done; operator commits.
- **Don't `git commit --amend`** (Rule 12).
- **Don't add Leaflet/Mapbox JS in this lane.** Map embed is a placeholder `<div>` only.
- **Don't wire account-lite auth or owner-edit affordances.** `viewer_is_owner=False` hardcoded; the parameter exists so the template can branch later.
- **Don't add a route for the claim flow or the upgrade flow.** Those CTAs link to placeholder URLs (`/claim/<slug>`, `/upgrade/<slug>`) that don't need to exist yet — 404 is acceptable for V1 of this lane.
- **Don't add new CSS frameworks.** Use whatever the project already uses (check `home.html` for the pattern). Hand-roll a small amount of CSS if needed; keep it scoped to `provider_profile.html`.
- **Don't paraphrase the copy bank.** Lift §10 of `outputs/chatgpt_response_provider_profile_ux_spec.md` verbatim.
- **Don't try to backfill `Provider.featured` or set `tier="sponsored"` for test fixtures via the sponsor_store API.** Just set the columns directly on the Provider model in tests.
- **Don't touch the chat-route runtime** (`app/chat/`). The Ask Hava button links to `/chat?q=...`; if the route doesn't already accept `q=`, flag it as a follow-up, don't add it here.
- **Don't run any computer-use or browser-automation tools.** Pure code lane.

---

## §10 Final report format

When done, paste back a single message with:

1. **§0 baseline values** (HEAD, pytest count, alembic head, prerequisite checks).
2. **Files created** (paths + line counts).
3. **Files modified** (paths + net line counts; should be limited to `app/main.py`).
4. **Phase A commit-ready / Phase B commit-ready** status, and final test counts after each phase.
5. **Pragmatic deviations** — anything you adapted from this brief with rationale. Schema-lane Cursor flagged three pragmatic deviations and they were all fine; transparent reporting is the norm.
6. **Anything you noticed that the operator should know** before they commit (e.g. "the `/chat` route does not yet accept `q=` for prefill; file a ticket").
7. **Confirmation that you did NOT run `git add`/`commit`/`push` or `--amend`.**

Ready. Start at §0.

# Cursor Brief — Phase 2B: Image storage (R2 + Pillow) + Postgres FTS search + search bar UI

> **Operator note:** paste this brief to a fresh Cursor chat. **This is Lane 2B of Phase 2 of the master build plan** (`docs/maintainability/master_build_plan.md` §4 Phase 2). Lane 2A (account-lite) is in flight — Phase 2A.1 shipped at commit `6000138` (2026-05-11); 2A.2 + 2A.3 dispatch on top. Lane 2B is file-disjoint from 2A.1/2A.2 per dispatch_protocol Rule 3 (this brief touches `app/photos/`, `app/search/`, `app/chat/tier2_db_query.py`, `app/templates/`, `alembic/versions/`, `app/db/models.py` tail-append; Lane 2A touches `app/auth/`, `app/admin/router.py::_guard`, `app/providers/router.py` viewer_is_owner plumbing). **However, Phase 2B.1 depends on Phase 2A.3** for the `verified` Claim plumbing that the upload route's auth check uses — see §3 sub-phase dependency note.
>
> The brief is structured around **three explicit sub-phase boundaries (Phase 2B.1 photos schema + R2 + Pillow upload pipeline; 2B.2 Postgres FTS + chat tier 2 LIKE→FTS swap; 2B.3 search bar UI + endpoint + close-out)**, each independently committable + pytest-green. **You are expected to HALT and report after each sub-phase so the operator can commit before you proceed.** Each sub-phase is sized to one Cursor session. Authored by Cowork primary at session-17 mid-flight from `docs/maintainability/image_storage_design.md`, `docs/maintainability/search_index_decision.md`, `docs/maintainability/master_build_plan.md` §4 Phase 2 Lane 2B, and the Phase 2A brief shape (`outputs/cursor_brief_phase_2a_account_lite.md`).
>
> **Operator prereq:** Cloudflare R2 bucket + access keys + public-URL strategy locked, and env vars dropped into Railway (see `outputs/operator_prereqs_phase_2.md` §2). The canonical env var names are `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL_BASE`. **As of this brief's authoring (session-17 mid-flight), the R2 setup has NOT yet been completed by the operator** — the brief is authored cold (mirroring 2A's authoring pattern before Resend was locked). If the operator hasn't done R2 setup by the time you read §0, halt and report at step 8.

---

## §0 Baseline confirmation (do this FIRST and report before touching code)

Before any edits, confirm and report:

1. `git log --oneline -5` — top of `main` should top at **`2423d4f`** ("Phase 2A.2 dispatch prompt artifact") OR a newer commit if Phase 2A.2 / 2A.3 has landed before this lane dispatches. Floor SHA chain at authoring: `2423d4f` → `9150be5` (docs ship-line) → `5bf4c14` (dispatch artifacts) → `6000138` (Phase 2A.1 code) → `4a5ee24` (boot prompt SHA patch). Treat the floor as a soft floor — material divergence (e.g., top SHA not derivable from this chain, or Lane 2A has landed something other than 2A.2/2A.3) is the halt trigger. **Report actual top-5 SHAs.**
2. `git status` — should be clean.
3. `python -m pytest -q --collect-only 2>&1 | tail -3` — collected count should be **≥1543** tests (Phase 2A.1 close-out baseline). If 2A.2 / 2A.3 has landed, count will be higher (~1570-1600+). Treat 1543 as floor, not exact.
4. `python -m alembic heads` — single head **`92ce4899dc08`** (Phase 2A.1 account-lite v0.1) OR a newer head if 2A.2/2A.3 added migrations. The Lane 2B.1 migration chains off whatever head you find.
5. `python -m alembic current` — should match head when local SQLite is clean. SQLite drift gotchas per dispatch_channels gotcha #10 — chain-walk down_revision before alarming.
6. **Read these six docs end-to-end before writing any code:**
   - `docs/maintainability/image_storage_design.md` (the design memo Lane 2B.1 implements — Photo schema in §5, upload flow in §4, Pillow pipeline in §6, security model in §7, CDN strategy in §8 are the locked specs; every recommendation has a corresponding "what NOT to do" in §13)
   - `docs/maintainability/search_index_decision.md` (the decision memo Lane 2B.2 implements — Option A (Postgres FTS + pg_trgm) locked in §3; index design in §4; chat tier 2 integration in §6; ranking heuristic in §4.4)
   - `docs/maintainability/master_build_plan.md` §4 Phase 2 Lane 2B (the deliverables checklist at line ~129-140; explicit "now points to entities.id" amendment carries forward — Photo.entity_id FKs entities.id NOT providers.id or places.id, mirroring Lane 2A's user_favorites/claims amendment)
   - `outputs/cursor_brief_phase_2a_account_lite.md` §0 + §2 + §3 + §10 + §11 + §12 (the brief-shape precedent and Postgres portability checklist absorbed into §9 below; deviation guardrails in §10; risk register in §11; final report format in §12 — mirror that voice + density)
   - `docs/maintainability/dispatch_protocol.md` (12 working-agreement rules — anchored Edit on shared files; no `git add` until explicit report; sequential lanes when files overlap)
   - `outputs/operator_prereqs_phase_2.md` §2 (R2 env vars + bucket setup + public-URL strategy Path A vs Path B)
7. **Read these source files** so you have current line offsets for the anchored edits in §5–§7:
   - `app/db/models.py` end-to-end (~970+ lines after Phase 2A.1; you'll append one new model class — `Photo` — at the bottom alongside the Phase 2A.1 User/MagicLinkToken/AuthSession/UserFavorite/Claim classes; `Entity` is at line ~625, extensions follow; the FK target `entities.id` is at :639)
   - `app/chat/tier2_db_query.py` end-to-end (~1000 lines; you'll migrate the LIKE chains around `:33+` to FTS. The synonym-expansion helper at `_category_needle_set` (`:548`) and its call sites (`:401`, `:450`, `:574`, `:968`) MUST BE PRESERVED — feed synonyms into `tsquery` OR clauses instead of `ilike` OR conditions. The `_query_providers_orm` shape (~:811-892), `_query_events` (~:683), `_query_programs` (~:866) are the migration targets. The Python-side `open_now` filter (~:946-954) stays as-is — FTS doesn't change that path.)
   - `app/main.py` end-to-end (~416+ lines; you'll add the photo upload router include + the search router include + extend `_hourly_cleanup_loop` at `:246` to sweep stuck-uploading Photo rows per design memo §4 step 9 failure handling)
   - `app/templates/home.html` + `app/templates/provider_profile.html` (existing visual treatment; search bar UI in 2B.3 lands here)
   - `app/providers/queries.py` (`derive_hero_photo` at `:80-91` + `derive_gallery` at `:94+` — Lane 2B.1 extends both to three-tier per design memo §5.2: owner-uploaded Photo row → legacy `attributes.hero_pin_photo_url` → Google photos)
   - `app/auth/dependencies.py` (Phase 2A.2-shipped — `require_user` + `get_current_user`; Phase 2B.1 upload route uses these; if 2A.2 hasn't shipped yet, halt — see §3 sub-phase dependency note)
   - `app/auth/claims.py` (Phase 2A.3-shipped — `find_existing_claim` helper that returns Claim if `(user_id, entity_id, status='verified')` matches; the upload route's claim-ownership check calls this; if 2A.3 hasn't shipped yet, halt)
   - `tests/conftest.py` (test session fixtures — your FTS tests will need either a Postgres skip marker OR seeded test data that passes under SQLite LIKE-equivalent fallback; see §6.4)
   - `alembic/versions/92ce4899dc08_account_lite_v01.py` (the Phase 2A.1 migration; your Lane 2B.1 migration chains off this head — unless 2A.2/2A.3 added migrations, in which case chain off whatever `alembic heads` reports)
   - `requirements.txt` (verify Pillow + boto3 are NOT yet present; you'll add both for 2B.1; check current pinned versions of related libs)
8. **Confirm R2 prereq is locked.** Report whether the operator has set the five canonical R2 env vars in Railway. If any are missing, **halt and report** before proceeding — the brief is authored against the canonical names; if the operator's Railway config diverges, the names need amending before 2B.1 ships. Also confirm whether the operator chose **Path A** (default `pub-<hash>.r2.dev` URL) or **Path B** (custom domain `cdn.havasuchat.com`) per operator_prereqs §2 step 5 — this affects `R2_PUBLIC_URL_BASE` value but no code changes.
9. Report all baseline values + confirm reads complete. Only then proceed to §1.

If any baseline value mismatches, any file has materially moved from these descriptions, any 2A sub-phase that 2B.1 depends on hasn't shipped, or R2 env vars aren't set, **HALT and report** before proceeding.

---

## §1 Why this lane exists

The directory has **zero owner-uploaded image storage and zero structured search**. Repo-wide grep confirms:

- **No `app/photos/` package; no `app/images/`; no Pillow on tree.** `requirements.txt` has no `Pillow` and no `boto3`. The only photo surfaces today are external URLs — `Provider.google_photo_refs: list[str] | None` (`app/db/models.py:83`) and `Provider.attributes.hero_pin_photo_url` (an operator-typed URL surfaced by `derive_hero_photo` at `app/providers/queries.py:80-91`). Both hotlink third-party URLs; neither is owner-controlled. A sponsor paying $79/mo for Verified Presence sees the same Google photo any free-tier listing shows.
- **No `tsvector`; no `pg_trgm`; no `to_tsquery`.** The chat tier 2 retrieval path at `app/chat/tier2_db_query.py:33+` is a chain of `ilike("%term%")` filters — each one a sequential scan when no functional index covers the column. The synonym-expansion helper `_category_needle_set` at `:548` is well-shaped (it'll port to FTS cleanly via `tsquery` OR clauses) but the LIKE-chain it currently feeds breaks around ~500 catalog rows or ~500 concurrent users per `architecture_gaps_for_full_vision_audit.md` §5.2.

Image storage gates the entire merchant-visual-feature half of the pivot product:

- **Verified Presence ($79/mo) sponsor sales** require owner-uploaded hero photo + gallery (Pivot §7)
- **Eat & Drink cards are photo-first** per Opus #4 — restaurants need owner-uploaded food + patio photos to make discovery feel right
- **Place pages need photos too** — operator field-trip captures of parks/dog parks/ramps; Google often has wrong or no photos for these
- **Future sponsor logo upload**, V2 review-attached photos, V2 user-uploaded venue photos — all branch off the Photo schema

Search index gates discovery at scale:

- **Search bar on home + category pages** needs full-text + facets + ranking
- **Chat tier 2 retrieval** quality is bottlenecked by the LIKE chain — Tier 3 LLM synthesis only sees the top N candidates Tier 2 returns; better retrieval directly improves answer quality
- **Pivot's 1500-3000 launch directory** is 10-30x the scale where LIKE chains stop being acceptable

**Texture rule reminder:** every existing chat-route response, every Provider profile render, every Tier 2 catalog lookup must produce **equivalent output** after Phase 2B as before. Search-bar is a net-new surface (zero regression risk). The chat tier 2 LIKE→FTS swap MUST preserve current synonym-expansion behavior (Voice battery 2026-05-08 tests at `tests/test_tier2_db_query_entity_pivot.py` are the regression bar — pytest stays green). Photo upload is a net-new authenticated surface visible only to verified claimants + admins.

---

## §2 Locked decisions (do not relitigate)

| # | Locked answer | Source |
|---|---|---|
| Storage backend | **Option B — Cloudflare R2.** S3-compatible via boto3 with `endpoint_url` swap. Zero egress fees. CDN edge built-in on public buckets. Free tier covers V1. | Image storage memo §2.2 + §3 |
| Image processing | **Pillow inline via FastAPI `BackgroundTasks`.** Per `background_job_infrastructure_decision.md` §6.4 (Option A V1). Three variants × two formats (thumbnail/medium/hero × WebP/JPEG). EXIF strip mandatory. SHA-256 dedup per entity. | Image storage memo §6 |
| **`Photo.entity_id` FK targets `entities.id`, NOT `providers.id` / `places.id`** | Phase 1's ENTITY schema unified the polymorphic target. The design memo §5.1 predates Phase 1's ship and shows a polymorphic `(entity_type, entity_id)` shape with no DB-level FK; master plan §4 Phase 2 Lane 2B implicitly amends to "polymorphic (entity_id) reference" — same amendment shape as Lane 2A's user_favorites/claims. App-layer validation on insert: look up `entities.id`, assert `entities.entity_type IN ('commercial', 'place')`. `Entity.entity_type` already discriminates; no duplicate column on `photos`. FK uses `ondelete="CASCADE"`. | Master plan §4 Phase 2 Lane 2B + Lane 2A FK amendment precedent |
| Search backend | **Option A — Postgres FTS + `pg_trgm`.** Generated `tsvector` columns + GIN indexes. Migration path to Meilisearch (Option B) deferred until quantitative triggers fire (>10k entries; >5 active facets; p95 >50ms). | Search memo §3 |
| FTS column anchored on `entities`, not `providers`/`events`/`programs` | Phase 1's ENTITY pivot means search must run against the unified entity row. `Entity.name` + `Entity.description` are the search surface. Synonym + name-trigram indexes on `entities.name`. Legacy `providers.provider_name` / `events.title` / `programs.title` are not re-indexed — Phase 1C reads already prefer Entity. | Phase 1 ENTITY pivot; search memo §4.1 needs adjusting from `providers.search_vector` to `entities.search_vector` |
| Variant sizes | Thumbnail 256×256, Medium 512×512, Hero 1280×720 (16:9). WebP quality 82 + JPEG quality 85 fallback. Original kept private (post-EXIF-strip), not served. | Image storage memo §6 stage 4 |
| MIME whitelist | `image/jpeg`, `image/png`, `image/webp`. **No SVG** (XSS surface). **No HEIC** in V1. **No GIF** in V1. MIME-sniff defense: declared content-type must match what Pillow decodes. | Image storage memo §7 |
| File size limit | 10 MB per upload. Enforced at both `Content-Length` and body-read. | Image storage memo §7 |
| Rate limits | 20 uploads/day per uploader; 50 photos per Place; 100 photos per Provider (per design memo's recommended cap; design memo §10 Q2 was "20 or 50 or 100" — locking the upper bound at 50 for Place, 100 for Provider per design memo §7); 50 uploads/day per IP. | Image storage memo §7 |
| EXIF strip | **Mandatory** — never serve photos with EXIF. Privacy / location-leak prevention. If strip fails, flag row `processing_error='exif_strip_failed'` rather than upload-with-EXIF. | Image storage memo §6 stage 2 + §7 |
| Storage key shape | `photos/<entity_type>/<entity_id>/<photo_id>/<variant>.<ext>` — random UUID, never the original filename. Prevents enumeration + path-traversal. | Image storage memo §4 step 5 |
| CDN cache headers | `Cache-Control: public, max-age=31536000, immutable`. Filenames include the photo UUID so immutability is safe; replacement = new URL. | Image storage memo §8 |
| Public URL strategy | Path A (`R2_PUBLIC_URL_BASE=https://pub-<hash>.r2.dev`) for V1 by default. Path B (custom domain `cdn.havasuchat.com`) is a config-only swap when operator wires DNS. Code reads `R2_PUBLIC_URL_BASE` env var — never hard-codes the host. | operator_prereqs §2 step 5 |
| FTS weights | A=name, B=description+google_primary_category, C=district, D=attributes — but anchored on Entity table after Phase 1 pivot. Mirror weights via Entity.name (A) + Entity.description (B); per-entity-type extension data (Provider.google_primary_category, Place.place_type, etc.) appended via the application-side `tsquery` builder rather than the generated column to keep schema simple. | Search memo §4.1 (Phase 1-adjusted) |
| Ranking heuristic | `ts_rank` × 100 base + bonuses: verification freshness (+30 if <30d, +15 if 30-90d), featured `+25`, currently_open `+30`, matching cuisine/sub-trade `+25`, matching district `+15`. Sum → ORDER BY DESC → top N (8 for chat Tier 2, 20 for search bar). | Search memo §4.4 |
| Sub-phase commit boundaries | Three sub-phases (2B.1 photos schema + R2 + Pillow + upload route; 2B.2 FTS migration + chat tier 2 swap; 2B.3 search bar UI + endpoint + close-out). Each ships green pytest. Operator commits each. | This brief §3 |

---

## §3 Sub-phase boundaries (the rhythm of this lane)

This lane will not ship in one session. The work splits into three sub-phases, each independently shippable + pytest-green. Halt-and-report after each.

### Phase 2B.1 — Photos schema + R2 client + Pillow pipeline + upload route (target: 3-4 days)

Add `photos` table per design memo §5.1 (amended to FK `entities.id`). New `app/photos/` package with `r2_client.py` (boto3 against R2 `endpoint_url`), `processor.py` (Pillow variants + EXIF strip + WebP/JPEG + SHA-256 dedup), and routes wired into the upload flow. Three new dependencies: `Pillow`, `boto3`, `python-multipart` (if not already pulled in by FastAPI). One Alembic migration chained off Phase 2A.1's `92ce4899dc08` (or whatever head is current). Extend `derive_hero_photo` + `derive_gallery` at `app/providers/queries.py` to three-tier (Photo row → legacy `hero_pin_photo_url` → Google). Fold `run_stuck_photo_sweep` into `_hourly_cleanup_loop` at `app/main.py:246` for the design memo §4 step 9 "stuck-uploading >24h → flagged" sweep.

**Sequencing dependency on Phase 2A.3:** the upload route uses `require_user` (Phase 2A.2-shipped) and `app/auth/claims.py::find_existing_claim` (Phase 2A.3-shipped) for the claim-ownership check. **You can author against this brief, but should not dispatch 2B.1 until 2A.3 has shipped.** If the operator dispatches 2B.1 before 2A.3, halt at §0 step 8 and report the dependency. 2B.2 (FTS) and 2B.3 (search bar) are dependency-free from Lane 2A — those CAN dispatch independently if Lane 2A is running slow.

**Acceptance:** photos table exists with FK to `entities.id` ON DELETE CASCADE + indexes + CHECK constraints (status, mime_type, optional entity_type if you carry the discriminator denormalized for query speed — see §4); `app/photos/r2_client.py` initializes a boto3 client against R2 endpoint + uploads bytes to a key; `app/photos/processor.py` decodes bytes, strips EXIF, computes SHA-256, generates 3 variants × 2 formats, returns URLs; upload route `POST /api/entities/<id>/photos` accepts multipart upload, validates MIME + size + claim ownership, persists row in `status='uploading'`, schedules `BackgroundTask` to process + upload + finalize → `status='live'`; `_hourly_cleanup_loop` extended; tests cover schema + Pillow pipeline (each stage independently) + R2 client mocked + upload route (auth + claim + MIME + size + dedup + size cap). Pytest stays green at 1543+ (+ ~30 new tests). Alembic head advances by one migration.

### Phase 2B.2 — Postgres FTS + pg_trgm + chat tier 2 LIKE→FTS swap (target: 3-4 days)

One Alembic migration: enable `pg_trgm` extension (Postgres only — guarded against SQLite); add generated `search_vector` tsvector column to `entities`; add GIN index on `entities.search_vector`; add `gin_trgm_ops` index on `entities.name`; add functional partial indexes on hot `Provider.attributes` facets per memo §4.3 (`emergency_service`, etc.) — these stay on legacy `providers` table since the JSON is there. New `app/search/` package with `fts.py` (FTS query builder consuming `Tier2Filters` shape from `app/chat/tier2_schema.py`) and `ranking.py` (the §4.4 ranking heuristic emitting SQL ORDER BY expression). Migrate `_query_providers_orm` + `_query_events` + `_query_programs` in `app/chat/tier2_db_query.py` from LIKE chains to FTS queries. **Preserve `_category_needle_set` synonym expansion at `:548`** — feed synonyms into `to_tsquery` OR clauses (`'plumber | plumbing | plumbers'` shape) instead of `or_(provider.category.ilike(...), ...)`. Preserve the Python-side `open_now` filter (~:946-954) — FTS doesn't change that path.

**SQLite-vs-Postgres handling:** `pg_trgm` extension, generated `tsvector` columns, and `websearch_to_tsquery` are Postgres-only. The migration must enable `pg_trgm` only when the bind is Postgres (per design memo §5 maintenance + tested via `op.get_bind().dialect.name == "postgresql"` guard). The `tsvector` generated column path needs an equivalent SQLite fallback or be skipped on SQLite. **Recommended approach (per Phase 1A `passive_deletes=True` SQLite-vs-Postgres precedent):** application-side FTS query builder branches on dialect — Postgres uses `search_vector @@ websearch_to_tsquery(...)`; SQLite test fallback uses `ilike` against `entities.name` + `entities.description` (preserving the current behavior). Tests for the FTS path that require Postgres semantics get `@pytest.mark.skip_on_sqlite` (or `pytest.mark.skipif(dialect == "sqlite", ...)`) and parity tests on SQLite cover the LIKE-equivalent fallback. See §6.4 for the full plan.

**Acceptance:** Postgres FTS migration applies cleanly to a Postgres dev DB (skip the bulk of the FTS test on SQLite, but the migration must not crash on SQLite — gated by `if dialect == "postgresql"`); `app/search/fts.py` exposes `build_fts_query(db, filters: Tier2Filters)` returning a SQLAlchemy select; `app/search/ranking.py` exposes `ranking_score_expr(...)` returning a SQL expression; chat tier 2 paths use the new query builder; synonym expansion preserved (`_category_needle_set` calls land in `tsquery` OR clauses); voice-battery tests (`tests/test_tier2_db_query_entity_pivot.py` + chat-integration tests) stay green; new tests cover the FTS path on Postgres (skip-on-sqlite) + the SQLite fallback parity (asserts equivalent row sets); ranking-heuristic tests cover each bonus tier independently. Pytest stays green; new tests ~15-25.

### Phase 2B.3 — Search bar UI + endpoint + ranking close-out (target: 1-2 days)

New `GET /api/search` endpoint accepting `q`, optional facet params (`category`, `district`, `entity_type`), pagination cursor. Returns ranked entities as JSON. Search bar UI on `app/templates/home.html` (top of page) + `app/templates/provider_profile.html` (header). Minimal JS: form submit → fetch JSON → render dropdown of top 8 results with click-through to entity profile. Anonymous-viewer regression coverage — `/api/search` is public, no auth gate. Add the search endpoint to the master plan §4 Phase 2 Lane 2B "Shipped" line.

**Acceptance:** `/api/search?q=plumber` returns ranked JSON (top 20); search bar on home + profile pages submits to endpoint + renders results inline; anonymous viewers can use the search bar (no auth gate); ranking heuristic from 2B.2 produces sensible top-N (anchor a couple of tests with seeded data — "plumber" query returns plumber entities ranked by verification freshness + featured); new tests ~10-15.

### Important — phase boundary etiquette

After completing each sub-phase:

1. Confirm `python -m pytest -q` is green and report final count.
2. Confirm `python -m ruff check .` is clean.
3. Confirm `python -m alembic upgrade head` applies cleanly against a fresh dev DB. For 2B.2 specifically: confirm it applies cleanly against both a SQLite fresh DB (skipping the FTS-specific DDL) and Postgres (executing the full DDL).
4. Produce the final report per §12 for THAT sub-phase only.
5. **STOP. Do not start the next sub-phase.** Operator commits the current sub-phase and re-dispatches you (likely in a fresh session) for the next.

If you discover mid-sub-phase that the scope is bigger than estimated, **halt early** and report what's done + what's outstanding. Do not push past a half-broken state to "make progress."

---

## §4 Target schema in detail

One new table — `photos` — in 2B.1. One additive column + extension enable + indexes on `entities` in 2B.2. Postgres portability rules per Phase 2A.1 precedent: every Boolean default uses `sa.true()` / `sa.false()`; every timestamp default uses `sa.func.now()`; no raw SQL in `op.execute()` unless verified portable. FTS-specific DDL is gated on `op.get_bind().dialect.name == "postgresql"`.

### §4.1 `Photo` model — append to `app/db/models.py`

```python
class Photo(Base):
    """Owner-uploaded photo for an Entity (commercial / place in V1).

    FK to entities.id with ON DELETE CASCADE (master plan §4 Phase 2 amendment
    over the design memo's polymorphic-no-FK shape — Phase 1's ENTITY pivot
    unifies the target). Entity.entity_type discriminates; no duplicate column
    on photos. App-layer validation on insert: assert
    entities.entity_type IN ('commercial', 'place'). Events + programs are
    NOT photo-uploadable in V1 — guarded at the route level.
    """

    __tablename__ = "photos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('uploading', 'processing', 'live', 'flagged', 'deleted')",
            name="ck_photos_status",
        ),
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_photos_mime_type",
        ),
        Index("ix_photos_entity_id", "entity_id"),
        Index("ix_photos_uploaded_by_user_id", "uploaded_by_user_id"),
        Index("ix_photos_status", "status"),
        Index("ix_photos_image_hash", "image_hash"),
        # Composite for the "per-entity dedup lookup" path in processor.py.
        Index("ix_photos_entity_hash_status", "entity_id", "image_hash", "status"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid4())
    )
    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Upload metadata
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 of post-EXIF-strip pixel bytes; per-entity dedup.

    # Storage references — R2 keys + public URLs
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    # R2 object key prefix, e.g. "photos/commercial/<entity_id>/<photo_id>/".
    cdn_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Canonical public URL for the "medium" variant.
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    medium_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    hero_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Owner-facing fields
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_hero: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Exactly-one-hero-per-entity enforced at application layer.
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="uploading", server_default="uploading"
    )
    processing_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Allowed values: 'decode_failed' | 'too_small' | 'unsafe_mime' |
    # 'moderation_rejected' | 'user_deleted' | 'exif_strip_failed' | 'duplicate'.

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[entity_id])
    uploader: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by_user_id])
```

**Why FK to `entities.id` (vs polymorphic no-FK).** Design memo §5.1 shows polymorphic `(entity_type, entity_id)` with no DB-level FK because Phase 1 hadn't shipped yet. Phase 1's ENTITY pivot unifies; same amendment as Lane 2A. Polymorphic discriminator already lives on `entities.entity_type` (`app/db/models.py:640`); duplicating on `photos.entity_type` is denormalization without a query-shape benefit (photos-for-entity queries already filter on `entity_id`, which is indexed; entity_type filtering is application-layer post-fetch).

**Why no PhotoVariant child table.** All three variants ship atomically; never a state where thumbnail exists but medium doesn't. Three String columns + the storage_key prefix are simpler than a child table for the bounded variant set. V2 may refactor if owner-configurable variants become a thing.

**`Entity.photos` relationship.** Add to the Entity class via anchored Edit at `app/db/models.py:~685` (after `sponsorship_slots`):

```python
photos: Mapped[list["Photo"]] = relationship(
    "Photo",
    primaryjoin="and_(foreign(Photo.entity_id) == Entity.id, Photo.status == 'live')",
    viewonly=True,
    order_by="Photo.display_order",
)
```

`viewonly=True` because the filter on `status='live'` means SQLAlchemy shouldn't attempt write cascades through this relationship — drops/inserts go through the application code, not the relationship.

### §4.2 `entities.search_vector` generated column + indexes (Phase 2B.2)

Postgres only. The migration runs only when `op.get_bind().dialect.name == "postgresql"`. SQLite dev DBs skip this DDL entirely — the FTS fallback uses `ilike`.

```sql
-- In the Alembic migration's upgrade(), conditionally:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE entities ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B')
  ) STORED;

CREATE INDEX ix_entities_search_vector ON entities USING gin(search_vector);
CREATE INDEX ix_entities_name_trgm ON entities USING gin (name gin_trgm_ops);
```

**Per-entity-type extension data (e.g., `Provider.google_primary_category`, `Place.place_type`) is NOT in the generated column** — Phase 1's ENTITY pivot left legacy columns on the per-type tables. Adding them to `entities.search_vector` would require a custom function or denormalization. Application-side `fts.py` builds the per-type secondary `tsquery` clause using the legacy columns (JOIN provider/place/event/program) when category-narrowing is requested. This avoids a schema-level cross-table generated column (Postgres supports it via PL/pgSQL but it's significantly more migration complexity for marginal query speedup at V1 scale).

**Functional partial indexes on hot `Provider.attributes` facets** stay on the legacy `providers` table (the JSON lives there; Phase 3 will pull these onto `entities`). Per memo §4.3:

```sql
CREATE INDEX ix_providers_emergency_service
  ON providers ((attributes ->> 'emergency_service'))
  WHERE attributes ->> 'emergency_service' = 'true';
```

Ship `emergency_service` + `dog_friendly` as the V1 hot facets (mirroring memo §4.3). Other facets add when telemetry warrants.

### §4.3 Migration shape

Two migrations, one per sub-phase:

- **2B.1 migration** — `<rev>_photos_table.py` chains off Phase 2A.1's `92ce4899dc08` (or current head if 2A.2/2A.3 added one). Single `op.create_table('photos', ...)` + indexes + CHECK constraints. Reversible: `downgrade()` is `op.drop_table('photos')`. No data backfill.
- **2B.2 migration** — `<rev>_entities_fts_pgtrgm.py` chains off the 2B.1 head. Conditional Postgres-only DDL guarded by dialect check. The pattern:

```python
def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute("""
            ALTER TABLE entities ADD COLUMN search_vector tsvector
              GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(description, '')), 'B')
              ) STORED
        """)
        op.execute(
            "CREATE INDEX ix_entities_search_vector ON entities USING gin(search_vector)"
        )
        op.execute(
            "CREATE INDEX ix_entities_name_trgm ON entities USING gin (name gin_trgm_ops)"
        )
        op.execute("""
            CREATE INDEX ix_providers_emergency_service
              ON providers ((attributes ->> 'emergency_service'))
              WHERE attributes ->> 'emergency_service' = 'true'
        """)
        op.execute("""
            CREATE INDEX ix_providers_dog_friendly
              ON providers ((attributes ->> 'dog_friendly'))
              WHERE attributes ->> 'dog_friendly' = 'true'
        """)
    # SQLite path: no-op. FTS uses ilike fallback at query time.


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_providers_dog_friendly")
        op.execute("DROP INDEX IF EXISTS ix_providers_emergency_service")
        op.execute("DROP INDEX IF EXISTS ix_entities_name_trgm")
        op.execute("DROP INDEX IF EXISTS ix_entities_search_vector")
        op.execute("ALTER TABLE entities DROP COLUMN IF EXISTS search_vector")
        # Don't drop pg_trgm — may be used by other tables.
```

Verify both `alembic upgrade head` and `alembic downgrade -1 && alembic upgrade head` cycle on a SQLite dev DB AND a Postgres dev DB. SQLite cycle is the easy one (the dialect guard makes it a no-op); Postgres cycle is the harder one — only verifiable if Cursor has Postgres available locally, otherwise document in the §12 report that Postgres cycle wasn't verified locally and operator should verify in Railway staging before merging.

---

## §5 Phase 2B.1 — Photos schema + R2 + Pillow + upload route (target: 3-4 days)

### §5.1 New package: `app/photos/`

```
app/photos/
    __init__.py             # docstring + re-exports
    r2_client.py            # boto3 against R2 endpoint; upload + delete helpers
    processor.py            # Pillow pipeline (decode + EXIF strip + variants + dedup)
    routes.py               # POST /api/entities/<id>/photos; DELETE /api/photos/<id>; etc.
    schemas.py              # Pydantic response shapes
    sweep.py                # run_stuck_photo_sweep() called from _hourly_cleanup_loop
```

Mirror the `app/auth/` package shape from Phase 2A.

### §5.2 New file: `app/photos/r2_client.py`

Boto3 against R2 `endpoint_url`. Env vars per operator_prereqs §2 step 6. Configuration error → `RuntimeError` at module init. Functions:

- `get_r2_client() -> boto3.client` — lazy singleton (per-process). Reads env vars; raises `RuntimeError` with a clear message if any are missing.
- `upload_bytes(key: str, content: bytes, content_type: str) -> str` — uploads bytes to R2 with `Cache-Control: public, max-age=31536000, immutable` + content-type. Returns the public URL constructed from `R2_PUBLIC_URL_BASE + "/" + key`.
- `delete_object(key: str) -> None` — best-effort delete (used by V2 photo-delete path; V1 V1 sets `status='deleted'` and leaves the object on R2 to CDN-expire).
- `build_public_url(key: str) -> str` — joins `R2_PUBLIC_URL_BASE` + key cleanly (handles trailing/leading slash quirks).

Env var contract:
- `R2_ACCESS_KEY_ID` — boto3 `aws_access_key_id`
- `R2_SECRET_ACCESS_KEY` — boto3 `aws_secret_access_key`
- `R2_ENDPOINT_URL` — boto3 `endpoint_url` (e.g., `https://<account>.r2.cloudflarestorage.com`)
- `R2_BUCKET_NAME` — bucket name passed to `put_object`
- `R2_PUBLIC_URL_BASE` — public URL prefix (e.g., `https://pub-abc.r2.dev` or `https://cdn.havasuchat.com`)

`region_name` defaults to `"auto"` per Cloudflare R2 convention. Signature version `s3v4`.

### §5.3 New file: `app/photos/processor.py`

Six-stage pipeline per design memo §6. Pure-function shape — each stage is testable independently. Stages:

1. `decode_and_validate(content: bytes) -> PIL.Image.Image | ProcessingError` — `Image.open(BytesIO(content))` + dimension check + extrema-check for all-black/all-white reject. ProcessingError variants: `decode_failed`, `too_small`, `unsafe_mime` (caller passes declared MIME for sniff defense).
2. `strip_exif(img: PIL.Image.Image) -> PIL.Image.Image` — re-save without EXIF segment + convert to sRGB if profile differs.
3. `compute_hash(img: PIL.Image.Image) -> str` — SHA-256 of post-EXIF-strip pixel bytes (the `.tobytes()` output).
4. `generate_variants(img: PIL.Image.Image) -> dict[str, dict[str, bytes]]` — returns `{"thumbnail": {"webp": ..., "jpeg": ...}, "medium": {...}, "hero": {...}}`. Dimensions per locked decisions table. Quality WebP=82, JPEG=85. Center-crop fill mode (uses Pillow's `ImageOps.fit`).
5. `upload_all_variants(r2_client, storage_key_prefix: str, variants: dict) -> dict[str, dict[str, str]]` — uploads each variant + returns the URL map.
6. `finalize_photo_row(db, photo_id, variants_urls, width, height, file_size, image_hash) -> None` — single UPDATE that flips `status='live'` + populates URL columns + image_hash + dimensions. Wrapped in its own DB transaction.

The orchestrator `process_uploaded_photo(photo_id: str, content: bytes, declared_mime: str) -> None` is the BackgroundTask entry point. It coordinates the six stages; on any stage failure, flips the row to `status='flagged'` with the appropriate `processing_error` and short-circuits. Idempotent: re-running against a row already in `status='live'` is a no-op (logged at WARNING).

### §5.4 New file: `app/photos/routes.py`

```python
from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session as SqlSession

from app.auth.claims import find_existing_claim  # Phase 2A.3-shipped
from app.auth.dependencies import require_user  # Phase 2A.2-shipped
from app.db.database import get_db
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE
from app.db.models import Entity, Photo, User
from app.photos.processor import process_uploaded_photo

router = APIRouter()

ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/api/entities/{entity_id}/photos", status_code=201)
async def upload_photo(
    entity_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    caption: Annotated[str | None, Form()] = None,
    current_user: Annotated[User, Depends(require_user)] = ...,
    db: Annotated[SqlSession, Depends(get_db)] = ...,
):
    # 1. Lookup entity + assert photo-eligible.
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    if entity.entity_type not in (ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE):
        raise HTTPException(status_code=400, detail="entity_not_photo_uploadable")

    # 2. Authz: admin OR verified claim for this entity.
    if current_user.role != "admin":
        claim = find_existing_claim(db, current_user.id, entity_id)
        if claim is None or claim.status != "verified":
            raise HTTPException(status_code=403, detail="claim_not_verified")

    # 3. MIME whitelist + Content-Length cheap reject.
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="unsupported_mime_type")

    # 4. Read body with hard size cap (defense against missing/spoofed CL).
    content = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="file_too_large")

    # 5. Per-entity + per-uploader rate limit checks (helper in app/photos/limits.py).
    # ... (omitted; mirror app/auth/email_helpers rate-limit shape)

    # 6. Create Photo row in status='uploading'; schedule background processing.
    photo = Photo(
        entity_id=entity_id,
        uploaded_by_user_id=current_user.id,
        original_filename=file.filename,
        mime_type=file.content_type,
        storage_key="",  # populated by processor finalize step
        caption=caption,
        status="uploading",
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    background_tasks.add_task(
        process_uploaded_photo,
        photo_id=photo.id,
        content=content,
        declared_mime=file.content_type,
    )

    return {"photo_id": photo.id, "status": "uploading"}
```

Additional routes: `DELETE /api/photos/<id>` (sets `status='deleted'`; soft-delete only; admin OR uploader of the photo OR verified claimant); `POST /api/photos/<id>/set-hero` (atomically clears `is_hero` on siblings + flips this row's `is_hero=True`); `POST /api/photos/<id>/reorder` (accepts a new `display_order` int).

### §5.5 New file: `app/photos/sweep.py`

```python
def run_stuck_photo_sweep() -> int:
    """Sweep Photo rows stuck in status='uploading' for >24h to 'flagged'.

    Called from _hourly_cleanup_loop alongside run_expired_review_cleanup.
    Returns count of rows swept (for logging / tests).
    """
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    with SessionLocal() as db:
        stuck = (
            db.query(Photo)
            .filter(Photo.status == "uploading", Photo.created_at < cutoff)
            .all()
        )
        for p in stuck:
            p.status = "flagged"
            p.processing_error = "decode_failed"
        db.commit()
        return len(stuck)
```

### §5.6 Anchored Edit on `app/main.py:_hourly_cleanup_loop`

Per design memo §4 step 9 + the Phase 2A brief §10 "fold into `_hourly_cleanup_loop`" pattern: append `run_stuck_photo_sweep` alongside `run_expired_review_cleanup`. Both run hourly.

```python
async def _hourly_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        await asyncio.to_thread(run_expired_review_cleanup)
        await asyncio.to_thread(run_stuck_photo_sweep)
```

Also add the router include for `app/photos/routes.py` after the existing `include_router` block.

### §5.7 Anchored Edit on `app/providers/queries.py` — `derive_hero_photo` + `derive_gallery`

Per design memo §5.2. Three-tier shape:

```python
def derive_hero_photo(provider: Provider) -> Optional[str]:
    # Tier 1 (new): owner-uploaded Photo row flagged is_hero, status='live'.
    if provider.entity_id is not None:
        for photo in (provider.entity.photos or []):
            if photo.is_hero and photo.status == "live":
                if photo.hero_url:
                    return photo.hero_url
                break
    # Tier 2 (existing fallback 1): operator-pinned URL.
    attrs = provider.attributes or {}
    pinned = attrs.get("hero_pin_photo_url")
    if pinned:
        return pinned
    # Tier 3 (existing fallback 2): first Google photo.
    photos = provider.google_photo_refs or []
    if photos:
        return photos[0]
    return None
```

`derive_gallery` extends similarly — owner Photo rows (`status='live'`, not the hero) in `display_order`, then Google photos with hero excluded. Anchor edit by current line offsets (re-grep `derive_hero_photo` to find them; the design memo cites `:80-91` but Phase 1C/1D edits may have shifted offsets).

### §5.8 New files: `app/photos/schemas.py` + `app/photos/limits.py`

`schemas.py` — Pydantic response models (`PhotoUploadResponse`, `PhotoListItem`).

`limits.py` — rate-limit helpers:

- `check_uploader_daily_cap(db, user_id) -> bool` — `count(*) FROM photos WHERE uploaded_by_user_id = ? AND created_at > now - 24h` >= 20 → True.
- `check_entity_photo_cap(db, entity_id, entity_type) -> bool` — counts live + uploading photos against the per-entity cap (50 for place, 100 for commercial).

### §5.9 Tests — new files

`tests/test_photos_schema.py`:
1. `photos` table exists after migration
2. Columns + types + nullability (parametric per column)
3. CHECK constraints on `status` + `mime_type` reject invalid values (IntegrityError)
4. FK `entity_id` ON DELETE CASCADE: delete the entity, photo rows cascade-delete
5. FK `uploaded_by_user_id` ON DELETE CASCADE: delete the user, their photo rows cascade
6. Indexes exist (ix_photos_entity_id, ix_photos_image_hash, etc.)
7. `Entity.photos` relationship returns only `status='live'` rows in display_order
8. Phase 1A `passive_deletes=True` precedent: verify SQLite cascade works without the SQLAlchemy NULL-before-cascade dance (if cascade test fails on SQLite, follow Phase 1A's `engine.dispose()` workaround in `tests/test_entity_schema.py`)

`tests/test_photos_processor.py`:
1. `decode_and_validate` accepts a 256×256 valid JPEG
2. `decode_and_validate` rejects all-black image as `decode_failed`
3. `decode_and_validate` rejects 100×100 image as `too_small`
4. `decode_and_validate` rejects bytes that aren't an image as `decode_failed`
5. `strip_exif` removes EXIF segment (load fixture JPEG with EXIF; assert post-strip has none)
6. `compute_hash` produces deterministic SHA-256 for the same image bytes
7. `generate_variants` produces 3 variants × 2 formats; thumbnail is 256×256; hero is 1280×720; WebP smaller than JPEG (sanity check)
8. `process_uploaded_photo` end-to-end with R2 mocked: row transitions uploading → live; URLs populated
9. Dedup: second upload of same image bytes for same entity → row flagged `duplicate`
10. R2 upload failure (mock raises) → row stays in `uploading` (sweep handles later)

`tests/test_photos_r2_client.py`:
1. `get_r2_client()` raises `RuntimeError` when env vars missing
2. `get_r2_client()` constructs a boto3 client with the R2 endpoint when env vars present (mock boto3)
3. `upload_bytes` calls `put_object` with correct key + Cache-Control header (mock)
4. `build_public_url` joins prefix + key correctly (handles trailing/leading slash)

`tests/test_photos_routes.py`:
1. Anonymous POST → 401
2. Authenticated POST without verified claim → 403 (claim is pending or missing)
3. Authenticated POST with verified claim → 201 + photo row in `status='uploading'`
4. Admin POST without claim → 201 (admin bypass)
5. POST with `image/gif` MIME → 400
6. POST with file >10 MB → 413
7. POST for entity_type='event' → 400 (not photo-uploadable)
8. POST for non-existent entity_id → 404
9. POST hitting per-entity cap (100th photo on a provider) → 429
10. POST hitting per-uploader daily cap (21st upload today) → 429
11. DELETE by uploader → row → `status='deleted'`
12. DELETE by non-uploader / non-admin / non-claimant → 403
13. POST `/set-hero` clears is_hero on siblings + flips on target

`tests/test_photos_sweep.py`:
1. Photo row stuck in `uploading` >24h → swept to `flagged` with `processing_error='decode_failed'`
2. Photo row stuck in `uploading` <24h → untouched

`tests/test_provider_queries_hero_photo.py` (extend or new):
1. `derive_hero_photo` returns Photo.hero_url when owner-uploaded hero exists
2. Falls back to `hero_pin_photo_url` when no owner Photo
3. Falls back to `google_photo_refs[0]` when neither owner Photo nor pinned URL
4. Returns None when none of the three tiers populated

### §5.10 Phase 2B.1 acceptance + commit

After 2B.1:
- pytest count: 2A.3 baseline + (40-50 new tests) → ~1610-1640
- alembic head advances by one migration
- ruff clean
- `python -m alembic upgrade head` against fresh dev DB passes
- ZERO behavior change on chat-route, /provider/<slug> for anonymous viewers, /home, /admin
- Manual smoke: with `R2_ACCESS_KEY_ID` etc. set, upload a real JPEG to a test commercial Entity via curl — verify R2 bucket has the variants + row transitions to `status='live'`

HALT here. Produce the §12 report for 2B.1. Operator commits, then re-dispatches for 2B.2.

---

## §6 Phase 2B.2 — Postgres FTS + pg_trgm + chat tier 2 LIKE→FTS swap (target: 3-4 days)

### §6.1 New package: `app/search/`

```
app/search/
    __init__.py
    fts.py        # FTS query builder (dialect-aware)
    ranking.py    # ranking_score_expr — emits SQL CASE/COALESCE for ORDER BY
    sqlite_fallback.py  # ilike-based fallback for SQLite tests + dev
```

### §6.2 Migration `<rev>_entities_fts_pgtrgm.py`

Per §4.3 shape. Conditional on Postgres. Idempotent (`CREATE EXTENSION IF NOT EXISTS`, `CREATE INDEX` only — re-running is fine; or use `CREATE INDEX IF NOT EXISTS` for explicit re-run safety). Reversible via `DROP INDEX` + `DROP COLUMN` in `downgrade()`. SQLite path is no-op (the dialect guard makes the migration cleanly applicable on either backend).

### §6.3 New file: `app/search/fts.py`

Exposes the public API the chat tier 2 + search bar consume. Key functions:

- `build_fts_query(db: Session, filters: Tier2Filters, *, entity_type: str | None = None, limit: int = 8) -> Select` — returns a SQLAlchemy `select` statement.
- `_build_tsquery_string(filters: Tier2Filters) -> str | None` — composes the `tsquery` string from `filters.entity_name` and `filters.category` (with synonym expansion from `_category_needle_set`). Returns None when no text filter is set.
- Dialect branching: at query-build time, check `db.bind.dialect.name`. Postgres uses `search_vector @@ websearch_to_tsquery('english', :term)`. SQLite falls back to `app/search/sqlite_fallback.py::build_ilike_query` which mirrors the current LIKE-chain shape from `tier2_db_query.py:33+`.

The `tsquery` string composition is the only non-trivial part:

```python
def _build_tsquery_string(filters: Tier2Filters) -> str | None:
    parts: list[str] = []
    if filters.entity_name and filters.entity_name.strip():
        # Quote-escape for tsquery safety; use & for AND across tokens.
        tokens = [t for t in filters.entity_name.split() if t]
        if tokens:
            parts.append("(" + " & ".join(tokens) + ")")
    if filters.category and filters.category.strip():
        needles = _category_needle_set(filters.category)  # imports from app.chat.tier2_db_query
        if needles:
            # Synonym group → OR clause.
            parts.append("(" + " | ".join(needles) + ")")
    if not parts:
        return None
    return " & ".join(parts)
```

The `& ` (AND across user terms) preserves the implicit "all terms must match" semantics of the current LIKE chain — the LIKE chain ANDs implicitly through repeated `where` clauses; FTS preserves that with explicit `&`. Synonym groups OR within themselves (`|`) and AND with the other parts (`&`).

### §6.4 New file: `app/search/sqlite_fallback.py`

The SQLite fallback path. Existence of this module makes the FTS swap **safe** on the test DB — tests that ran on SQLite under the LIKE chain continue to pass under the same LIKE chain via the fallback, while Postgres execution takes the FTS path.

```python
def build_ilike_query(db, filters: Tier2Filters, *, entity_type: str | None = None,
                      limit: int = 8) -> Select:
    """SQLite + dev-DB fallback. Mirrors the current pre-FTS query shape from
    tier2_db_query.py:33+. Preserves synonym expansion behavior. Does NOT use
    ranking score (ts_rank is Postgres-only); returns rows in insertion order.
    """
    q = select(Entity).where(Entity.is_active.is_(True))
    if entity_type:
        q = q.where(Entity.entity_type == entity_type)
    if filters.entity_name and filters.entity_name.strip():
        needle = f"%{filters.entity_name.strip()}%"
        q = q.where(or_(Entity.name.ilike(needle), Entity.description.ilike(needle)))
    if filters.category and filters.category.strip():
        needles = _category_needle_set(filters.category)
        if needles:
            conds = [Entity.name.ilike(f"%{n}%") for n in needles]
            conds += [Entity.description.ilike(f"%{n}%") for n in needles]
            q = q.where(or_(*conds))
    return q.limit(limit)
```

Tests that need pure-FTS semantics (e.g., assert `ts_rank` ordering) get `@pytest.mark.skipif(dialect == "sqlite", ...)` per §6.7.

### §6.5 New file: `app/search/ranking.py`

The §4.4 ranking heuristic. Emits a SQL expression for ORDER BY:

```python
def ranking_score_expr(entity_alias=Entity, *,
                       has_text_query: bool = True,
                       provider_alias=None,
                       open_now_flag=None,
                       current_district: str | None = None,
                       current_category: str | None = None) -> ColumnElement:
    """Compose the ranking score expression.

    Score = FTS rank (0-100) + bonuses:
    - verification freshness: +30 (<30d), +15 (30-90d), 0 (>90d)
    - featured: +25
    - currently open: +30
    - matching cuisine/sub-trade: +25
    - matching district: +15
    """
    # FTS contribution — Postgres only. For SQLite fallback the caller passes
    # has_text_query=False and the expression evaluates to 0 for the FTS part.
    # Build CASE expressions for each bonus tier.
    # Sum all → expose as ColumnElement.
    ...
```

Implementation uses `sqlalchemy.sql.case` / `func.coalesce` to compose the SQL CASE expression. The bonuses are deterministic per-row (no FTS-specific deps), so the same expression works under SQLite fallback (minus the FTS rank term).

### §6.6 Edit `app/chat/tier2_db_query.py` — migrate LIKE chains to FTS

Anchored Edit per dispatch_protocol Rule 1+6. The three migration targets:

1. **`_query_providers_orm` at ~:811-892.** Replace the `or_(Provider.category.ilike(...), Provider.google_primary_category.ilike(...))` chain with a JOIN against `entities` + the FTS predicate from `app/search/fts.py::build_fts_query`. Preserve the legacy outerjoin-Entity orphan fallback (Phase 1C precedent) — pre-FTS this is an `outerjoin Entity` + `or_(entity_id IS NULL, Entity.entity_type == 'commercial')` shape. Post-FTS: the orphan branch returns zero rows (no Entity → no `search_vector` → no FTS match), which is the correct behavior — orphan Providers don't surface in search until they're Phase-1D-dual-write linked. Document this in §12 as a deliberate consequence.

2. **`_query_events` at ~:683.** Same shape; Entity FK is `events.entity_id`. ENTITY_TYPE_EVENT discriminator. Synonym expansion preserved.

3. **`_query_programs` at ~:866.** Same shape; Entity FK is `programs.entity_id`. ENTITY_TYPE_PROGRAM discriminator.

**Preserve every other piece of `tier2_db_query.py`:**
- `_category_needle_set` at :548 — UNCHANGED. Its callers (`:401`, `:450`, `:574`, `:968`) now feed FTS instead of LIKE, but the helper itself ships intact.
- Python-side `open_now` filter (~:946-954) — UNCHANGED. FTS doesn't change open-now logic.
- Time-window / day-of-week / span filters on Event — UNCHANGED.
- Time-bucket clustering — UNCHANGED.

The migration is **substitution at the where-clause layer**, not a rewrite of the query shape. Done right, the diff is bounded to ~150-200 lines of net change concentrated in the three `_query_*` functions.

### §6.7 Tests — FTS path coverage + parity coverage

`tests/test_search_fts.py` — Postgres-only path:
1. `_build_tsquery_string` composes correct tsquery from `entity_name='plumber repair'` → `(plumber & repair)`
2. `_build_tsquery_string` adds synonym group: `category='barbershop'` → expansion includes `barber | barbershop` etc.
3. Combined: name + category → `(plumber & repair) & (plumber | plumbing | plumbers)`
4. `build_fts_query` returns rows ranked by `ts_rank` when Postgres (skip on sqlite)
5. `gin_trgm_ops` index speeds up fuzzy match (smoke test — assert query plan uses the index; relaxed assertion since EXPLAIN parsing is brittle)

All tests in this file marked `@pytest.mark.skipif(dialect == "sqlite", reason="FTS is Postgres-only")` (or whatever helper your conftest provides — see §6.4 for the skip helper).

`tests/test_search_sqlite_fallback.py` — SQLite-path parity:
1. `build_ilike_query` produces the same row set as the pre-FTS `_query_providers_orm` for a battery of fixture queries
2. Synonym expansion preserved end-to-end (use the existing voice-battery seeded data)
3. Open-now Python filter still post-filters correctly

`tests/test_search_ranking.py` — dialect-agnostic ranking heuristic:
1. `ranking_score_expr` adds +25 for `featured=True` rows
2. Adds +30 for `last_verified_at < 30 days ago`
3. Adds +15 for `last_verified_at 30-90 days ago`
4. Adds 0 for `last_verified_at > 90 days ago` or NULL
5. Open-now bonus adds +30 (caller passes the flag; SQL CASE)

Regression coverage — the existing tier 2 voice battery tests at `tests/test_tier2_db_query_entity_pivot.py` and `tests/test_chat_route_integration.py` MUST stay green. These tests run on SQLite + take the fallback path; if they fail, the fallback diverges from the original LIKE chain shape.

### §6.8 Phase 2B.2 acceptance + commit

After 2B.2:
- pytest count: 2B.1 baseline + ~15-25 new tests → ~1635-1665
- alembic head advances by one migration
- ruff clean
- `python -m alembic upgrade head` against fresh SQLite dev DB passes (FTS DDL is a no-op)
- Voice battery tests + chat integration tests stay green (synonym expansion preserved)
- ZERO behavior change for anonymous viewers + chat clients on SQLite
- Manual smoke (operator can run against staging Postgres): a query for "plumber" returns ranked Provider entities; a fuzzy query "plummber" returns the same providers via `pg_trgm` similarity

HALT. Produce §12 report. Operator commits, then re-dispatches for 2B.3.

---

## §7 Phase 2B.3 — Search bar UI + endpoint + close-out (target: 1-2 days)

### §7.1 New route: `GET /api/search`

Lives at `app/search/routes.py` (new file). Mirrors the `app/photos/routes.py` shape from 2B.1.

- Query params: `q` (required), `category` (optional), `district` (optional), `entity_type` (optional, default any), `limit` (default 20, max 50), `cursor` (optional pagination — opaque base64).
- No auth gate — search is public.
- Calls `app/search/fts.py::build_fts_query` with the parsed filters; applies the ranking from `app/search/ranking.py`; returns JSON `{results: [...], next_cursor: str | None}`.
- Result shape: `{entity_id, entity_type, slug, name, description, district, hero_url}` per row.

### §7.2 Search bar UI

Two templates touched via anchored Edit:

- `app/templates/home.html` — add a search bar near the top (above the chat surface OR above the featured-providers section; UX call — match existing visual treatment). Single text input + submit button + a results-dropdown div that JS populates.
- `app/templates/provider_profile.html` — small search affordance in the header (matches the home-page treatment).

New JS module `app/static/search.js` (or inline if the project's existing pattern is inline — grep for existing JS file layouts). Submits form to `/api/search?q=...` via fetch, renders top 8 results in the dropdown with click-through links to entity profiles. No frameworks; vanilla JS to match existing project style (verify by grepping `app/static/` and `app/templates/` for Vue/React/HTMX usage).

Anonymous-viewer regression: search bar visible + functional for anonymous viewers. No `current_user` requirement.

### §7.3 Tests — new file `tests/test_search_route.py`

1. `GET /api/search?q=plumber` returns ranked JSON (top 20)
2. Anonymous viewer can call the endpoint (no auth gate)
3. `q` missing → 400
4. Filter combinations: `?q=coffee&entity_type=commercial`
5. Pagination cursor round-trips correctly
6. Result shape includes `hero_url` (uses the Photo+derive-hero-photo chain from 2B.1)
7. Voice-battery synonym expansion works via the search bar (test that `q=barbershop` returns barber-tagged providers)
8. Search bar UI rendered on home + profile pages (template smoke test)

### §7.4 Phase 2B.3 acceptance + commit

After 2B.3:
- pytest count: 2B.2 baseline + ~10-15 new tests → ~1650-1680
- alembic head unchanged (no migration in 2B.3)
- ruff clean
- Manual smoke: search bar on `/home` submits → renders results dropdown with rank-ordered entities
- Master plan §4 Phase 2 Lane 2B gets a "Shipped: <date> + commit SHA" line added by operator after commits

HALT. Produce the §12 close-out report including a Phase 2 summary: Phase 2 Lane 2B complete. If Lane 2A has also completed, Phase 2 is shipped end-to-end; next dispatchable phase is Phase 3 (v1.1 schema pass — districts, alerts, category taxonomy rewrite).

---

## §8 What to do, in order (across all three sub-phases)

1. §0 baseline confirmation. Report values. Confirm reads complete. **Confirm Phase 2A.3 has shipped** before dispatching 2B.1 (or 2B.2 can dispatch independently if 2A is running slow). Confirm R2 env vars in Railway.
2. **Phase 2B.1:** Photos schema + R2 client + Pillow processor + upload route + sweep + provider-queries three-tier hero. Halt + report + operator commits.
3. **(Operator re-dispatches you in a new session.)**
4. **Phase 2B.2:** FTS migration + `app/search/fts.py` + `app/search/ranking.py` + SQLite fallback + tier 2 LIKE→FTS swap. Halt + report + operator commits.
5. **(Operator re-dispatches.)**
6. **Phase 2B.3:** `/api/search` route + search bar UI on home + profile + integration tests. Halt + report + operator commits.
7. Master plan §4 Phase 2 Lane 2B gets a "Shipped: <date> + commit SHA + actual effort vs estimate" line by operator after 2B.3 commits.

---

## §9 What NOT to do

- **Don't run `git add`, `git commit`, `git push`, `--amend`.** Report when each sub-phase is done; operator commits.
- **Don't ship multiple sub-phases in one session** unless operator explicitly authorizes. Halt-and-report between each.
- **Don't dispatch 2B.1 before Phase 2A.3 has shipped.** 2B.1 imports `app/auth/dependencies.py::require_user` (Phase 2A.2) and `app/auth/claims.py::find_existing_claim` (Phase 2A.3). 2B.2 and 2B.3 don't have this dependency and can dispatch independently if Lane 2A is running slow.
- **Don't write SQLite-only constructs in the migration.** Production runs Postgres; the sandbox + tests run SQLite. **Postgres portability checklist** (absorbed from Phase 2A's brief §9 + Phase 1A hotfix lesson):
  - Use `sa.true()` / `sa.false()` (NOT `sa.text("1")` / `sa.text("0")`) for Boolean `server_default` values. Phase 1 Entity at `app/db/models.py:648` is the precedent.
  - Use `sa.func.now()` (NOT `sa.text("CURRENT_TIMESTAMP")`) for default timestamps where the migration needs a server-side default.
  - Verify any raw SQL inside `op.execute()` works on Postgres, not just SQLite. SQLite is loose about quoting, keyword strictness, NULL-handling in unique constraints, and JSON syntax.
  - The Phase 2A.1 `92ce4899dc08_account_lite_v01.py` migration is the most recent precedent — `op.create_table` with portable `sa.true()` defaults; no raw SQL on the SQLite-compatible path. Mirror that shape for the 2B.1 photos table migration.
- **Don't ship FTS DDL unguarded.** `CREATE EXTENSION pg_trgm`, generated `tsvector` columns, `websearch_to_tsquery`, and `gin_trgm_ops` are Postgres-only. SQLite fails hard on any of these. **All FTS-related DDL in the 2B.2 migration must be inside an `if op.get_bind().dialect.name == "postgresql":` block.** Cite Phase 1A's `passive_deletes=True` SQLite-vs-Postgres precedent — the same principle of "diverge handling by dialect" applies. SQLite tests run the `app/search/sqlite_fallback.py` LIKE-based path; Postgres production runs the real FTS path.
- **Don't break the chat tier 2 voice-battery regression bar.** The synonym-expansion helper `_category_needle_set` at `app/chat/tier2_db_query.py:548` MUST be preserved exactly — its callers move from `ilike`-OR-clause consumers to `tsquery`-OR-clause consumers, but the helper itself ships intact. Voice battery 2026-05-08 tests at `tests/test_tier2_db_query_entity_pivot.py` are the regression bar — if they fail post-swap, the FTS path diverges from the LIKE-chain shape.
- **Don't change the Python-side `open_now` filter.** It runs after SQL fetch because hours are JSON. FTS doesn't change that. The filter stays at `~:946-954`.
- **Don't change the chat-route response shape or Provider profile rendering for anonymous viewers.** This is foundational infra — synonym expansion + ranking are net improvements, but Tier 2 returns the same JSON shape and Tier 3 LLM receives the same candidate-list shape. Existing integration tests are the regression bar.
- **Don't add additional Photo entity_types** beyond `commercial` and `place`. Events + programs are NOT photo-uploadable in V1 per design memo §13.
- **Don't store EXIF metadata.** Strip is mandatory per design memo §6 stage 2 + §7. If strip fails, flag the row rather than upload-with-EXIF — privacy non-negotiable.
- **Don't trust the original filename for the storage key.** UUIDs only per design memo §7. Original filename is kept on the row for owner recall ("did I upload that one?") but never in the URL path.
- **Don't add Cloudinary / Cloudflare Images / AWS Rekognition / pgvector / Meilisearch.** Storage = R2 only; search = Postgres FTS only. Cloudinary etc. defer per design memo §2.4 + §13; Meilisearch is the Option B migration path triggered by quantitative signals per search memo §7.
- **Don't add image moderation in V1.** Manual operator review queue only per design memo §7 + §13. Automated moderation is V1.5.
- **Don't add video uploads / GIF support / HEIC support / signed URLs / cropping UI / multi-format on-the-fly transforms.** Design memo §13 lists every explicit V1 exclusion. None of those ship.
- **Don't change the existing `derive_hero_photo` fallback chain order.** Add owner-Photo tier as Tier 1; existing pinned-URL + Google fallback tiers stay at Tier 2 + Tier 3.
- **Don't add a separate `PhotoVariant` table.** Three String columns + the storage_key prefix are simpler than a child table per design memo §5.1 rationale. V2 may refactor if variants become user-configurable.
- **Don't add a polymorphic `entity_type` column on `photos`.** The FK to `entities.id` + Entity's existing discriminator is the locked shape per master plan amendment. Same as Lane 2A's user_favorites/claims.
- **Don't pre-process photos synchronously in the upload route.** FastAPI `BackgroundTasks` per design memo §4 step 7 + background_job_infrastructure_decision.md §6.4 Option A.
- **Don't introduce circular imports.** `app/photos/routes.py` imports `app/auth/dependencies.py` + `app/auth/claims.py`. `app/photos/processor.py` does NOT import anything from `app/photos/routes.py`. `app/search/fts.py` imports `_category_needle_set` from `app/chat/tier2_db_query.py` — verify this doesn't create a cycle (it shouldn't; the helper is leaf-level).
- **Don't ignore PowerShell `$` interpolation** if the operator commits via PowerShell (dispatch_channels gotcha #8 — single-quote git commit subjects with `$` or sigils).
- **Don't use `&&` in PowerShell command chains** (gotcha #13 — PowerShell 5.1 doesn't support `&&`; use `;` or newline-separated commands).
- **Don't proceed past a baseline mismatch.** Halt and report.

---

## §10 Pragmatic deviations are allowed (within guardrails)

You may deviate from the brief if you discover something on the ground that materially changes the right call. **Report every deviation in the final report.** Examples of acceptable deviations:

- **`before_flush` Session listener safety net for Photo row creation.** Same precedent as Phase 1D + Phase 2A.1 — if test fixtures create `Photo` rows directly without going through the upload route, register a listener that auto-fills `created_at` / `status` default if missing, mirroring `app/db/seed_helpers.py::register_provider_slug_hooks` and the dual-write hooks in `app/db/database.py::_register_orm_listeners`. Recommended if test setup needs it.
- **Folding `run_stuck_photo_sweep` into `_hourly_cleanup_loop` at `app/main.py:246`** — this is the **recommended deviation** (mirrors Phase 2A.1 deviation #5 fold of expired-token cleanup). Same precedent as `run_expired_review_cleanup`. Document in §12 if you do this.
- **Line offsets different than this brief states.** Likely — the brief was authored 2026-05-12 between 2A.2 dispatch and 2A.3. Phase 2A.2/2A.3 may have shifted offsets in `app/main.py`, `app/providers/router.py`, and `app/db/models.py`. Re-grep before edits.
- **Field name adjustment** for the `Photo` model if there's a name collision with existing code. (Unlikely — `Photo` is novel.)
- **Skip on SQLite via pytest marker vs skip via `if dialect == "sqlite"` runtime branch** — either pattern is acceptable. The codebase may already have a `@pytest.mark.requires_postgres` fixture; reuse it if it exists.
- **Adding a `Place.photos` viewonly relationship** when Place model lands in Phase 3 — out of scope for Lane 2B. The `Entity.photos` relationship covers both commercial and place entities transparently.
- **MIME-sniff implementation detail** — the design memo says "declared content-type must match what Pillow actually decodes." Pillow's `Image.open(...).format` returns 'JPEG' | 'PNG' | 'WEBP'. The simplest implementation is: assert `declared_mime in ALLOWED_MIME_TYPES`, then call `Image.open(BytesIO(content)).format.lower()`, then check it matches the declared mime (e.g., declared `image/jpeg` → format `jpeg`). Document if you use a different shape.
- **Pagination cursor shape for `/api/search`** — opaque base64 of `(score, entity_id)` for stable seek-pagination is the cleaner shape than offset; but offset is simpler. Either is fine for V1. Document choice.
- **Search bar visual treatment** — the brief says "match existing visual treatment." If the existing `app/templates/home.html` has a clear search-bar slot already in the design, use it. If you find one of those existing slots that this brief didn't anticipate, you can deviate to fit it without breaking visual rhythm.
- **Pin caption length / hero-set behavior** for V2 — design memo §5.1 doesn't lock caption max length; bound it at `Text` (effectively unlimited) on the schema but UI may want to surface a soft cap (e.g., 300 chars). Defer to V1.5 unless trivial.
- **Boto3 client `region_name='auto'` vs `region_name='wnam'` (Western North America)** — both work for R2. `'auto'` per boto3+R2 convention is the default; if the operator's R2 bucket is region-pinned, deviate. Document.

Unacceptable deviations (these are LOCKED):
- **Choosing storage other than R2.** Image storage memo §3 LOCKED Option B. AWS S3 / Cloudinary / Bunny / Railway-volume are explicitly rejected.
- **Choosing search backend other than Postgres FTS + `pg_trgm`.** Search memo §3 LOCKED Option A. Meilisearch / Algolia / Typesense are deferred.
- **Adding `entity_type` discriminator column to `photos`.** Master plan §4 Phase 2 + Phase 1 ENTITY pivot LOCKED FK-to-entities-only shape.
- **Storing EXIF metadata on uploaded photos.** Design memo §6 stage 2 + §7 LOCKED strip-mandatory.
- **Storing plaintext credentials or raw R2 access keys in the codebase.** Env vars only.
- **Renaming `photos` table.** Name is LOCKED — V2 phases reference it.
- **Adding additional tables beyond `photos` in 2B.1 or beyond the entities-column-add in 2B.2.**
- **Skipping or merging sub-phases without explicit operator authorization.**
- **Breaking the chat tier 2 voice-battery regression** by changing `_category_needle_set` or by FTS-swap producing different row sets than the LIKE chain for the seeded test data.
- **Shipping FTS DDL unguarded against SQLite.** Migration must run cleanly on both backends.
- **Synchronous image processing in the upload route.** BackgroundTasks per memo §4 step 7.
- **Hard-coding `R2_PUBLIC_URL_BASE` host.** Env-var driven so Path A↔Path B swap is config-only.

---

## §11 Risk register for this lane

| # | Risk | Mitigation |
|---|---|---|
| 1 | Operator's R2 setup uses different env var names than the brief specifies | §0 step 8 halts on mismatch. The names (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL_BASE`) are the canonical recommendation; operator can deviate but the brief should be updated to match. |
| 2 | Operator chose Path B (custom domain) but DNS hasn't propagated | `R2_PUBLIC_URL_BASE` env var is read at upload-finalize time; if DNS isn't live yet, the URL works the moment DNS does. No code change needed. Photos uploaded pre-DNS will work once DNS lands (CDN cache lifecycle is per-URL, not per-bucket). |
| 3 | SQLite vs Postgres divergence on FTS DDL | Migration gated on `op.get_bind().dialect.name == "postgresql"`. SQLite skips FTS-specific DDL entirely; application-layer FTS query builder branches on dialect at query-build time. Phase 1A `passive_deletes=True` precedent for SQLite-vs-Postgres divergence handling. |
| 4 | Phase 2A.3 hasn't shipped when 2B.1 is dispatched | §0 step 8 halts on missing `app/auth/claims.py::find_existing_claim`. 2B.2 + 2B.3 don't have this dependency — operator can dispatch those independently if Lane 2A is running slow. |
| 5 | Pillow EXIF strip silently fails (some malformed images keep partial EXIF data) | Stage 2 returns explicit ProcessingError on strip failure; row flagged `exif_strip_failed`. Test with a battery of EXIF-rich fixtures from camera vendors. |
| 6 | Polyglot upload — JPEG that's actually HTML | MIME-sniff check at Stage 1 (declared MIME must match Pillow's decoded format). Test with a crafted polyglot fixture. |
| 7 | R2 transient network failure during upload-variant step | Row left in `status='uploading'`; daily sweep flips to `flagged` after 24h. Operator can manually retry by re-uploading via UI. |
| 8 | FTS swap changes ranking for chat Tier 2 → Tier 3 LLM gets different candidates than before → answer quality regresses | Voice battery tests are the regression bar; if they pass with the SQLite fallback (which mirrors LIKE chain), and the Postgres FTS path returns the same row SET (different order is acceptable since LIKE chain had no deterministic order either), the swap is safe. Document any row-set divergence in §12. |
| 9 | `tsquery` parser errors on user-supplied input (special chars in `filters.entity_name`) | `_build_tsquery_string` must sanitize: split on whitespace, drop non-word chars, escape quotes. Tests cover adversarial inputs (`'plumber\'s OR 1=1'`, etc.) — the tsquery should reject + fall back to no-text-query branch. |
| 10 | `entities.search_vector` generated column adds INSERT/UPDATE overhead on `entities` writes | Marginal — Postgres FTS generated columns are well-optimized. At V1 scale (writes are admin-driven, low-frequency) the overhead is unmeasurable. Worth a sanity check post-deploy. |
| 11 | Photos table grows large; per-entity-hash dedup query slow without the composite index | Composite index `ix_photos_entity_hash_status` per §4.1 covers the common dedup-lookup path. Cardinality at V1 is bounded (a few thousand photos); index is cheap. |
| 12 | Search bar lands but Tier 2 LIKE→FTS swap regresses chat | 2B.2 ships in isolation BEFORE 2B.3 — search bar only lights up post-2B.3. Tier 2 swap in 2B.2 ships green-tests-first; chat-route integration regressions caught at 2B.2 commit. |
| 13 | Cursor over-scopes by attempting all three sub-phases in one session | Halt-and-report etiquette in §3 is the safety valve. Better to ship 2B.1 cleanly + re-dispatch than push past a broken state. |
| 14 | Postgres migration verified only on SQLite (Cursor doesn't have Postgres locally) | Document in §12 report that Postgres cycle wasn't locally verified. Operator validates against Railway staging Postgres before merge. |
| 15 | Pillow version pin conflicts with existing requirements.txt | Verify before pinning. Latest stable (Pillow 10+) is the recommended pin. boto3 latest stable. |

---

## §12 Final report format (per sub-phase)

After each sub-phase, paste back a single message:

1. **Sub-phase identifier** — 2B.1 / 2B.2 / 2B.3.
2. **§0 baseline values** (top-5 SHAs, pytest count, alembic head, alembic current). Confirm R2 env vars present + Phase 2A.3 shipped (for 2B.1) / 2A.x state (for 2B.2 + 2B.3).
3. **Files created** (paths + line counts).
4. **Files modified** (paths + net line counts).
5. **Migration revision id chosen** (2B.1 + 2B.2 only) + `down_revision`.
6. **Tests added** (count + brief description of each).
7. **Final pytest count** (expected to be baseline + tests added).
8. **`python -m alembic upgrade head` result** against fresh dev DB (success/failure + any output). For 2B.2 specifically: report SQLite cycle result; flag if Postgres cycle was not locally verified.
9. **`python -m alembic downgrade -1 && python -m alembic upgrade head` cycle** (2B.1 + 2B.2 only — verify the migration is reversible).
10. **Ruff status** (clean / autofixes applied / remaining issues).
11. **Manual smoke result** (2B.1: upload a real JPEG end-to-end via curl with R2 env set; 2B.2: query a known seeded provider via tier 2 path with FTS active; 2B.3: search bar on home page submits + renders results).
12. **Pragmatic deviations** — anything you adapted from this brief, with rationale. Be transparent; reasonable deviations are fine.
13. **Anything that surprised you** or that the operator should know before they commit. Include any baseline mismatches or env-var-name mismatches with the brief's canonical names. Include any chat tier 2 row-set differences post-FTS-swap.
14. **Confirmation you did NOT run `git add` / `git commit` / `git push` / `--amend`.**
15. **Next sub-phase preview** — 2B.1: "Ready for 2B.2 re-dispatch — photos schema in, R2 + Pillow pipeline live, upload route functional, no search index yet." 2B.2: "Ready for 2B.3 — FTS migration applied (Postgres) + SQLite fallback live; chat tier 2 swapped to FTS; no search bar UI yet." 2B.3: "Phase 2B complete; master plan §4 Phase 2 Lane 2B ready for Shipped: line; if Lane 2A also complete, Phase 2 is shipped end-to-end."

---

Ready. Start at §0. Halt at the first sub-phase boundary.

# Image Storage — Design Memo

> **Status:** design only; no implementation, no migration. Output of the architecture-audit-driven design pass on 2026-05-14.
> **Source gap:** Gap #9 in `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3.9.
> **Audience:** Cowork primary + Casey; future implementation-lane author (Cursor / CC).
> **Companion docs:** `docs/maintainability/place_model_design.md` (Place rows also carry photos — voice + structure anchor), `docs/maintainability/account_lite_v01_design.md` (auth gate — uploads happen post-login + via the same Claim model), `docs/maintainability/background_job_infrastructure_decision.md` (Option A FastAPI `BackgroundTasks` is the queue this lane plugs into), `outputs/chatgpt_response_home_services_category_page_spec.md` §3 (16:9 card thumbnail priority), `outputs/chatgpt_response_eat_and_drink_strategic_review.md` §3.5 (Opus's "food / patio photo matters" lock for Eat & Drink).

---

## §1 Why image storage exists (problem statement)

The current codebase has **no owner-uploaded image storage**. Two surfaces in `app/db/models.py` carry external URLs and neither is durable, owner-controlled, or category-aware:

- `Provider.google_photo_refs: list[str] | None` (`app/db/models.py:83`) — URLs returned by the Google Places API. We don't own these. Google rotates / expires / blocks hotlinking. When a sponsor pays $79/mo for Verified Presence and the Google photo of their patio is a blurry 2018 phone-shot taken by a random reviewer, we have no path to replace it.
- `Provider.attributes.hero_pin_photo_url` — a single arbitrary URL surfaced by the hero-photo deriver at `app/providers/queries.py:80-91`. The deriver prefers `hero_pin_photo_url` over `google_photo_refs[0]`, but there's no upload mechanism behind it — it's a string that an operator types into the admin form when they happen to find a better photo elsewhere on the web. Same hotlink-fragility problem; same "owner can't replace it" problem.

`grep -r "image\|upload\|photo" app/` confirms what's missing: no `app/images/`, no `app/uploads/`, no Pillow import anywhere on tree (`PIL` not in `requirements.txt`), no boto3 / S3 client, no Cloudflare R2 wiring, no multipart upload route, no `Photo` model, no thumbnail generation. The full set of photo-related symbols today is: the two storage fields above, the hero/gallery derivers at `app/providers/queries.py:80` and `:94`, the template render of `vm.hero_photo_url` at `app/templates/provider_profile.html:198-199`, and JSON keys in `app/home/mock_data.py` for the Home page mockup. That is the entirety of the image surface.

**Why the gap matters under the full vision.** Three pressure points compound:

1. **Owner-controlled photos are the Verified Presence value prop.** Pivot §7 sells Verified Presence at $79/mo. Among the locked deliverables: "owner-uploaded hero photo + gallery." A sponsor who can't upload their own photos is paying for nothing visible — they'd see the same Google photo any free-tier listing shows.
2. **Eat & Drink cards are photo-first per Opus.** `outputs/chatgpt_response_eat_and_drink_strategic_review.md` §3.5 emphasizes "Provider cards should become more visual than Home Services / one photo thumbnail matters / food photo matters / patio photo matters." Home Services tolerates a generic streetfront thumbnail; restaurants do not. The discovery surface for the highest-frequency-use category requires owner-uploaded food + patio photos.
3. **Place pages need photos too.** Per `docs/maintainability/place_model_design.md` §4.1, the new `Place` model carries both `photo_refs` and `google_photo_refs`. Parks, dog parks, scenic spots, ramps — Google often has no photos at all for these, and the ones it has are usually wrong (a photo of someone's truck in the parking lot, not the trail itself). The operator field-trip photo capture workflow (manual recovery campaign) needs a place to put those photos.

Beyond V1, image storage is also foundational for: future sponsor logo upload (Category Visibility branding), Eat & Drink category cards with food thumbnails (Opus #4 emphasized), operator field-trip captures during the Place ingest sprint, and any V2 review-submission UI that allows user-attached photos.

This memo locks the storage backend, the upload flow, the `Photo` schema, and the processing pipeline. Reading the previous lane's memo decisions (Place + account-lite + background-jobs) is a prerequisite — image storage sits downstream of all three.

---

## §2 Five storage backend options

The comparison is across: monthly cost at three scale tiers, code complexity, CDN/edge story, S3-API compatibility (which determines whether boto3 plugs in trivially), Railway integration story, and vendor stability.

**Scale tiers used below.**

- **V1 launch (~100 photos).** Verified Presence soft-launch with 5-15 sponsors × ~10 photos each. Plus operator field-trip photos for ~30 Place rows. ~500 MB total counting all variants (thumb / medium / hero / WebP / JPEG fallback).
- **Category-complete (~5,000 photos).** All 12 categories' top entities photo-covered. ~25 GB.
- **Year 2 scale (~50,000 photos).** Dense coverage + user-attached photos on reviews (V2). ~250 GB.

### §2.1 Option A — Railway persistent volume

Railway supports mounting a persistent volume to a service; photos are written to a local filesystem path, served by FastAPI's `StaticFiles` mount.

**Pros.**
- Simplest possible. No new vendor, no new SDK, no credentials beyond the existing Railway deploy.
- Same deploy lifecycle as the app. No DNS/CDN config to learn.
- Filesystem semantics — easiest to debug locally (just `ls` the volume).

**Cons.**
- Tied to one Railway region / one service. No multi-region replication; if Railway loses the volume, the photos are gone.
- No CDN edge. Every photo request hits the Python app, saturating the same workers the audit §5.6 already calls out as a static-asset bottleneck.
- Volume backups on Railway are manual + region-locked. Backup story is fragile.
- Egress through Railway's bandwidth, billed on the app's egress meter.
- Cost scales linearly with the same dollars-per-GB-storage as the app — uncompetitive with object storage.

**Monthly cost estimates.**
- V1 launch: $0.25-1 (volume + bandwidth essentially negligible at 500 MB).
- Category-complete: $5-15 (25 GB + maybe 100 GB/mo egress).
- Year 2 scale: $50-200 depending on egress (250 GB stored, possibly 1 TB+/mo egress).

**Code complexity.** Lowest. ~50 lines: a save-to-path helper + `StaticFiles` mount. Zero new dependencies beyond Pillow for processing.

**Railway integration story.** Native. Single Railway dashboard knob to attach a volume.

**Verdict.** Cheapest at V1 but the wrong long-term answer. The CDN-edge gap and backup fragility make this a V0 prototype, not a V1 ship. If we ship on Railway volumes, we re-do this work the moment Eat & Drink lands with any real photo traffic.

### §2.2 Option B — Cloudflare R2

S3-compatible object storage with **zero egress fees**. Cloudflare's CDN edge is built-in (publicly-served R2 buckets are reachable at `<bucket>.r2.dev` or a custom domain through Cloudflare's edge for free). Cloudflare Images is a separate product layered on top for on-the-fly transforms; we can ship without it on V1 and add later.

**Pros.**
- Cheapest at scale by a wide margin — no egress is the headline difference vs S3.
- S3-compatible API works with boto3 verbatim (`endpoint_url` swap + R2-issued access/secret keys).
- Cloudflare CDN edge is automatic when bucket is bound to a public domain — no separate CloudFront-like config dance.
- Active development at Cloudflare; the product has shipped features steadily since GA.
- Free tier: 10 GB storage + 1M Class A ops/month + 10M Class B ops/month + unlimited egress. V1 fits entirely inside free tier.

**Cons.**
- Another vendor in the stack (one more dashboard, one more set of credentials).
- Learning curve for Cloudflare-specific concepts (R2 access policies, bucket-binding, custom-domain attachment via Cloudflare DNS or via a worker route).
- Cloudflare's "smaller-and-newer" reputation vs AWS S3 — though R2 has been GA since 2022 and shipped no major regression in that window.
- No native image transform without adding Cloudflare Images (extra cost) or running our own Pillow pipeline (which we'd do anyway for variants).

**Monthly cost estimates.**
- V1 launch: $0 (fully in free tier).
- Category-complete: $0.40-1 (25 GB stored × $0.015/GB = $0.38; ops well under free tier; egress free).
- Year 2 scale: $4-8 (250 GB × $0.015 = $3.75; ops scaling depends on traffic but typically <$5).

**Code complexity.** Low-medium. ~150 lines: boto3 client pinned to R2 endpoint, upload helper, key-naming convention, public-URL builder. Pillow processing is separate and the same regardless of backend.

**Railway integration story.** Clean. Same deploy stack; R2 credentials live in Railway env vars; nothing platform-specific.

**Verdict.** The strong front-runner. Cheapest at every scale tier past V1; CDN edge included; S3-compat means no vendor lock-in (a future migration to S3 is a one-line `endpoint_url` change + bucket sync).

### §2.3 Option C — AWS S3 + CloudFront

Industry standard. S3 for storage; CloudFront in front for CDN edge; standard egress fees apply.

**Pros.**
- Maximally mature ecosystem; every Python library, every doc, every Stack Overflow answer assumes S3.
- AWS account features (IAM, KMS, VPC endpoints) are best-in-class if Casey needs them eventually.
- Multi-region replication is one config setting.
- Survives any scale we'd plausibly hit.

**Cons.**
- **Egress fees add up fast.** $0.09/GB out of CloudFront US tier. At Year 2 scale with 1 TB/mo egress = $90/mo just for serving photos.
- AWS account management overhead — IAM roles, bucket policies, OAC for CloudFront, KMS key rotation, billing alarms. The smallest setup is still more configuration than R2.
- CloudFront cache invalidation is metered (first 1,000/month free; cheap but a footgun).
- Operator already has zero AWS account today. Spinning one up is a half-day operator cost + a Day 1 billing alarm + ongoing surface.

**Monthly cost estimates.**
- V1 launch: $1-3 (S3 free tier covers 5 GB; CloudFront free tier covers first 1 TB/mo egress for 12 months; outside the year-1 freebies it's ~$1-3).
- Category-complete: $10-25 (25 GB × $0.023 + 100 GB egress × $0.09 = ~$9.60; plus request costs).
- Year 2 scale: $80-150 (250 GB × $0.023 + 1 TB egress × $0.09 = ~$96; plus requests).

**Code complexity.** Medium. ~200 lines: boto3 + CloudFront signed-URL helper (not needed for V1 public-photos, but the option is wired) + lifecycle policy for old variants. Higher operational complexity than R2 from the IAM dance.

**Railway integration story.** Independent of Railway. Standard env-var-driven AWS SDK.

**Verdict.** The "default" answer. Not wrong; just 10-30x more expensive than R2 at Year 2 scale for no advantage we'd use. Reserved for a future migration only if R2 becomes untenable.

### §2.4 Option D — Cloudinary

Managed image-CDN + transformation API. Photos uploaded via their SDK; transforms (resize, format conversion, crop, quality) happen on-the-fly via URL parameters.

**Pros.**
- **Zero-ops for image transforms.** Need a 256x256 thumbnail? Just request `/upload/w_256,h_256,c_fill/`. We skip the Pillow pipeline entirely.
- Built-in CDN; built-in WebP / AVIF auto-format negotiation; built-in EXIF strip.
- Excellent free tier: 25 GB storage + 25 credits/month (credits cover transforms + bandwidth combined).
- Quick to ship — the SDK does the upload + processing in one call.

**Cons.**
- **Pricing scales aggressively past free tier.** First paid tier ("Plus") is $99/mo for 225 credits. Credits get consumed by both bandwidth AND transforms — at 5,000 photos with moderate traffic, credits exhaust quickly.
- **Vendor lock-in for transforms.** Switching off Cloudinary means losing the URL-parameter transform shape; every reference to `/upload/w_256/` becomes broken. Re-doing the pipeline elsewhere costs more than ever doing R2 + Pillow ourselves.
- Less control over the storage layer (their bucket, their keys, their policies).
- Doesn't S3-compat the same way the others do.

**Monthly cost estimates.**
- V1 launch: $0 (free tier).
- Category-complete: $0-99 (depends on traffic; one viral category page can blow through credits and force the $99/mo tier in a single month).
- Year 2 scale: $99-249/mo (likely the $249/mo "Advanced" tier with 600 credits).

**Code complexity.** Lowest of all options for end-to-end. ~80 lines via the official SDK. Skips Pillow entirely.

**Railway integration story.** Trivial — pure SDK + env var.

**Verdict.** Tempting for V1 (free + fastest to ship) but the vendor lock-in is the long-tail problem. The transform URLs become load-bearing; the migration cost out of Cloudinary at Year 2 scale exceeds the cost of running Pillow ourselves over R2 from day one. Not recommended.

### §2.5 Option E — Bunny CDN + Bunny Storage

Cheap CDN + S3-compatible storage from a smaller European vendor.

**Pros.**
- Very low storage + bandwidth pricing (~$0.01/GB storage; $0.005-0.02/GB egress depending on region).
- S3-compatible API (boto3 works).
- Reasonable CDN speed; ~50ms p50 from US edge.
- Per-region pricing tiers (US/EU/AsiaPac) are transparent.

**Cons.**
- Smaller ecosystem than R2 or S3. Fewer integrations, fewer Stack Overflow answers, less battle-tested at scale.
- Less mature dashboard / less mature account-management features.
- Egress isn't free (unlike R2) — at Year 2 scale the egress line item matters.
- Vendor-stability risk higher than R2 (Cloudflare is a public, well-capitalized company; Bunny is privately held and smaller).

**Monthly cost estimates.**
- V1 launch: $0.50-2 (negligible storage; small egress).
- Category-complete: $2-8 (25 GB storage + ~100 GB egress).
- Year 2 scale: $25-50 (250 GB storage + 1 TB egress × $0.02 = ~$22; plus storage ~$2.50).

**Code complexity.** Low. Same shape as R2 (boto3 with custom endpoint).

**Railway integration story.** Clean — env-var driven.

**Verdict.** Cheaper than S3, comparable or slightly higher than R2 at scale (because egress isn't free). The ecosystem maturity gap pushes this below R2 in the ranking, but it remains a fallback if R2 ever becomes untenable.

### §2.6 Cross-option grid

| Option | V1 cost | Cat-complete cost | Yr2 cost | CDN edge | S3-compat | Vendor lock-in | Code lines |
|---|---|---|---|---|---|---|---|
| A — Railway volume | <$1 | $5-15 | $50-200 | none | n/a | low (just files) | ~50 |
| B — Cloudflare R2 | $0 | $0.40-1 | $4-8 | built-in | yes | low | ~150 |
| C — AWS S3 + CF | $1-3 | $10-25 | $80-150 | CloudFront | yes | low | ~200 |
| D — Cloudinary | $0 | $0-99 | $99-249 | built-in | no | **high** | ~80 |
| E — Bunny | $0.50-2 | $2-8 | $25-50 | built-in | yes | medium | ~150 |

---

## §3 Recommendation — Option B (Cloudflare R2)

Ship image storage on Cloudflare R2 with a Pillow-based processing pipeline running through the FastAPI `BackgroundTasks` infrastructure decided in the background-jobs memo (`docs/maintainability/background_job_infrastructure_decision.md` §6.4).

**Why Option B wins.**

1. **Cost at scale.** R2 is the cheapest option at category-complete and Year 2 scale by 10-30x vs S3/CloudFront, and is competitive with Bunny while being a stabler vendor. Zero egress fees is the structural advantage — at Year 2 the dollar gap vs S3 is ~$90/mo for no functional difference.
2. **Free tier covers V1.** 10 GB storage + ample ops on the free tier means V1 launch costs $0. No billing footgun on day one.
3. **S3-compatible escape hatch.** If R2 ever becomes untenable (Cloudflare price hike, performance regression, business reasons), migration to S3 or Bunny is a one-line `endpoint_url` change + bucket sync. Vendor lock-in is structurally low — the same property that makes Cloudinary risky makes R2 safe.
4. **Pillow pipeline is portable.** Variants (thumb / medium / hero), EXIF strip, WebP conversion, hash-based dedup all run in-app and are backend-agnostic. We do the same Pillow work regardless of where the bytes land; choosing R2 doesn't lock us into anything we'd want to undo later.
5. **CDN edge built-in.** Public R2 buckets bound to a Cloudflare-managed custom domain (`cdn.havasuchat.com`) get edge caching for free — no separate CloudFront-style config, no signed-URL infrastructure, no edge worker required at V1.
6. **Active vendor.** Cloudflare has shipped R2 features steadily since GA; the product is not in maintenance mode. Same cannot be confidently said about Bunny.

**The case for not picking Option A (Railway volume):** the audit §5.6 already calls out static-asset serving through FastAPI as a saturation risk at 1000-concurrent-user scale. Volumes double down on that risk and add a backup-fragility tax. Ship a prototype here only if R2 setup blocks the lane for more than a day — and migrate immediately after.

**The case for not picking Option C (AWS S3):** S3 is the right answer if we have any pre-existing AWS commitment or any operator familiarity with AWS billing. We have neither. R2 gets us the same S3 API with no egress and no IAM dance.

**The case for not picking Option D (Cloudinary):** the transform URL shape becomes load-bearing across templates and emails; migration cost is high; Year 2 pricing is uncomfortable. We can always add Cloudinary later as a layered transform service on top of R2 if dynamic image transforms become valuable, but we shouldn't make storage depend on it.

**The case for not picking Option E (Bunny):** comparable on cost; loses to R2 on ecosystem + vendor stability. Solid fallback, not a leader.

---

## §4 Upload flow (end-to-end)

The numbered sequence below is the happy-path owner photo upload. Assumes the owner has completed the account-lite login flow (`docs/maintainability/account_lite_v01_design.md` §5) and holds a `verified` Claim row for the entity they're editing.

1. **Owner logged in via account-lite, viewing their Provider profile.** Route `/provider/<slug>/edit` is gated on `current_user.role == 'admin'` OR a `verified` Claim row matching `(user_id, 'provider', provider_id)` per `account_lite_v01_design.md` §7.
2. **Clicks "Upload photo".** UI renders a `<input type="file" accept="image/jpeg,image/png,image/webp" multiple>` plus a drag-drop target. Multi-file selection is supported; each file uploads independently (sequential or parallel — implementation decides).
3. **Browser POSTs multipart form-data to `/api/providers/<id>/photos`.** Body shape: one or more `file` parts + optional `caption` per file. Cookie-auth via the `hava_session` cookie established in account-lite §6.
4. **Server validates the request.** In order: (a) `current_user` exists, (b) `current_user` has admin role OR `verified` Claim on the entity, (c) MIME type in whitelist (`image/jpeg`, `image/png`, `image/webp`; **no SVG**, **no HEIC** in V1), (d) `Content-Length` ≤ 10 MB, (e) per-merchant + per-entity rate-limit caps (§7) not exceeded.
5. **Server reads upload into memory, generates UUID-based key.** Filename is randomized — never trust the original filename for the storage path. Original filename is kept on the row for owner recall ("did I upload that one?") but not in the URL. Storage key shape: `photos/<entity_type>/<entity_id>/<photo_id>/original.<ext>`.
6. **Server writes a `Photo` row immediately in `status='uploading'`.** This is the synchronous DB write that lets the response return without waiting on Pillow + R2 — the row is the durable handle.
7. **Server kicks off async image processing via FastAPI `BackgroundTasks`.** Per `background_job_infrastructure_decision.md` §6.4 (Option A — V1 inline). Task does, in order:
   - Decode the bytes with Pillow; reject if decode fails or if MIME-sniff disagrees with the declared MIME (defense against polyglot uploads).
   - Strip EXIF metadata (privacy — location leak prevention) and any embedded color profile beyond sRGB.
   - Compute SHA-256 of the decoded pixel bytes (post-EXIF-strip). If a `Photo` with the same hash already exists for this entity, mark the new row as a duplicate and short-circuit. (Dedup across entities is V2; one operator uploading the same logo to two listings is rare and not worth solving on day one.)
   - Generate variants: `thumbnail` (256×256, fill-crop), `medium` (512×512, fill-crop), `hero` (1280×720, 16:9 fill-crop — matches the home services card spec at `outputs/chatgpt_response_home_services_category_page_spec.md` §3 and the Eat & Drink visual emphasis from Opus).
   - For each variant: write WebP at quality 82 (~30% smaller than equivalent JPEG) + JPEG at quality 85 as fallback for legacy browsers / clients that prefer JPEG.
   - Upload all variants to R2 with content-type headers + `Cache-Control: public, max-age=31536000, immutable` (filenames include the photo UUID so immutability is safe).
   - Update the `Photo` row: set `width_px`, `height_px`, `file_size_bytes`, `thumbnail_url`, `medium_url`, `hero_url`, transition `status` to `live`.
8. **Server returns 201 immediately** with the `Photo` row in `status='uploading'`. UI renders a pending state (greyed-out tile with a spinner). When the row transitions to `live`, the next page refresh or polled API call surfaces the URLs.
9. **UI refresh mechanism.** V1: simple — owner refreshes the page after a few seconds; the new photo is live. V2 optional: poll `GET /api/photos/<id>` every 2s for ~30s until `status='live'`. Worth the small polish if V1 owners complain.

**Failure handling.** If the BackgroundTask raises:
- For Pillow decode failure: mark the row `status='flagged'` with `processing_error='decode_failed'`. UI surfaces "Couldn't process this image. Try a different file." next page load.
- For R2 upload failure (transient network): the retry wrapper at `app/core/background.py` (per background-jobs memo §6.2) gives 2 retries; on exhaustion, leave the row in `status='uploading'` and surface a "Processing — try refreshing" message. A daily cleanup pass (sibling to `_hourly_cleanup_loop` at `app/main.py:246`) sweeps rows stuck in `status='uploading'` for >24h and flips them to `status='flagged'`.
- The synchronous response is already returned by step 8 — the user sees a successful upload regardless. Recovery is async.

---

## §5 Schema additions

### §5.1 `Photo` model

```python
class Photo(Base):
    """Owner-uploaded photo for a Provider or Place.

    Polymorphic entity reference via (entity_type, entity_id). Mirrors the
    UserFavorite + Claim pattern in account_lite_v01_design.md §4 — same
    cross-entity validator helper, same uniqueness shape, no DB-level FK
    because the target tables differ.
    """

    __tablename__ = "photos"
    __table_args__ = (
        Index("ix_photos_entity", "entity_type", "entity_id"),
        Index("ix_photos_uploaded_by_user_id", "uploaded_by_user_id"),
        Index("ix_photos_status", "status"),
        Index("ix_photos_hash", "image_hash"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))

    # Polymorphic entity reference — same shape as UserFavorite + Claim.
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # CHECK ck_photos_entity_type: "provider" | "place".
    entity_id: Mapped[str] = mapped_column(String, nullable=False)

    uploaded_by_user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False
    )

    # Upload metadata
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # CHECK ck_photos_mime_type: "image/jpeg" | "image/png" | "image/webp".
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 of post-EXIF-strip pixel bytes; used for per-entity dedup.

    # Storage references
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    # R2 object key prefix, e.g. "photos/provider/<entity_id>/<photo_id>/".
    # All variants live under this prefix; the URL columns below are the
    # public CDN URLs for the specific variants.

    cdn_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Canonical public URL for the "medium" variant — used when no specific
    # variant is requested (e.g., simple <img src=...>).
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    medium_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    hero_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Owner-facing fields
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_hero: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Exactly-one-hero-per-entity is enforced at the application layer (the
    # set-hero handler clears is_hero on siblings inside one transaction).
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="uploading")
    # CHECK ck_photos_status: "uploading" | "processing" | "live" |
    # "flagged" | "deleted".
    processing_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Free-text-but-bounded reason when status='flagged'. Allowed values
    # operator-curated: "decode_failed" | "too_small" | "unsafe_mime" |
    # "moderation_rejected" | "user_deleted" | "exif_strip_failed".

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    uploader: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by_user_id])
```

**Why polymorphic via `(entity_type, entity_id)` rather than two FK columns.** Same reasoning as `UserFavorite` and `Claim` in `account_lite_v01_design.md` §4.4 / §4.5: the operator queries "all photos for this entity" with one indexed scan rather than two. The application-layer validator confirms `entity_id` actually exists in the relevant table on insert; same helper as the favorites/claims path.

**Why not a separate `PhotoVariant` table for the three URLs.** Considered. Rejected because (a) all three variants are produced atomically — there's never a state where thumbnail exists but medium doesn't, (b) the variant set is fixed at three (not user-defined), (c) joining a child table on every Provider profile render to fetch three URLs is wasteful when three String columns do the job. If V2 adds owner-configurable variant sizes, refactor at that point.

### §5.2 Provider / Place relationship

```python
# On Provider:
photos: Mapped[list["Photo"]] = relationship(
    "Photo",
    primaryjoin="and_(Photo.entity_type == 'provider', "
                "foreign(Photo.entity_id) == Provider.id, "
                "Photo.status == 'live')",
    viewonly=True,
    order_by="Photo.display_order",
)

# On Place (per place_model_design.md §4.1):
photos: Mapped[list["Photo"]] = relationship(
    "Photo",
    primaryjoin="and_(Photo.entity_type == 'place', "
                "foreign(Photo.entity_id) == Place.id, "
                "Photo.status == 'live')",
    viewonly=True,
    order_by="Photo.display_order",
)
```

`viewonly=True` because the relationship spans tables without a DB-level FK; SQLAlchemy mustn't try to cascade. `status='live'` filter is baked in so the relationship returns only display-ready rows — `flagged` / `deleted` / `uploading` are invisible to the view layer.

**`derive_hero_photo` becomes three-tier.** The current function at `app/providers/queries.py:80-91` extends from two tiers to three:

```python
def derive_hero_photo(provider: Provider) -> Optional[str]:
    # New: owner-uploaded photo flagged is_hero, status='live'.
    hero_row = next(
        (p for p in provider.photos if p.is_hero and p.status == "live"),
        None,
    )
    if hero_row and hero_row.hero_url:
        return hero_row.hero_url
    # Fallback 1: legacy attributes.hero_pin_photo_url (operator-pinned URL).
    attrs = provider.attributes or {}
    pinned = attrs.get("hero_pin_photo_url")
    if pinned:
        return pinned
    # Fallback 2: first Google photo.
    photos = provider.google_photo_refs or []
    if photos:
        return photos[0]
    return None
```

`derive_gallery` similarly extends — owner-uploaded `status='live'` photos in `display_order`, then Google photos, with the hero excluded. Place pages get the same treatment via a sibling `app/places/queries.py` module when that lane lands.

---

## §6 Image processing pipeline

Pillow-based, runs inside the `BackgroundTask` triggered by step 7 of §4. Single function in a new `app/images/processing.py` module with the following stages applied in order. Each stage is a pure function for testability; failures at any stage flip the row to `status='flagged'` with the appropriate `processing_error`.

**Stage 1 — Decode + sanity check.** `Pillow.Image.open(io.BytesIO(bytes))`. On `UnidentifiedImageError`, flag with `decode_failed`. Check dimensions: reject `<200×200` as `too_small` (the source can't produce a usable thumbnail at all). Check pixel statistics — reject all-black / all-white images via a quick `Image.getextrema()` check that flags `processing_error='decode_failed'` (covers blank uploads).

**Stage 2 — EXIF + color profile strip.** Drop the EXIF segment via `Image.info.pop('exif', None)` and re-save without it. Convert to sRGB if the embedded profile says otherwise. EXIF strip is **mandatory** — never write photos to R2 with EXIF intact. If the strip somehow fails, flag with `exif_strip_failed` rather than upload-with-EXIF.

**Stage 3 — Hash + dedup check.** Compute SHA-256 of the post-EXIF-strip pixel bytes. Look up `SELECT id FROM photos WHERE entity_type = ? AND entity_id = ? AND image_hash = ? AND status = 'live'`; if a match exists, mark the new row `status='flagged'` with `processing_error='duplicate'` and short-circuit. (Optional V2: dedup across entities for the same uploader.)

**Stage 4 — Variant generation.** Three target sizes, each with WebP + JPEG fallback:

| Variant | Dimensions | Fit mode | Quality | Use case |
|---|---|---|---|---|
| `thumbnail` | 256×256 | center-crop fill | WebP q=82, JPEG q=85 | Card thumbnails on category index pages |
| `medium` | 512×512 | center-crop fill | WebP q=82, JPEG q=85 | Gallery grid + chat-renderer cards |
| `hero` | 1280×720 | center-crop fill (16:9) | WebP q=82, JPEG q=85 | Provider profile hero + Eat & Drink top-of-card hero |

Per the home services card spec (`outputs/chatgpt_response_home_services_category_page_spec.md` §3) the card thumbnail is 16:9 — the `hero` variant is the source for that surface; the smaller `thumbnail` (1:1 square) covers density-tight surfaces like search-result rows and the Home page mockup tiles.

Original is kept (uploaded as-is post-EXIF-strip) for V2 reprocessing (e.g., if we later want to add a 4:3 portrait variant). Not served publicly — the original key has no CDN binding.

**Stage 5 — Upload to R2.** Six bytes uploads per photo (thumbnail.webp, thumbnail.jpg, medium.webp, medium.jpg, hero.webp, hero.jpg) + the original (kept private). All variant uploads carry `Cache-Control: public, max-age=31536000, immutable` and `Content-Type` per format. R2 public URLs are constructed deterministically from `storage_key` + variant suffix; populated into the `Photo` row's variant URL columns.

**Stage 6 — Row finalize.** Single `UPDATE photos SET status='live', width_px=..., height_px=..., file_size_bytes=..., image_hash=..., thumbnail_url=..., medium_url=..., hero_url=..., cdn_url=...` inside one transaction.

**Failure-mode summary.**
- **Invalid image (Pillow can't decode):** flag `decode_failed`, reject. UI surfaces error next refresh.
- **Too small (<200×200):** flag `too_small`, reject. UI surfaces "minimum size is 200×200" hint.
- **Too large (decoded dimensions like 8000×6000):** accept; downscale during variant generation. Original is kept; serving variants are bounded.
- **EXIF strip failure:** flag `exif_strip_failed`. Never serve a photo with EXIF — privacy is non-negotiable.
- **R2 upload failure:** retry 2x via the retry wrapper from background-jobs memo §6.2; on exhaustion leave row in `status='uploading'` for the daily sweep.
- **Duplicate hash for the same entity:** flag `duplicate`; don't double-store.

---

## §7 Security model

- **Auth required.** Upload route is gated on a valid `hava_session` cookie per account-lite §6. Anonymous uploads are 401.
- **Claim ownership required.** Beyond auth, the uploader must hold a `verified` Claim on the entity (or have `role='admin'`). Validator runs inside the route before reading the multipart body.
- **MIME type whitelist.** Accept exactly `image/jpeg`, `image/png`, `image/webp`. **No SVG** (XSS surface via embedded scripts). **No HEIC** in V1 (Pillow heif plugin is an extra dependency and most HEIC sources can re-export as JPEG — defer). **No GIF** in V1 (animated images out of scope per §13).
- **MIME-sniff defense.** The declared `Content-Type` must match what Pillow actually decodes. A `.jpg` that's actually a polyglot HTML file gets flagged `unsafe_mime`. (Polyglot uploads are rare but real attack vectors against image processing pipelines.)
- **File size limit.** 10 MB per upload. Enforced at the `Content-Length` check (cheap reject) AND at the body-read step (defense against missing or spoofed Content-Length headers).
- **EXIF strip mandatory.** Location data leaks via EXIF are common; the strip is non-optional per §6 Stage 2.
- **Public storage URLs.** All `live` photos are publicly addressable via CDN URL with no signed-URL requirement. They're meant to be displayed publicly; signing buys no protection. V2 might add signed URLs for owner-private photos (e.g., draft photos not yet published) but V1 has no such concept.
- **Filename randomization.** Storage keys use the photo UUID, never the original filename. Prevents enumeration attacks (`/photos/.../IMG_1234.jpg` predictability) and prevents path-traversal via crafted filenames.
- **Rate limits.**
  - **Per-merchant cap:** 20 uploads per day per `uploaded_by_user_id`. Prevents one compromised merchant account from filling storage.
  - **Per-entity cap:** 100 live photos per Provider; 50 per Place. Hard cap at the application layer; further uploads return 429 with "max photos reached" message. The lower Place cap reflects that places have less photo-density value than restaurants.
  - **Per-IP cap:** 50 uploads per IP per day (separate from per-merchant; covers the case of one operator behind a NAT uploading for multiple merchants).
- **Moderation queue.** V1 has no automated moderation — every accepted photo goes live immediately. Manual flagging path: any user can `POST /api/photos/<id>/flag` (auth required, anti-abuse rate-limited) to surface the photo to the operator review queue. Operator can flip `status='flagged'` and `processing_error='moderation_rejected'`.

---

## §8 CDN strategy

**Custom domain:** `cdn.havasuchat.com` (open question §10 — operator may prefer the default `<bucket>.r2.dev` for V1 simplicity). The custom-domain setup is:

1. Casey adds the apex `havasuchat.com` to Cloudflare DNS (free Cloudflare account).
2. Creates `cdn` CNAME record bound to the R2 bucket via Cloudflare's R2 dashboard "connect domain" flow.
3. Cloudflare auto-provisions a TLS cert; bucket becomes reachable at `https://cdn.havasuchat.com/<storage_key>/<variant>.<ext>`.

**Cache headers.** All variant URLs serve with `Cache-Control: public, max-age=31536000, immutable` (one year + immutable hint). Safe because filenames include the photo UUID — the URL never refers to a different image. When an owner replaces a hero photo, the old URL stays valid (and cacheable forever) and the new photo lives at a new URL.

**Invalidation strategy.** Effectively none. The immutable-URL property means we never need to invalidate. The two paths where invalidation could be wanted:
- **Owner deletes a photo.** The row flips to `status='deleted'`; the variant URLs remain valid on the CDN for cache lifetime. Server-side, the relationship filter (`status='live'`) hides it from the gallery. We could call R2's delete API on the underlying objects, but cached copies on edge nodes survive until TTL expiry. Acceptable: deleted photos are unreachable from the site but discoverable for a year if someone bookmarks a direct URL. V2 may add a "force purge" admin action.
- **Owner replaces a hero photo.** New photo lives at a new URL; old URL is unaffected. No invalidation needed.

**Edge behavior.** Cloudflare's CDN serves cached variants from edge POPs globally. For the Lake Havasu / Phoenix / LA corridor (likely majority of traffic), p50 image latency is well under 50ms after first cache fill.

**Bandwidth accounting.** R2 + Cloudflare-cached delivery is free egress. Even at Year 2 scale with 1TB+/mo of image bandwidth, this line item stays at $0.

---

## §9 Migration strategy

Single additive Alembic migration. Adds the `photos` table per §5.1 + the indexes + the CHECK constraints. Reversible — `downgrade()` is `op.drop_table('photos')`.

**No data backfill.** Existing `google_photo_refs` and `attributes.hero_pin_photo_url` stay on `Provider` rows. The `derive_hero_photo` function (§5.2) prefers `Photo` rows when present and falls back to the existing fields when not. Day-one V1 has zero `Photo` rows; the directory looks identical to today; merchants who upload photos through the new flow start replacing Google photos one entity at a time.

**Future V2 cleanup migration (out of scope here):** could backfill featured Google photos into `Photo` rows (download → process → store) for entities without owner photos. This would let us standardize the serving path entirely on R2 and stop hotlinking Google. Triggered when (a) Google starts rate-limiting or breaking hotlinks at meaningful frequency, or (b) we want to apply consistent variant sizing across all listed entities. Not V1.

**Batching with sibling lanes.** Per `account_lite_v01_design.md` §12 sequencing, the Phase 2 schema additions (Place, account-lite, images) can ship as one combined Alembic migration. Image storage is one of those three. Coordinating into one migration is preferable to three separate migrations because Alembic's serial-ordering on a single-region Postgres is a known operational footgun.

---

## §10 Open questions for Casey

1. **Pick a backend.** Recommendation: **Option B — Cloudflare R2**. Trade-offs across A/B/C/D/E are in §2. The biggest "is this right" pressure points: Casey's existing Cloudflare familiarity (zero today? some?), comfort adding one more vendor account, and any pre-existing AWS commitment (none today as far as I can see). If the answer is "I just don't want another vendor right now," Option A (Railway volume) is the only credible "no new vendor" path — but it ships a known-bad CDN story.

2. **Per-entity photo cap: 20 or 50 or 100?** Recommendation: **50 for Provider, 20 for Place**. Storage cost at 50 photos × 5000 providers × 6 variants × ~150KB avg = ~225 GB which is ~$3.40/mo at R2 pricing. Cost is not a real constraint; the cap is about owner UX (a Provider page with 100 photos is a worse page than one with 20 well-chosen photos). 50 is generous without being unwieldy.

3. **Should we allow video uploads in V2?** Recommendation: **probably not**. Video adds 10-30x storage cost per asset, adds transcoding (FFmpeg, separate pipeline), adds player UX, adds moderation surface, and the use case is thin (a restaurant doesn't gain much from a video over a great photo). Defer indefinitely.

4. **Image moderation — automated vs operator review queue?** Cloudflare Images has built-in content moderation (returns a "is this safe" classification). Alternatives: AWS Rekognition, Google Cloud Vision, or a self-hosted NSFW classifier. Recommendation: **manual operator review queue in V1**, since photo volume is small enough Casey can review each before it sees production. **Add automated moderation in V2** once daily upload volume exceeds ~10/day. The architecture supports it — `processing_error='moderation_rejected'` is already in the enum.

5. **CDN custom domain — `cdn.havasuchat.com` vs default `<bucket>.r2.dev`?** Recommendation: **custom domain at launch**. Branding consistency on photo URLs matters more than the 30 minutes of DNS setup. The default `r2.dev` domain also has some published rate limits at the Cloudflare-product level that don't apply to custom-domain bindings; using the custom domain sidesteps those.

6. **Per-Place photo cap and the operator field-trip workflow.** When Casey field-trips a dog park and takes 30 photos, does each one go through the merchant-claim authorization path? Operators (`role='admin'`) bypass the claim check by definition, so operationally yes — admin uploads work the same flow as owner uploads, just with no claim gating. Worth a confirm that "operator uploads under admin" is the intended pattern rather than a separate "operator photo capture" route. Recommendation: **shared route, admin role bypasses claim check** — keeps the surface small.

---

## §11 Effort estimate

Sub-lane sizing (mirrors the place-model and account-lite memos' `S` / `M` / `L` shape):

- **Schema migration + `Photo` ORM model:** S (hours). Single additive table; pattern-match to `Claim` + `UserFavorite` from account-lite §4.
- **Upload route + auth + ownership check (`POST /api/providers/<id>/photos`, `POST /api/places/<id>/photos`):** M (1-2 days). Multipart parsing, validation chain (auth → claim → MIME → size → rate-limit), row creation, background-task dispatch, error pages.
- **Image processing pipeline (Pillow + variants + EXIF strip + WebP/JPEG):** M (2 days). New `app/images/processing.py` module per §6; six discrete stages, each independently testable. The hardest part is the variant-generation correctness (16:9 crop math, quality tuning).
- **R2 SDK integration + bucket setup:** S-M (hours + 1 day operator-side). The code is ~50 lines of boto3 with an R2 `endpoint_url`. Operator-side: create the R2 bucket, generate access keys, bind public domain, set up Cloudflare DNS — that's a 1-2 hour evening for Casey.
- **CDN config + custom domain DNS:** S (operator action). 30 minutes of Cloudflare dashboard work assuming the domain is already on Cloudflare DNS. Longer if domain transfer is needed.
- **UI upload form on Provider edit / Place edit page:** S-M (1-2 days). File picker + drag-drop target + caption inputs + pending-state tile rendering + delete + set-hero + reorder. Shared component between Provider and Place pages.
- **`derive_hero_photo` + `derive_gallery` extension to prefer Photo rows:** S (hours). Per §5.2.
- **Daily sweep job for stuck-uploading rows:** S (hours). Sibling to `_hourly_cleanup_loop` at `app/main.py:246` per background-jobs memo §6.3.
- **Tests:** M (1-2 days). Schema tests, Pillow pipeline tests (each stage independently), upload route tests, auth/claim tests, rate-limit tests, R2-mocked integration tests.

**Total: roughly 5-8 engineering days of focused work**, dispatchable as 1-2 Cursor or CC lanes. The largest single chunk is the processing pipeline (M) which can run in parallel with the upload-route lane.

---

## §12 Sequencing

Image storage lands **after** these prerequisites:

- **Account-lite v0.1** (`account_lite_v01_design.md`) — uploads need a `User` and a `Claim`. Image storage cannot ship before auth exists.
- **Place model** (`place_model_design.md`) — Place rows need photos too. If Place lands first, the `entity_type='place'` branch is wired from day one; if image storage lands first, that branch is dormant until Place ships. Recommended: ship Place first since its schema additions are larger.

Image storage lands **before** these dependents:

- **Verified Presence sponsor sales push** — sponsors expect to upload their own hero photo. Pivot §7 gates this on owner-controlled photos being a feature.
- **Eat & Drink category page UI** — per Opus #4, the visual-first category page depends on owner-uploaded food/patio photos.
- **Home Services category page V2 polish** — V1 can ship with Google photos via the existing `derive_hero_photo` fallback, but owner-uploaded hero photos make sponsor cards distinctly better.
- **Operator field-trip workflow for Place ingest** — operator needs a place to drop the photos taken during a manual recovery sprint.

**Batched migration recommendation.** Per `account_lite_v01_design.md` §12, the Phase 2 schema additions (Place + account-lite + photos) should land as one combined Alembic migration. Three additive table-creation operations + their respective CHECK constraints in one revision. The implementation lane for any of the three should coordinate with the others before applying.

**Within the v1.1 schema pass.** Image storage is the third of three schema lanes in the v1.1 pass. The order — Place → account-lite → photos — flows from dependency direction: Place defines an entity that photos reference; account-lite defines the User that uploads; photos reference both.

---

## §13 What we explicitly DON'T build in V1

Calling these out so the implementation lane doesn't over-scope.

- **Video uploads.** Storage cost + transcoding + player UX + moderation. Defer indefinitely.
- **Image moderation API.** Cloudflare Images / Rekognition / Cloud Vision. V1 ships with manual operator review queue; automated moderation is V1.5 or V2.
- **Signed / private URLs.** Everything is public by design. The owner-private "draft" photo concept doesn't exist in V1.
- **Automatic AI-tagged categorization.** "Is this a food photo or a storefront photo or a patio photo" — interesting but not load-bearing. Owner picks the hero; owner orders the gallery; categorization is a V2 nice-to-have if the photo-density-by-type signal becomes a recommendation input.
- **Cropping / editing UI.** Owner pre-crops before upload. Building an in-browser cropper is a meaningful UX cost for a feature the operating-system-native photo app already handles. V2 if owners complain.
- **Bulk import from Google photos.** Could be a useful migration helper at V2 (download → process → store all Google photos into Photo rows) but not V1. V1 keeps Google photos as the fallback via the existing `derive_hero_photo` tier chain.
- **Watermarking.** No "havasu-chat.com" logo overlay. Photos are owner-property and shouldn't be branded.
- **Animated images / GIFs.** No GIF support; no animated WebP. Static images only. Reduces moderation surface and storage cost.
- **HEIC support.** iPhone-native HEIC requires the `pillow-heif` plugin; not in V1. Owners with HEIC photos can re-export as JPEG from the iOS Photos app.
- **EXIF GPS preservation.** Stripped mandatorily for privacy. Owner who wants location-tagged photos in V2 can opt-in via a per-photo flag — out of scope for V1.
- **Multi-format on-the-fly transforms (e.g., `/photo/<id>?w=400&h=300`).** V1 has three fixed variants. Adding Cloudinary-style URL-parameter transforms is a meaningful infra add (either Cloudflare Workers or a transform service) that we don't need for the static set of surfaces we serve today.
- **Per-photo analytics ("how many times was this photo viewed").** Out of scope. Sponsor analytics dashboard (audit Gap #17) is a separate lane.
- **User-attached photos on reviews.** Out of scope — reviews themselves are V2 per audit §3.19. When reviews land, photos-on-reviews extends the `Photo.entity_type` enum to `'review'`.
- **Logo upload as a distinct asset type.** V1 treats sponsor logos as just another `Photo` row; if logo-specific behavior is needed in V2 (e.g., transparent-background PNG handling, distinct variant sizes), add `Photo.purpose` enum then.

---

## §14 Summary

Image storage is the third foundational schema gap (after Place and account-lite) in the audit's full-vision sequencing. The recommended backend is **Cloudflare R2** — cheapest at every scale tier past V1, S3-compatible escape hatch, built-in CDN edge, zero egress fees. The schema is a single new `Photo` model with polymorphic `(entity_type, entity_id)` reference — same shape as `UserFavorite` and `Claim` from account-lite §4. The processing pipeline runs Pillow inside `BackgroundTasks` per the Option A choice in `background_job_infrastructure_decision.md` §6.4 — three variants (thumbnail / medium / hero 16:9) × two formats (WebP + JPEG) with mandatory EXIF strip and per-entity hash dedup. The upload flow gates on account-lite auth + a verified Claim; CDN domain is `cdn.havasuchat.com` for branding. Total effort 5-8 engineering days; sequenced into the Phase 2 v1.1 schema pass alongside Place and account-lite as one combined Alembic migration. Six open questions for operator decision, with clear recommendations on each.

**Next step after this memo is reviewed:** lock the six open questions, then file a Cursor or CC dispatch brief for (a) the schema migration + `Photo` model, (b) the R2 + Pillow processing module, (c) the upload route + UI. Operator-side R2 bucket + Cloudflare DNS setup (§8) is a parallel Casey-time task that does not block the implementation lane.

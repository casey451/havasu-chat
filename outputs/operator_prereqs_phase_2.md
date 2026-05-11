# Operator Prerequisites — Phase 2

> **Audience:** Casey. **Authored:** session-16 close, 2026-05-14. **Read time:** ~5 minutes. **Action time:** ~1-3 hours total depending on choices.
>
> Phase 2 of the master build plan has two parallel lanes (Lane 2A account-lite + Lane 2B image storage / search). **Each lane has an operator-side prerequisite** that has to be locked before authoring the corresponding Cursor brief — otherwise the brief bakes in unverified assumptions about external service shapes that need rework. This doc gives you the exact steps for each prereq.
>
> The two prereqs are independent. You can do either or both in any order. Neither blocks the other. Authoring the corresponding Cursor brief can start the moment the prereq is locked.

---

## §1 Resend — gates Lane 2A (account-lite, magic-link auth)

### What it is
Resend is a transactional email API for sending one-off emails (password resets, magic links, receipts, etc.) — not a marketing-email service. Lane 2A uses it to send the magic-link login email that account-lite v0.1 is built around. Locked in `docs/STRATEGY_PIVOT_2026-05-12.md` §8.3 and detailed in `docs/maintainability/account_lite_v01_design.md` §9.

### Why we need it before authoring the Lane 2A brief
The brief specifies the integration shape — endpoint URL, expected response, error envelope, dev-mode fallback. If the Resend account isn't created yet, we can't verify the actual API shape (Resend has changed minor things over time) and the brief may bake in stale assumptions. Locking the account first means the brief lands accurate.

### Setup steps

**1. Sign up.** Go to <https://resend.com> → "Get started." Free tier covers 100 emails/day + 3,000/month — more than enough for V1 magic-link traffic.

**2. Verify a sender domain (production-required) OR use the default sandbox domain (dev-only).**
   - **For production sender domain (recommended):** Resend → Domains → Add Domain. Use a domain you control (probably `havasuchat.com` or whatever the production domain ends up being). Resend gives you 3 DNS records to add (SPF, DKIM, MX) — copy them into your DNS provider (Cloudflare DNS, Route 53, wherever the domain lives). Verification typically lands within 5-30 minutes after DNS propagates. Once verified, you can send `from: noreply@havasuchat.com`.
   - **For dev-only sandbox:** Resend's `onboarding@resend.dev` domain works without DNS setup, but Resend caps it at 3 emails/day per recipient. Fine for poking the API by hand; not fine for V1 launch.

**3. Generate an API key.** Resend → API Keys → Create API Key. Name it something obvious (e.g., `havasu-chat-prod`). Set permissions to "Sending access" (not "Full access"). Copy the key — Resend only shows it once.

**4. Drop the key into Railway.** Railway → havasu-chat service → Variables → `+ New Variable`. Add:
   - `RESEND_API_KEY` = `<the key from step 3>`
   - `AUTH_DEV_MODE` = `false` (for production; the design memo §9 also recommends `AUTH_DEV_MODE=true` in your local `.env` for development — when true, the app skips the Resend call and logs the magic-link URL so you can copy-paste it during dev)

**5. (Optional) Email allowlist for end-to-end testing.** Per design memo §9 you can set `AUTH_DEV_EMAIL_ALLOWLIST=casey-test@…,other-test@…` to bypass production rate limits for specific test accounts. Skip for V1; revisit when traffic grows.

### What goes in the Lane 2A brief that you don't have to do
The actual code module (`app/auth/email_sender.py` with the `send_magic_link()` function), the magic-link email template (HTML/text), the `/api/auth/request-link` route handler, the synchronous-vs-queued-send tradeoff (synchronous in V1 per design memo §9). All Cursor's job.

### Time estimate
- Without sender domain (sandbox only): ~10 minutes (signup + key + Railway env drop).
- With sender domain (production-ready): ~30-60 minutes (signup + key + Railway env drop + DNS records + propagation wait).

### What to report back
"Resend done — sender domain `<X>` verified, key dropped into Railway as `RESEND_API_KEY`." Or "Resend done — sandbox only for now, will set up sender domain pre-launch." Either is fine for unblocking Lane 2A brief authoring; the production sender domain can land any time before Lane 2A actually deploys.

---

## §2 Cloudflare R2 — gates Lane 2B (image storage + search)

### What it is
Cloudflare R2 is S3-compatible object storage from Cloudflare with **zero egress fees** — meaning it's free to serve images out to users at any volume. "S3-compatible" means it speaks the same API as Amazon S3, so any code that uses `boto3` (the standard AWS Python library) works against R2 by changing one line (the endpoint URL). Locked in `docs/maintainability/image_storage_design.md` §2.2 + §3 as the V1 image storage backend.

If you've never used object storage: think of it as a big bucket where the app uploads image files (`bucket/photos/provider/abc123/thumb.webp`), and users' browsers fetch them via URL (`https://cdn.havasuchat.com/photos/provider/abc123/thumb.webp` or the default `https://<bucket>.r2.dev/...`). The "object" is the file; the "key" is the path. Different from a database, different from disk on the Railway server — it's a separate service whose only job is storing/serving file blobs cheaply.

### Why we need it before authoring the Lane 2B brief
Same reason as Resend: the brief specifies the bucket name, access pattern, custom-domain wiring, and `boto3` endpoint. Locking the bucket + credentials first means the brief lands accurate. R2 also has a one-time setup decision (custom domain vs default `r2.dev`) that affects the URL shape baked into the codebase — better to make that call before brief authoring than mid-implementation.

### Setup steps

**1. Sign up for Cloudflare (if you don't already have an account).** <https://dash.cloudflare.com/sign-up>. Free tier covers everything we need for R2.

**2. Activate R2.** Cloudflare dashboard → R2 (left sidebar). First time, it prompts you to add a payment method — R2 charges $0 below 10 GB of storage and unlimited egress, so you'll likely never see a bill, but the card is required to activate. Add a card; click activate.

**3. Create a bucket.** R2 → Create Bucket. Name it `havasu-chat-photos` (or whatever — bucket names are global within R2 so something like `havasuchat-photos-prod` may be safer). Region: "Automatic" is fine (R2 picks the lowest-latency region for your Cloudflare account). Don't enable "public access" yet — that comes in step 5.

**4. Generate API tokens.** R2 → Manage R2 API Tokens → Create API Token. Permissions: "Object Read & Write" scoped to the bucket you just created. TTL: "Forever" is fine for production (you can revoke at any time). Click create — Cloudflare shows you three values, all one-time-only:
   - **Access Key ID** (looks like a long hex string)
   - **Secret Access Key** (longer hex string)
   - **Endpoint** (looks like `https://<account-id>.r2.cloudflarestorage.com`)
   
   Copy all three immediately. Cloudflare won't show the secret again.

**5. Choose your public-URL strategy. TWO PATHS — pick one:**

   **Path A (RECOMMENDED for V1): Use the default `<bucket>.r2.dev` URL.** Simplest path: zero DNS work, instant. Bucket → Settings → "Public Access" → enable "R2.dev subdomain." Cloudflare gives you a URL like `https://pub-abc123def.r2.dev`. Image URLs become `https://pub-abc123def.r2.dev/photos/provider/abc123/thumb.webp`. Slightly ugly but functional; you can swap to a custom domain later without code changes.

   **Path B (recommended for launch polish, can defer): Custom domain `cdn.havasuchat.com`.** Per design memo §8 + §10 (open question — your call). Requires:
   - You own a domain (`havasuchat.com` or whatever) and it's in Cloudflare DNS
   - In R2 bucket settings → Custom Domains → "Connect Domain" → enter `cdn.havasuchat.com`
   - Cloudflare auto-creates the CNAME record + provisions a TLS cert (~5-10 min)
   - Image URLs become `https://cdn.havasuchat.com/photos/provider/abc123/thumb.webp`
   
   **Recommendation: do Path A now to unblock Lane 2B brief authoring; switch to Path B at any natural point before launch.** The codebase reads the public-URL prefix from an env var so swapping is one variable change + bucket setting toggle.

**6. Drop credentials into Railway.** Railway → havasu-chat service → Variables → add:
   - `R2_ACCESS_KEY_ID` = `<from step 4>`
   - `R2_SECRET_ACCESS_KEY` = `<from step 4>`
   - `R2_ENDPOINT_URL` = `<from step 4 — the cloudflarestorage.com URL>`
   - `R2_BUCKET_NAME` = `<your bucket name from step 3>`
   - `R2_PUBLIC_URL_BASE` = either `https://pub-abc123def.r2.dev` (Path A) OR `https://cdn.havasuchat.com` (Path B). The code uses this to build public image URLs.

### What goes in the Lane 2B brief that you don't have to do
The `boto3` client setup pinned to the R2 endpoint, the upload helper, the key-naming convention, the Pillow image processing pipeline (thumbnail/medium/hero variants + EXIF strip + WebP conversion + dedup hash), the `Photo` schema (`docs/maintainability/image_storage_design.md` §5.1), the upload route, the search-index FTS work that ships in the same lane. All Cursor's job.

### Time estimate
- Path A (default r2.dev URL): ~30-45 minutes (signup + payment card + bucket + API token + Railway env drop). 
- Path B (custom domain): add ~30 min for the DNS + cert flow if your domain is already in Cloudflare DNS; add ~hours if your domain is registered elsewhere and needs to be migrated to Cloudflare nameservers first.

### What to report back
"R2 done — bucket `<name>`, public URL `<r2.dev or custom>`, credentials in Railway as `R2_*` variables." That's enough to unblock Lane 2B brief authoring.

---

## §3 Order + parallelism

Both prereqs are independent. You can do them in any order, in parallel, or stagger them. Suggested order if you only do one at a time:

1. **Resend first** if you want to ship Lane 2A (account-lite) before Lane 2B (image storage). Account-lite is the smaller lane (5-7 day brief estimate) and unblocks the user-claim flow that the rest of the directory depends on.
2. **R2 first** if you want to ship Lane 2B before 2A. Image storage is bigger (7-10 day brief estimate) and the search-index FTS work in the same lane is what makes the directory feel responsive.

Per master plan §4 Phase 2, both lanes are designed to ship in parallel — they're file-disjoint per dispatch_protocol Rule 3, so two Cursor sessions can run concurrently if you want maximum throughput.

**There's no wrong order.** Just don't dispatch a brief before its prereq is locked.

---

## §4 What happens after both are done

When both prereqs are locked + reported back, the next agent (or this one in a future session) authors the corresponding Phase 2 dispatch briefs:

- `outputs/cursor_brief_phase_2a_account_lite.md` — heavy-prescriptive operating doc mirroring `outputs/cursor_brief_phase_1_entity_schema.md` shape (§0 baseline + reads, §1 why, §2 locked decisions, §3 sub-phase boundaries, §4+ deliverables, §10 what NOT to do, §11 deviations, §12 risks, §13 final report format).
- `outputs/cursor_brief_phase_2b_image_storage_search.md` — same shape, scoped to image storage + Postgres FTS + pg_trgm.

Plus short paste-into-Cursor dispatch prompts at `outputs/cursor_dispatch_prompt_phase_2a.md` and `outputs/cursor_dispatch_prompt_phase_2b.md` mirroring the 1C/1D dispatch prompts.

Brief authoring takes ~1-3 hours per lane (loading the design memos + writing 600-1000 lines per brief). It's the kind of work a fresh agent's full context window handles best — see `outputs/session_17_boot_prompt.md` for the boot pattern.

---

*Authored at session-16 close, 2026-05-14, in response to Casey's "give me directions on what you need" / "i dont know what this is" answers to the Phase 2 prereq disambiguation. Lives durably under `outputs/` per dispatch_channels gotcha #12 so the next agent can reference it without reauthoring.*

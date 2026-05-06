# url_fetcher

`app/contrib/url_fetcher.py` (~248 lines)

## Purpose

**Defense-in-depth HTTP fetch** for untrusted submission URLs: SSRF-resistant DNS + IP checks, bounded redirects and body size, HTML-only content types, and lightweight **title/description extraction** via BeautifulSoup (`og:title`, `<title>`, `og:description`, `<meta name=description>`). Feeds **`Contribution`** URL enrichment (`url_title`, `url_description`, `url_fetch_status`, `url_fetched_at`).

## Public surface

**Constants**

- **`MAX_BODY_BYTES`** — 5 MiB cap on streamed response body.
- **`MAX_REDIRECTS`** — 3 manual redirect hops (client **`follow_redirects=False`**).
- **`USER_AGENT`** — Identifying UA string for outbound requests.
- **`ALLOWED_CONTENT_TYPES`** — HTML-family MIME prefixes only.

**`UrlFetchResult` dataclass** — Fields: **`status`** (`"success"` \| `"error"` \| `"timeout"` \| …), **`title`**, **`description`**, **`final_url`**, **`error_message`**, **`fetched_at`** (naive UTC timestamp factory).

**`fetch_url_metadata(url: str, timeout_seconds: int = 10) -> UrlFetchResult`** — Single entry point.

## Inputs and outputs

**Success.** HTTP 2xx, allowed **`Content-Type`**, parsed HTML yields optional truncated title (≤300 chars) / description (≤1000 chars).

**Blocking (`blocked:*`).** Unsupported scheme, localhost-ish hosts, private/reserved IP literals or **resolved** addresses from **`getaddrinfo`**.

**Redirect loop.** Follows **301/302/303/307/308** via **`urljoin`**, re-validates target each hop; **`too_many_redirects`** / **`redirect_missing_location`** errors.

**Size guards.** Rejects **`Content-Length`** above cap when parseable; streaming **`iter_bytes`** stops when cumulative bytes exceed **`MAX_BODY_BYTES`**.

**Timeouts / transport errors** — Distinct **`timeout`** vs generic **`request_error:`** messages.

## Internal structure

**`_is_blocked_target`** — **`urlparse`** scheme allowlist (**http/https**), hostname sanity, **`ip_address`** classification for literal IPs, iterative **`socket.getaddrinfo`** resolution for DNS SSRF defense.

**`_normalize_url`** — Prepends **`https://`** when scheme missing.

**`_content_type_ok`** — Strips parameters, accepts exact or `+suffix` HTML variants.

**`_extract_meta`** — BeautifulSoup **`html.parser`** meta scraping.

Main **`fetch_url_metadata`** implements **manual redirect loop** with **`client.stream("GET", ...)`** to bound bytes without loading full response into memory first.

## Conventions

**Streaming read** — Parses HTML only after full capped buffer assembled (still bounded by **`MAX_BODY_BYTES`**).

**Inclusive logging** — Unexpected outer **`except`** logs **`logger.exception`** once with **`pragma: no cover`** note.

## Known limitations

**HTML-only** — JSON PDF or non-HTML success responses rejected via content-type gate.

**Redirect hop re-validation** — Each hop runs SSRF checks; legitimate chains through unusual hosts may fail.

**Character encoding** — Uses response-declared encoding with **`errors="replace"`** fallback to UTF-8.

**No caching** — Repeated enrichments re-fetch.

## Configuration

No environment variables; caps are code constants.

## Related

**Direct callers:**

- **`app/contrib/enrichment.py`** — primary production caller.

**Tests:** **`tests/test_url_fetcher.py`** (blocked hosts, redirects, meta extraction, caps).

**Operational context:** **`docs/components/enrichment.md`**, **`docs/components/admin_contributions_html.md`** (operator-visible fetch status).

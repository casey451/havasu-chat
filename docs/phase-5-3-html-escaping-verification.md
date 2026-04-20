# Phase 5.3 — HTML escaping verification (pre-commit)

Combined notes from the last two review exchanges: quick green-light summary + detailed field-by-field confirmation with code references.

---

## 1. Quick confirmation (one paragraph)

In `app/admin/contributions_html.py`, every place those fields hit the HTML goes through `_esc()` (i.e. `html.escape(..., quote=True)`), so you’re covered for normal page output and for attribute/textarea contexts: **list** uses `_esc(r.submission_name)`; **detail** uses `_esc` on `submission_name`, `submission_category_hint`, `submission_notes`, `url_title`, `url_description` (truncated), and `review_notes` (plus related strings like email/URL text); **approve** prefill wraps `submission_name`, `submission_category_hint`, `submission_notes`, the provider block’s merged **description** (notes + `url_description`) and **hours**, and program/event copies of the same; **flash** from the query string is `_esc`’d on the list page; validation error text on failed approve is `_esc`’d too. The only strings interpolated without `_esc` are structural (IDs, fixed copy, enum-like `status`/`entity_type`/`source`/`rejection_reason` from controlled sets). **Green-light** for commit from an XSS/escaping standpoint for the fields originally listed (submission_name, notes, category_hint, url_title, url_description, review_notes).

---

## 2. Detailed verification (requested fields + Places)

Verification is complete for `app/admin/contributions_html.py` (the only module that renders these contribution admin pages). Every field below is passed through `_esc()`, which wraps `html.escape(..., quote=True)` (safe for text nodes and for `value="..."` / textarea bodies).

| Field | Escaped? | Notes |
|--------|------------|--------|
| `submission_name` | Yes | List link, detail, approve forms |
| `submission_notes` | Yes | Detail, program/event textarea; provider description merge |
| `submission_category_hint` | Yes | Detail, category inputs on approve |
| `submission_url` | Yes | `url_line`: `_esc` on both `href` and link text |
| `submitter_email` | Yes | Detail submission section |
| `url_title` | Yes | Enrichment block |
| `url_description` | Yes | Enrichment block (truncated), merged into provider description then `_esc` |
| `review_notes` | Yes | Frozen “Review state” |
| `rejection_reason` | Yes | Frozen “Review state” |
| Places `display_name`, `formatted_address`, `phone`, `website_uri` | Yes | Detail enrichment + approve-form prefills (`_esc(str(ged.get(...)))`) |

No gaps were found; **no code change** was required before commit approval.

---

## 3. Representative code snippets

### Central helper

```python
def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)
```

*(Source: `app/admin/contributions_html.py` — `_esc` definition.)*

### Submission block (email, name, URL, category hint, notes)

```python
        sub_url = c.submission_url or ""
        url_line = (
            f'<a href="{_esc(sub_url)}" target="_blank" rel="noopener noreferrer">{_esc(sub_url)}</a>'
            if sub_url
            else "—"
        )
        llm_line = _esc(c.llm_source_chat_log_id or "—")
        if c.llm_source_chat_log_id:
            llm_line = _esc(c.llm_source_chat_log_id)
        sub = f"""<div class="section"><h2>Submission</h2>
<div class="kv"><span class="k">Submitter email</span> {_esc(c.submitter_email or "—")}</div>
<div class="kv"><span class="k">IP hash</span> {_ip_display(c.submitter_ip_hash)}</div>
<div class="kv"><span class="k">Entity type</span> {_entity_pill(c.entity_type)}</div>
<div class="kv"><span class="k">Name</span> {_esc(c.submission_name)}</div>
<div class="kv"><span class="k">URL</span> {url_line}</div>
<div class="kv"><span class="k">Category hint</span> {_esc(c.submission_category_hint or "—")}</div>
<div class="kv"><span class="k">Notes</span> {_esc(c.submission_notes or "—")}</div>
```

*(Source: `app/admin/contributions_html.py` — detail view submission section.)*

### URL enrichment + Google Places fields

```python
        if c.submission_url or c.url_fetch_status or c.url_title:
            enrich_bits.append(
                f'<div class="kv"><span class="k">URL fetch</span> {_esc(c.url_fetch_status or "—")}</div>'
            )
            if c.url_title:
                enrich_bits.append(f'<div class="kv"><span class="k">URL title</span> {_esc(c.url_title)}</div>')
            if c.url_description:
                enrich_bits.append(
                    f'<div class="kv"><span class="k">URL description</span> {_esc(c.url_description[:500])}</div>'
                )
            ...
            if ged.get("display_name"):
                enrich_bits.append(f'<div class="kv"><span class="k">display_name</span> {_esc(str(ged.get("display_name")))}</div>')
            if ged.get("formatted_address"):
                enrich_bits.append(
                    f'<div class="kv"><span class="k">formatted_address</span> {_esc(str(ged.get("formatted_address")))}</div>'
                )
            if ged.get("phone"):
                enrich_bits.append(f'<div class="kv"><span class="k">phone</span> {_esc(str(ged.get("phone")))}</div>')
            if ged.get("website_uri"):
                enrich_bits.append(f'<div class="kv"><span class="k">website</span> {_esc(str(ged.get("website_uri")))}</div>')
```

*(Source: `app/admin/contributions_html.py` — detail view enrichment section.)*

### Also covered (not duplicated as full snippets)

- List table: `_esc(r.submission_name)` for the name link.
- Frozen review: `_esc(c.rejection_reason or "—")`, `_esc(c.review_notes or "—")`.
- Approve GET prefills: `_esc` on names, notes, category, merged provider description/hours, Places fields in program/event forms, `event_url`, etc.
- List flash query param: `_esc(flash)`; approve validation errors: `_esc(err)`.

For exact line numbers in-repo, open `app/admin/contributions_html.py` and search for `_esc(`.

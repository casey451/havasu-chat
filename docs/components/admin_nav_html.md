# admin_nav_html

`app/admin/nav_html.py` (~13 lines)

## Purpose

Single shared **navigation fragment** for Phase 5 admin HTML pages: one function returns the standard `<nav class="nav">` block so every operator screen stays visually and navigationally consistent without a template engine (inline string HTML).

## Public surface

**`admin_phase5_nav_html() -> str`** — Returns a fixed six-link nav (leading indentation included so it nests cleanly inside sibling modules’ `_nav_shell` bodies):

1. Admin home — `/admin?tab=queue`
2. Contributions — `/admin/contributions`
3. Mentioned entities — `/admin/mentioned-entities`
4. Categories — `/admin/categories`
5. Analytics — `/admin/analytics`
6. Feedback — `/admin/feedback`

No parameters; no auth logic (callers gate pages separately).

## Inputs and outputs

Pure function: **no inputs**, **output** is a literal HTML substring. Not escaped — links are static paths known at compile time.

## Internal structure

One module docstring and one function returning a triple-quoted string. No CSS classes beyond `nav` and `nav`-scoped anchors (styles live in each caller’s `_nav_shell` inline `<style>` block).

## Conventions

**Name vs file.** The implementing function is `admin_phase5_nav_html`, not `nav_html`; imports use `from app.admin.nav_html import admin_phase5_nav_html`.

**Whitespace.** Callers embed the return value inside a `<div class="wrap">`; the string includes leading spaces so HTML source indentation stays readable.

## Known limitations

**Adding or renaming a top-level admin surface requires editing this string** and ensuring `router.py` (or register modules) expose matching paths — easy to forget when adding a seventh tab.

**No active-route highlighting** — unlike some SPAs, every link looks the same regardless of current page.

## Configuration

None.

## Related

- Every `app/admin/*_html.py` module that defines `_nav_shell` — each interpolates `admin_phase5_nav_html()` below `<body>`.
- `docs/components/admin_router.md` — route inventory for the targets of these links.

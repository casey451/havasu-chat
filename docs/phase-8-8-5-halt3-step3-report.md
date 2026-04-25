# Phase 8.8.5 — HALT 3 Step 3 Report

Date: 2026-04-25  
Scope: Classifier implementation + row dict integration + unit tests

---

## 1) Classifier function code (verbatim)

```python
def _classify_description_richness(text: str | None) -> str:
    if text is None or not str(text).strip():
        return "sparse"
    normalized = str(text).strip().lower()
    word_count = len(_WORD_RE.findall(normalized))
    fact_concepts: set[str] = set()
    for concept, pats in _RICHNESS_FACT_CONCEPT_PATTERNS.items():
        if any(p.search(normalized) for p in pats):
            fact_concepts.add(concept)
    if word_count >= _RICH_WORD_THRESHOLD or len(fact_concepts) >= _RICH_FACT_THRESHOLD:
        return "rich"
    return "sparse"


def _classify_provider_richness(
    description: str | None, featured_description: str | None
) -> str:
    if featured_description is not None and str(featured_description).strip():
        return "rich"
    return _classify_description_richness(description)
```

---

## 2) `_provider_dict` and `_program_dict` modifications (verbatim)

```python
def _program_dict(p: Program) -> dict[str, Any]:
    ages = None
    if p.age_min is not None or p.age_max is not None:
        ages = f"{p.age_min if p.age_min is not None else '?'}-{p.age_max if p.age_max is not None else '?'}"
    loc = _program_location_display(p.location_name, p.location_address)
    out: dict[str, Any] = {
        "type": "program",
        "name": p.title,
        "provider_name": p.provider_name,
        "activity_category": p.activity_category,
        "age_range": ages,
        "schedule_days": list(p.schedule_days or [])[:7],
        "schedule_hours": f"{p.schedule_start_time}-{p.schedule_end_time}",
        "cost": p.cost,
        "description": _truncate(p.description, 120),
        "description_richness": _classify_description_richness(p.description),
        "tags": list(p.tags or [])[:8],
    }
    if loc:
        out["location"] = loc
    return out


def _provider_dict(p: Provider) -> dict[str, Any]:
    desc = p.featured_description if (p.featured_description and p.featured_description.strip()) else p.description
    return {
        "type": "provider",
        "name": p.provider_name,
        "category": p.category,
        "address": p.address,
        "phone": p.phone,
        "hours": _truncate(p.hours, 120),
        "description": _truncate(desc, 120),
        "description_richness": _classify_provider_richness(
            p.description, p.featured_description
        ),
    }
```

---

## 3) Added unit test coverage (`tests/test_tier2_db_query.py`)

- Aqua Beginnings text -> `rich`
- Grace Arts Live text -> `sparse`
- Aquatic Center text -> `rich`
- Aqua Aerobics / Water Fitness Program text -> `rich`
- `_provider_dict` with non-empty featured description forces `description_richness="rich"`
- `_provider_dict` with null featured description falls back to description classification
- `_program_dict` includes `description_richness`
- Edge cases `None`, empty string, whitespace, and single-word text -> `sparse`

---

## 4) Pytest summary

Command:

```powershell
.venv/Scripts/python -m pytest tests/test_tier2_db_query.py -v
```

Result:

- `28 passed in 1.95s`


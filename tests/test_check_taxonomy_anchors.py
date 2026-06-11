"""scripts/check_taxonomy_anchors.py — the §6.1 phase-gate checker (B3 prep).

Seeds a tiny taxonomy (department → leaf) + anchor entities and asserts the
checker's four outcomes: ok, mismatch, missing, no_primary — plus the
department filter and the exit-code contract via ``main()``.
"""

from __future__ import annotations

import csv
import uuid

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Category, Entity, EntityCategory
from scripts.check_taxonomy_anchors import check_anchors, main

_SUF = uuid.uuid4().hex[:6]
_DEPT = f"Health & Medical {_SUF}"
_LEAF_OK = f"Hearing & Audiology {_SUF}"
_LEAF_WRONG = f"Primary Care {_SUF}"


def _seed():
    with SessionLocal() as s:
        dept = Category(name=_DEPT, slug=f"hm-{_SUF}", level=0)
        s.add(dept)
        s.flush()
        leaf_ok = Category(
            name=_LEAF_OK, slug=f"hearing-{_SUF}", level=1, parent_id=dept.id
        )
        leaf_wrong = Category(
            name=_LEAF_WRONG, slug=f"primary-{_SUF}", level=1, parent_id=dept.id
        )
        s.add_all([leaf_ok, leaf_wrong])
        s.flush()

        ok_ent = Entity(entity_type="provider", slug=f"cleartone-{_SUF}", name=f"Cleartone {_SUF}")
        wrong_ent = Entity(entity_type="provider", slug=f"lumpkin-{_SUF}", name=f"Lumpkin {_SUF}")
        noprim_ent = Entity(entity_type="provider", slug=f"views-{_SUF}", name=f"Views {_SUF}")
        s.add_all([ok_ent, wrong_ent, noprim_ent])
        s.flush()
        s.add_all(
            [
                EntityCategory(entity_id=ok_ent.id, category_id=leaf_ok.id, is_primary=True),
                EntityCategory(entity_id=wrong_ent.id, category_id=leaf_wrong.id, is_primary=True),
                # noprim_ent: linked but NOT primary.
                EntityCategory(entity_id=noprim_ent.id, category_id=leaf_ok.id, is_primary=False),
            ]
        )
        s.commit()
        return dept.id, leaf_ok.id, leaf_wrong.id


def _cleanup():
    with SessionLocal() as s:
        ents = [
            e
            for e in s.query(Entity).all()
            if e.slug and e.slug.endswith(_SUF)
        ]
        ids = [e.id for e in ents]
        s.execute(delete(EntityCategory).where(EntityCategory.entity_id.in_(ids)))
        for e in ents:
            s.delete(e)
        s.execute(delete(Category).where(Category.slug.in_(
            [f"hm-{_SUF}", f"hearing-{_SUF}", f"primary-{_SUF}"]
        )))
        s.commit()


def _anchors():
    return [
        {"row_name": f"Cleartone {_SUF}", "expected_department": _DEPT,
         "expected_leaf": _LEAF_OK, "case_id": "6"},
        {"row_name": f"Lumpkin {_SUF}", "expected_department": _DEPT,
         "expected_leaf": _LEAF_OK, "case_id": "7"},
        {"row_name": f"Ghost {_SUF}", "expected_department": _DEPT,
         "expected_leaf": _LEAF_OK, "case_id": "8"},
        {"row_name": f"Views {_SUF}", "expected_department": _DEPT,
         "expected_leaf": _LEAF_OK, "case_id": "9"},
        {"row_name": f"Other Dept {_SUF}", "expected_department": "Eat & Drink",
         "expected_leaf": "Restaurants", "case_id": "3"},
    ]


def test_checker_statuses_and_department_filter():
    _seed()
    try:
        with SessionLocal() as s:
            results = check_anchors(s, _anchors(), department=_DEPT)
        by_name = {r.row_name: r for r in results}
        assert len(results) == 4  # the Eat & Drink anchor is filtered out
        assert by_name[f"Cleartone {_SUF}"].status == "ok"
        mismatch = by_name[f"Lumpkin {_SUF}"]
        assert mismatch.status == "mismatch"
        assert mismatch.actual_leaf == _LEAF_WRONG
        assert by_name[f"Ghost {_SUF}"].status == "missing"
        assert by_name[f"Views {_SUF}"].status == "no_primary"
    finally:
        _cleanup()


def test_main_exit_codes(tmp_path):
    _seed()
    try:
        path = tmp_path / "anchors.csv"
        fields = ["row_name", "expected_department", "expected_leaf", "case_id"]

        def write(rows):
            with path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)

        all_pass = [_anchors()[0]]
        write(all_pass)
        assert main(["--anchors", str(path)]) == 0

        with_missing = [_anchors()[0], _anchors()[2]]
        write(with_missing)
        assert main(["--anchors", str(path)]) == 1  # missing fails the gate…
        assert main(["--anchors", str(path), "--allow-missing"]) == 0  # …unless allowed

        with_mismatch = [_anchors()[1]]
        write(with_mismatch)
        assert main(["--anchors", str(path), "--allow-missing"]) == 1  # mismatch always fails
    finally:
        _cleanup()

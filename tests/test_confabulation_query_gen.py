"""Tests for :mod:`app.eval.confabulation_query_gen` (spec section 5.1 test 1)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Program, Provider
from app.eval.confabulation_query_gen import (
    _PROBES_PROGRAM,
    _PROBES_PROVIDER,
    generate_probes,
    normalize_row_name_for_include,
)


def _suffix() -> str:
    return uuid.uuid4().hex[:10]


def _prov(db: Session, *, name: str) -> Provider:
    p = Provider(
        provider_name=name,
        category="misc",
        verified=True,
        draft=False,
        is_active=True,
        source="confab-querygen-test",
        description=f"{name} description for search",
    )
    db.add(p)
    db.flush()
    return p


def _prog(db: Session, *, title: str, provider: Provider) -> Program:
    pr = Program(
        title=title,
        description="Twenty character minimum. Program desc.",
        activity_category="arts",
        schedule_days=["saturday"],
        schedule_start_time="10:00",
        schedule_end_time="11:00",
        location_name="Lake Havasu City",
        provider_name=provider.provider_name,
        provider_id=provider.id,
        source="confab-querygen-test",
        verified=True,
        is_active=True,
        draft=False,
    )
    db.add(pr)
    db.flush()
    return pr


def _provider_signature(name: str) -> set[tuple[str, str, str, str]]:
    return {
        (f"tell me about {name}", "provider", "provider_tell_me_about", name),
        (f"what does {name} offer", "provider", "provider_what_offer", name),
        (f"where is {name}", "provider", "provider_where_is", name),
    }


def _program_signature(title: str) -> set[tuple[str, str, str, str]]:
    return {
        (f"tell me about {title}", "program", "program_tell_me_about", title),
        (f"when does {title} meet", "program", "program_when_meet", title),
        (f"what is {title}", "program", "program_what_is", title),
    }


def _probe_tuples(probes: list) -> set[tuple[str, str, str, str]]:
    return {(p.query_text, p.row_type, p.template_id, p.row_id) for p in probes}


def test_generate_probes_nine_probes_and_templates() -> None:
    """2 live providers + 1 live program: 9 probes, literal templates from HALT 1 closure."""
    p1 = f"Alpha zz {_suffix()}"
    p2 = f"Zebra yy {_suffix()}"
    title = f"middle ProG Title {_suffix()}"

    with SessionLocal() as db:
        a = _prov(db, name=p1)
        b = _prov(db, name=p2)
        pr = _prog(db, title=title, provider=a)
        db.commit()
        id_a, id_b, id_pr = a.id, b.id, pr.id

    with SessionLocal() as db:
        subset = [p for p in generate_probes(db) if p.row_id in (id_a, id_b, id_pr)]
        assert len(subset) == 9

    got_a = _probe_tuples([p for p in subset if p.row_id == id_a])
    got_b = _probe_tuples([p for p in subset if p.row_id == id_b])
    got_pr = _probe_tuples([p for p in subset if p.row_id == id_pr])

    assert got_a == {(qt, rt, tid, id_a) for (qt, rt, tid, _) in _provider_signature(p1)}
    assert got_b == {(qt, rt, tid, id_b) for (qt, rt, tid, _) in _provider_signature(p2)}
    assert got_pr == {(qt, rt, tid, id_pr) for (qt, rt, tid, _) in _program_signature(title)}

    for template, _template_id in _PROBES_PROVIDER:
        assert "<n>" in template
    for template, _template_id in _PROBES_PROGRAM:
        assert "<n>" in template


def test_normalize_row_name_for_include_en_dash_matches_ascii_hyphen() -> None:
    assert normalize_row_name_for_include("Open Jump - 90 Minutes") == normalize_row_name_for_include(
        "Open Jump \u2013 90 Minutes"
    )
    assert normalize_row_name_for_include("Open Jump \u2014 90") == normalize_row_name_for_include(
        "Open Jump - 90"
    )


def test_substitution_verbatim_display_name() -> None:
    """<n> is the display name (provider_name / program title) with no case changes."""
    name = f"WeIrD cAsE CoMpArE {_suffix()}"
    ttitle = f"YoUtH ThEaTrE  {_suffix()}"
    with SessionLocal() as db:
        pv = _prov(db, name=name)
        pr = _prog(db, title=ttitle, provider=pv)
        db.commit()
        pid, prid = pv.id, pr.id
    with SessionLocal() as db:
        allp = generate_probes(db)
    p_probes = [x for x in allp if x.row_id == pid]
    p_tell = next(p for p in p_probes if p.template_id == "provider_tell_me_about")
    assert p_tell.query_text == f"tell me about {name}"
    g_prog = [x for x in allp if x.row_id == prid]
    w = next(p for p in g_prog if p.template_id == "program_when_meet")
    assert w.query_text == f"when does {ttitle} meet"

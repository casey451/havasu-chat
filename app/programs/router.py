from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.models import Program
from app.schemas.program import ProgramCreate, ProgramRead

router = APIRouter()


def _program_from_create(payload: ProgramCreate) -> Program:
    # Admin-submitted entries are auto-verified; provider/parent stay unverified
    # until AA-3's claim flow promotes them.
    verified = payload.source == "admin"
    return Program(
        title=payload.title,
        description=payload.description,
        activity_category=payload.activity_category,
        age_min=payload.age_min,
        age_max=payload.age_max,
        schedule_days=list(payload.schedule_days),
        schedule_start_time=payload.schedule_start_time,
        schedule_end_time=payload.schedule_end_time,
        location_name=payload.location_name,
        location_address=payload.location_address,
        cost=payload.cost,
        provider_name=payload.provider_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        contact_url=payload.contact_url,
        source=payload.source,
        verified=verified,
        is_active=payload.is_active,
        tags=list(payload.tags),
        embedding=payload.embedding,
    )


@router.post("/programs", response_model=ProgramRead)
@limiter.limit("5/minute")
def create_program(
    request: Request, payload: ProgramCreate, db: Session = Depends(get_db)
) -> Program:
    program = _program_from_create(payload)
    db.add(program)
    db.commit()
    db.refresh(program)
    return program


@router.get("/programs", response_model=list[ProgramRead])
def list_programs(db: Session = Depends(get_db)) -> list[Program]:
    return (
        db.query(Program)
        .filter(Program.is_active.is_(True))
        .order_by(Program.created_at.desc())
        .all()
    )


@router.get("/programs/{program_id}", response_model=ProgramRead)
def get_program(program_id: str, db: Session = Depends(get_db)) -> Program:
    program = db.query(Program).filter(Program.id == program_id).first()
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program

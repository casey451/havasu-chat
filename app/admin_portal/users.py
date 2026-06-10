"""Users & access — search, role changes, activate/deactivate.

Replaces the SQL-only admin promotion path (User docstring: "promoted to
admin SQL-only (V1)"). Every write records an audit row when the audit
table exists (see audit_models.record_audit).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.admin_portal.audit_models import record_audit
from app.admin_portal.guard import guard
from app.admin_portal.shared import render
from app.db.database import get_db
from app.db.models import Claim, User

router = APIRouter()

ROLES = ("end_user", "merchant", "admin")
PAGE_SIZE = 50


@router.get("/users", response_model=None)
def users_list(
    request: Request,
    q: str = "",
    role: str = "",
    active: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect

    stmt = select(User)
    if q.strip():
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(User.email).like(needle), func.lower(User.display_name).like(needle))
        )
    if role in ROLES:
        stmt = stmt.where(User.role == role)
    if active in ("yes", "no"):
        stmt = stmt.where(User.is_active.is_(active == "yes"))

    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0)
    page = max(1, page)
    users = (
        db.execute(
            stmt.order_by(desc(User.created_at)).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
        )
        .scalars()
        .all()
    )

    role_counts = dict(
        db.execute(select(User.role, func.count()).group_by(User.role)).all()
    )

    return render(
        request,
        "portal_users.html",
        "users",
        {
            "users": users,
            "q": q,
            "role": role,
            "active": active,
            "roles": ROLES,
            "page": page,
            "pages": max(1, -(-total // PAGE_SIZE)),
            "total": total,
            "role_counts": role_counts,
        },
    )


@router.get("/users/{user_id}", response_model=None)
def user_detail(
    request: Request, user_id: str, db: Session = Depends(get_db)
) -> HTMLResponse | RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    claims = (
        db.execute(
            select(Claim).where(Claim.user_id == user_id).order_by(desc(Claim.claimed_at))
        )
        .scalars()
        .all()
    )
    return render(
        request, "portal_user_detail.html", "users", {"user": user, "claims": claims, "roles": ROLES}
    )


@router.post("/users/{user_id}/role", response_model=None)
def set_role(
    request: Request, user_id: str, role: str = Form(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="invalid role")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    old_role = user.role
    if role != old_role:
        user.role = role
        record_audit(
            db,
            action="user.role_change",
            target_type="user",
            target_id=user_id,
            detail=f"{user.email}: {old_role} -> {role}",
        )
        db.commit()
    return RedirectResponse(url=f"/admin/portal/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/toggle-active", response_model=None)
def toggle_active(
    request: Request, user_id: str, db: Session = Depends(get_db)
) -> RedirectResponse:
    if (redirect := guard(request)) is not None:
        return redirect
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    user.is_active = not user.is_active
    record_audit(
        db,
        action="user.activate" if user.is_active else "user.deactivate",
        target_type="user",
        target_id=user_id,
        detail=user.email,
    )
    db.commit()
    return RedirectResponse(url=f"/admin/portal/users/{user_id}", status_code=303)

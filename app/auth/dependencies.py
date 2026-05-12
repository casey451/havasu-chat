"""FastAPI dependencies for auth-gated routes."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.db.models import User


def get_current_user(request: Request) -> User | None:
    return getattr(request.state, "current_user", None)


def require_user(request: Request) -> User:
    user = get_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login_required",
        )
    return user


def require_admin(request: Request) -> User:
    user = require_user(request)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_only",
        )
    return user

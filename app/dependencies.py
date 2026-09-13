"""FastAPI dependencies: db, current user, admin guard, language."""
from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.utils.i18n import normalize_lang

Db = Annotated[Session, Depends(get_db)]


def get_lang(request: Request) -> str:
    q = request.query_params.get("lang")
    if q:
        return normalize_lang(q)
    cookie = request.cookies.get("vyron_lang")
    user = getattr(request.state, "user", None)
    if user is not None and getattr(user, "lang", None):
        return normalize_lang(user.lang)
    return normalize_lang(cookie)


def get_current_user(request: Request, db: Db) -> models.User | None:
    return getattr(request.state, "user", None)


def require_user(request: Request, db: Db) -> models.User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="auth_required")
    return user


def user_roles(user: models.User) -> set[str]:
    return {ur.role.name for ur in user.roles if ur.role}


def require_admin(request: Request, db: Db) -> models.User:
    user = require_user(request, db)
    if "admin" not in user_roles(user):
        raise HTTPException(status_code=403, detail="admin_required")
    return user


def require_seller(request: Request, db: Db) -> models.User:
    user = require_user(request, db)
    roles = user_roles(user)
    if "seller" not in roles and "admin" not in roles:
        raise HTTPException(status_code=403, detail="seller_required")
    return user

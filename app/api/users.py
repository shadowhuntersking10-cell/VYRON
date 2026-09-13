"""Current-user profile API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import models
from app.auth.service import AuthError
from app.dependencies import Db, require_user
from app.utils.i18n import normalize_lang
from app.utils.security import hash_password, validate_password_strength, verify_password

router = APIRouter(prefix="/api/users", tags=["users"])


class ProfilePatch(BaseModel):
    display_name: str | None = None
    lang: str | None = None
    theme: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str


@router.get("/me")
def get_me(request: Request, db: Db):
    user = require_user(request, db)
    return {"id": user.id, "username": user.username, "email": user.email,
            "display_name": user.display_name, "avatar": user.avatar,
            "lang": user.lang, "theme": user.theme}


@router.patch("/me")
def patch_me(body: ProfilePatch, request: Request, db: Db):
    user = require_user(request, db)
    if body.display_name is not None:
        user.display_name = body.display_name[:64]
    if body.lang is not None:
        user.lang = normalize_lang(body.lang)
    if body.theme in ("dark", "light", "system"):
        user.theme = body.theme
    db.commit()
    return {"ok": True}


@router.post("/me/password")
def change_password(body: PasswordChange, request: Request, db: Db):
    user = require_user(request, db)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="invalid_password")
    if body.new_password != body.new_password_confirm:
        raise HTTPException(status_code=400, detail="password_mismatch")
    ok, key = validate_password_strength(body.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=key)
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}

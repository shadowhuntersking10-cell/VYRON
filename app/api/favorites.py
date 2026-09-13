"""Favorites API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import models
from app.dependencies import Db, require_user

router = APIRouter(prefix="/api/favorites", tags=["favorites"])
ALLOWED = {"game", "product", "listing"}


class FavIn(BaseModel):
    target_type: str
    target_id: int


@router.get("")
def list_favs(request: Request, db: Db):
    user = require_user(request, db)
    favs = db.query(models.Favorite).filter_by(user_id=user.id).all()
    return {"items": [{"type": f.target_type, "id": f.target_id} for f in favs]}


@router.post("")
def toggle(body: FavIn, request: Request, db: Db):
    user = require_user(request, db)
    if body.target_type not in ALLOWED:
        raise HTTPException(status_code=400, detail="invalid_target")
    existing = db.query(models.Favorite).filter_by(user_id=user.id, target_type=body.target_type,
                                                   target_id=body.target_id).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"ok": True, "favorited": False}
    db.add(models.Favorite(user_id=user.id, target_type=body.target_type, target_id=body.target_id))
    db.commit()
    return {"ok": True, "favorited": True}

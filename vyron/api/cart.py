"""Cart API — items are always re-priced on the server."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.db.base import get_db
from vyron.db.models import User
from vyron.security.rbac import get_current_user
from vyron.services import cart_service
from vyron.web.serializers import cart_payload

router = APIRouter(prefix="/api/cart", tags=["cart"])


def _payload(db: DbSession, user: User) -> Dict[str, Any]:
    return ok(cart_payload(cart_service.calculate(db, user)))


@router.get("")
def get_cart(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    return _payload(db, user)


@router.post("/items")
def add_item(
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cart_service.add_item(
        db,
        user,
        variant_id=str(payload.get("variant_id", "")),
        quantity=int(payload.get("quantity", 1)),
        required_field_values=payload.get("required_field_values") or payload.get("topup_fields") or {},
    )
    return _payload(db, user) | {"message_code": "CART_ADDED"}


@router.patch("/items/{item_id}")
def update_item(
    item_id: str,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cart_service.update_item(db, user, item_id, int(payload.get("quantity", 1)))
    return _payload(db, user)


@router.delete("/items/{item_id}")
def remove_item(item_id: str, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    cart_service.remove_item(db, user, item_id)
    return _payload(db, user)


@router.delete("")
def clear_cart(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    cart_service.clear_cart(db, user)
    return _payload(db, user) | {"message_code": "CART_CLEARED"}


@router.post("/coupon")
def apply_coupon(
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cart_service.set_coupon(db, user, str(payload.get("code", "")))
    return _payload(db, user) | {"message_code": "COUPON_APPLIED"}


@router.delete("/coupon")
def remove_coupon(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    cart_service.clear_coupon(db, user)
    return _payload(db, user)

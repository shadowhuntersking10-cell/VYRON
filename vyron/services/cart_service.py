"""Cart service — server-side cart with server-computed totals.

The frontend never sends prices: every amount is re-derived from the database
on each call. Required top-up fields (playerId, region, ...) are validated
against the product/game configuration server-side.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from vyron.db.models import Cart, CartItem, Game, Product, ProductVariant, User
from vyron.errors import NotFoundError, ValidationError
from vyron.money import sum_money, to_money
from vyron.services import coupon_service, settings_service


# --- dynamic required fields -----------------------------------------------------
def validate_required_fields(product: Product, values: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate user-supplied top-up fields against the configured schema.

    Schema (product.required_fields or game.required_fields):
      [{"name"|"key": "playerId", "label": "Player ID", "type": "text|number|select",
        "required": true, "pattern": "^\\d{6,12}$", "options": ["eu","asia"],
        "min": 1, "max": 200}]
    """
    schema: List[dict] = product.effective_required_fields
    values = dict(values or {})
    cleaned: Dict[str, Any] = {}
    for field in schema:
        name = str(field.get("name") or field.get("key") or "").strip()
        if not name:
            continue
        raw = values.get(name)
        required = bool(field.get("required", False))
        field_type = str(field.get("type", "text")).lower()
        label = str(field.get("label", name))

        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if required:
                raise ValidationError(f"Field '{label}' is required.", code="REQUIRED_FIELD_MISSING", details={"field": name})
            continue

        if field_type == "number":
            try:
                number = float(str(raw))
                if field.get("min") is not None and number < float(field["min"]):
                    raise ValidationError(f"Field '{label}' is below minimum.", code="FIELD_INVALID", details={"field": name})
                if field.get("max") is not None and number > float(field["max"]):
                    raise ValidationError(f"Field '{label}' exceeds maximum.", code="FIELD_INVALID", details={"field": name})
                cleaned[name] = number
                continue
            except ValueError:
                raise ValidationError(f"Field '{label}' must be a number.", code="FIELD_INVALID", details={"field": name})

        text = str(raw).strip()
        max_len = int(field.get("max_length") or field.get("max") or 200)
        if len(text) > max_len:
            raise ValidationError(f"Field '{label}' is too long.", code="FIELD_INVALID", details={"field": name})

        pattern = field.get("pattern")
        if pattern:
            try:
                if not re.match(str(pattern), text):
                    raise ValidationError(
                        str(field.get("pattern_error") or f"Field '{label}' has an invalid format."),
                        code="FIELD_INVALID",
                        details={"field": name},
                    )
            except re.error:
                pass  # bad pattern configured — skip pattern check rather than break checkout

        options = field.get("options")
        if isinstance(options, list) and options and text not in [str(o) for o in options]:
            raise ValidationError(f"Field '{label}' must be one of: {', '.join(str(o) for o in options)}.", code="FIELD_INVALID", details={"field": name})

        cleaned[name] = text
    return cleaned


# --- cart operations ----------------------------------------------------------------
def get_or_create_cart(db: DbSession, user: User) -> Cart:
    cart = db.query(Cart).filter(Cart.user_id == user.id).first()
    if cart is None:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.commit()
    return cart


def add_item(
    db: DbSession,
    user: User,
    variant_id: str,
    quantity: int = 1,
    required_field_values: Optional[Dict[str, Any]] = None,
) -> CartItem:
    variant = db.get(ProductVariant, variant_id)
    if variant is None or not variant.active:
        raise NotFoundError("This product option is not available.")
    product = db.get(Product, variant.product_id)
    if product is None or not product.active:
        raise NotFoundError("This product is not available.")
    quantity = max(1, min(int(quantity or 1), 99))
    if variant.stock is not None and variant.stock >= 0 and variant.stock < quantity:
        raise ValidationError("Not enough stock for the requested quantity.", code="OUT_OF_STOCK")

    cleaned_values = validate_required_fields(product, required_field_values)
    values_hash = CartItem.compute_values_hash(cleaned_values)

    cart = get_or_create_cart(db, user)
    existing = (
        db.query(CartItem)
        .filter(CartItem.cart_id == cart.id, CartItem.variant_id == variant.id, CartItem.values_hash == values_hash)
        .first()
    )
    if existing:
        existing.quantity = min(99, existing.quantity + quantity)
        db.commit()
        return existing
    item = CartItem(
        cart_id=cart.id,
        variant_id=variant.id,
        quantity=quantity,
        required_field_values=cleaned_values,
        values_hash=values_hash,
    )
    db.add(item)
    db.commit()
    return item


def update_item(db: DbSession, user: User, item_id: str, quantity: int) -> CartItem:
    cart = get_or_create_cart(db, user)
    item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
    if item is None:
        raise NotFoundError("Cart item not found.")
    quantity = int(quantity)
    if quantity <= 0:
        db.delete(item)
        db.commit()
        return item
    variant = db.get(ProductVariant, item.variant_id)
    if variant and variant.stock is not None and variant.stock >= 0 and variant.stock < quantity:
        raise ValidationError("Not enough stock for the requested quantity.", code="OUT_OF_STOCK")
    item.quantity = min(99, quantity)
    db.commit()
    return item


def remove_item(db: DbSession, user: User, item_id: str) -> None:
    cart = get_or_create_cart(db, user)
    deleted = db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).delete()
    db.commit()
    if not deleted:
        raise NotFoundError("Cart item not found.")


def set_coupon(db: DbSession, user: User, code: str) -> Decimal:
    cart = get_or_create_cart(db, user)
    coupon = coupon_service.find_coupon(db, code)
    if coupon is None:
        cart.coupon_code = None
        db.commit()
        raise ValidationError("This coupon code is not valid.", code="COUPON_INVALID")
    summary = calculate(db, user, ignore_coupon=True)
    items = [(line["variant"], line["quantity"]) for line in summary["lines"]]
    discount = coupon_service.validate_coupon(db, coupon, user, summary["subtotal"], items)
    cart.coupon_code = coupon.code
    db.commit()
    return discount


def clear_coupon(db: DbSession, user: User) -> None:
    cart = get_or_create_cart(db, user)
    cart.coupon_code = None
    db.commit()


def calculate(db: DbSession, user: User, ignore_coupon: bool = False) -> Dict[str, Any]:
    """Server-side totals: subtotal, discount, service fee, total (all Decimal)."""
    cart = get_or_create_cart(db, user)
    lines: List[Dict[str, Any]] = []
    subtotal = Decimal("0.00")
    for item in cart.items:
        variant = db.get(ProductVariant, item.variant_id)
        if variant is None or not variant.active:
            continue
        product = db.get(Product, variant.product_id)
        game = db.get(Game, product.game_id) if product and product.game_id else None
        line_total = to_money(Decimal(str(variant.selling_price)) * item.quantity)
        subtotal += line_total
        lines.append(
            {
                "item_id": item.id,
                "variant": variant,
                "product": product,
                "game": game,
                "quantity": item.quantity,
                "unit_price": to_money(variant.selling_price),
                "line_total": line_total,
                "required_field_values": item.required_field_values or {},
                "required_fields": product.effective_required_fields if product else [],
            }
        )

    discount = Decimal("0.00")
    coupon = None
    coupon_error: Optional[str] = None
    if not ignore_coupon and cart.coupon_code:
        coupon = coupon_service.find_coupon(db, cart.coupon_code)
        if coupon is not None:
            try:
                discount = coupon_service.validate_coupon(
                    db, coupon, user, subtotal, [(line["variant"], line["quantity"]) for line in lines]
                )
            except Exception as exc:
                coupon_error = str(exc)
                discount = Decimal("0.00")

    fee = settings_service.service_fee(db, subtotal - discount) if lines else Decimal("0.00")
    total = sum_money(subtotal, -discount, fee)
    return {
        "cart": cart,
        "lines": lines,
        "subtotal": to_money(subtotal),
        "discount": to_money(discount),
        "coupon": coupon,
        "coupon_error": coupon_error,
        "service_fee": to_money(fee),
        "total": to_money(total),
        "currency": "USD",
    }


def clear_cart(db: DbSession, user: User) -> Cart:
    cart = get_or_create_cart(db, user)
    for item in list(cart.items):
        db.delete(item)
    cart.coupon_code = None
    db.commit()
    return cart

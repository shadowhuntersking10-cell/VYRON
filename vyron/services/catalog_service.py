"""Catalog admin service — games, products and variants.

`cost_price` (supplier cost) is accepted ONLY through admin endpoints and is
never exposed by public serializers.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from vyron.db.models import Game, Product, ProductVariant, User
from vyron.enums import GameStatus, ProductType
from vyron.errors import ValidationError
from vyron.money import to_money
from vyron.services import audit_service


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:120] or "item"


def _unique_slug(db: DbSession, model, base: str, exclude_id: Optional[str] = None) -> str:
    slug = base
    counter = 1
    while True:
        query = db.query(model).filter(model.slug == slug)
        if exclude_id:
            query = query.filter(model.id != exclude_id)
        if query.first() is None:
            return slug
        counter += 1
        slug = f"{base}-{counter}"


def upsert_game(db: DbSession, admin: User, game: Optional[Game], payload: Dict[str, Any]) -> Game:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValidationError("Game name is required.", code="NAME_REQUIRED")
    status = str(payload.get("status", GameStatus.ACTIVE.value)).upper()
    if status not in {s.value for s in GameStatus}:
        raise ValidationError("Invalid game status.", code="STATUS_INVALID")

    if game is None:
        slug = _unique_slug(db, Game, slugify(payload.get("slug") or name))
        game = Game(name=name[:140], slug=slug)
        db.add(game)
        action = "game.created"
    else:
        action = "game.updated"
        if payload.get("slug"):
            game.slug = _unique_slug(db, Game, slugify(str(payload["slug"])), exclude_id=game.id)

    game.name = name[:140]
    game.description = (payload.get("description") or "").strip()[:2000] or None
    game.logo_url = (payload.get("logo_url") or "").strip()[:500] or None
    game.banner_url = (payload.get("banner_url") or "").strip()[:500] or None
    game.accent_color = (payload.get("accent_color") or "").strip()[:16] or None
    game.status = status
    game.is_featured = bool(payload.get("is_featured", game.is_featured))
    game.sort_order = int(payload.get("sort_order", game.sort_order or 0))
    if "required_fields" in payload:
        game.required_fields = _clean_field_schema(payload.get("required_fields"))
    db.commit()
    audit_service.record_admin_action(db, admin, action, target_type="game", target_id=game.id, data={"name": game.name})
    return game


def _clean_field_schema(fields: Any) -> List[dict]:
    """Normalize the dynamic required-field schema (list of dicts)."""
    cleaned: List[dict] = []
    if not isinstance(fields, list):
        return cleaned
    for raw in fields[:20]:
        if not isinstance(raw, dict):
            continue
        key = re.sub(r"[^a-zA-Z0-9_]", "", str(raw.get("key", "")))[:40]
        if not key:
            continue
        cleaned.append(
            {
                "key": key,
                "label": str(raw.get("label", key))[:80],
                "type": str(raw.get("type", "text"))[:16],
                "required": bool(raw.get("required", True)),
                "placeholder": str(raw.get("placeholder", ""))[:120],
                "pattern": str(raw.get("pattern", ""))[:200],
                "help": str(raw.get("help", ""))[:200],
            }
        )
    return cleaned


def upsert_product(db: DbSession, admin: User, product: Optional[Product], payload: Dict[str, Any]) -> Product:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValidationError("Product name is required.", code="NAME_REQUIRED")
    product_type = str(payload.get("type", ProductType.TOPUP.value)).upper()
    if product_type not in {t.value for t in ProductType}:
        raise ValidationError("Invalid product type.", code="TYPE_INVALID")
    game_id = payload.get("game_id") or None
    if game_id and db.get(Game, game_id) is None:
        raise ValidationError("Unknown game.", code="GAME_NOT_FOUND")

    if product is None:
        slug = _unique_slug(db, Product, slugify(payload.get("slug") or name))
        product = Product(name=name[:200], slug=slug)
        db.add(product)
        action = "product.created"
    else:
        action = "product.updated"
        if payload.get("slug"):
            product.slug = _unique_slug(db, Product, slugify(str(payload["slug"])), exclude_id=product.id)

    product.name = name[:200]
    product.type = product_type
    product.description = (payload.get("description") or "").strip()[:4000] or None
    product.image_url = (payload.get("image_url") or "").strip()[:500] or None
    product.game_id = game_id
    product.is_featured = bool(payload.get("is_featured", product.is_featured))
    product.active = bool(payload.get("active", True if product.active is None else product.active))
    product.sort_order = int(payload.get("sort_order", product.sort_order or 0))
    if "required_fields" in payload:
        product.required_fields = _clean_field_schema(payload.get("required_fields"))
    db.flush()

    if "variants" in payload:
        _sync_variants(db, product, payload.get("variants") or [])
    db.commit()
    audit_service.record_admin_action(db, admin, action, target_type="product", target_id=product.id, data={"name": product.name})
    return product


def _sync_variants(db: DbSession, product: Product, rows: List[Dict[str, Any]]) -> None:
    existing = {v.id: v for v in product.variants}
    seen: set = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            price = to_money(row.get("selling_price"))
        except Exception:
            raise ValidationError(f"Invalid price for variant '{row.get('name')}'.", code="PRICE_INVALID")
        if price <= 0:
            raise ValidationError("Selling price must be positive.", code="PRICE_INVALID")
        cost = row.get("cost_price")
        cost_value = to_money(cost) if cost not in (None, "") else None

        variant_id = row.get("id")
        if variant_id and variant_id in existing:
            variant = existing[variant_id]
            seen.add(variant_id)
        else:
            variant = ProductVariant(product_id=product.id)
            db.add(variant)
        variant.name = str(row.get("name") or "Variant")[:140]
        variant.selling_price = price
        if cost_value is not None:
            variant.cost_price = cost_value
        variant.currency = str(row.get("currency") or "USD").upper()[:8]
        variant.stock = int(row.get("stock", variant.stock or 0))
        variant.active = bool(row.get("active", True))
        variant.sort_order = int(row.get("sort_order", variant.sort_order or 0))
        variant.external_product_id = (row.get("external_product_id") or "").strip()[:120] or None
        db.flush()
        seen.add(variant.id)
    # Deactivate (never hard-delete — order items reference variants) removed rows.
    for variant_id, variant in existing.items():
        if variant_id not in seen:
            variant.active = False

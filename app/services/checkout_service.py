"""Checkout quoting + order creation. Backend is the ONLY price authority."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarketplaceListing, Order, OrderItem, OrderStatus, Product, ProductVariant
from app.services import coupon_service, settings_service
from app.services.catalog_service import get_game_by_slug, validate_customer_fields
from app.utils.helpers import generate_public_id, utcnow
from app.utils.money import D, money_add, money_percent, money_sub, quantize_money


class CheckoutError(ValueError):
    pass


async def _fees(db: AsyncSession, subtotal: Decimal) -> tuple[Decimal, Decimal]:
    fixed = D(await settings_service.get_float(db, "service_fee_fixed"))
    pct = D(await settings_service.get_float(db, "service_fee_percent"))
    service_fee = quantize_money(fixed + money_percent(subtotal, pct))
    return service_fee, Decimal("0.00")


async def quote(
    db: AsyncSession,
    *,
    product_id: int | None = None,
    variant_id: int | None = None,
    listing_id: int | None = None,
    quantity: int = 1,
    coupon_code: str | None = None,
    user_id: int | None = None,
    customer_fields: dict | None = None,
) -> dict:
    if quantity < 1 or quantity > 100:
        raise CheckoutError("bad_quantity")

    title, unit_price, currency = "", D(0), "UZS"
    game_id, product_obj = None, None
    kind = "product"

    if listing_id:
        listing = await db.get(MarketplaceListing, listing_id)
        if not listing or listing.status != "active":
            raise CheckoutError("listing_unavailable")
        if listing.stock != -1 and listing.stock < quantity:
            raise CheckoutError("out_of_stock")
        title, unit_price, currency, kind = listing.title, D(listing.price), listing.currency, "marketplace"
    else:
        if variant_id:
            variant = await db.get(ProductVariant, variant_id)
            if not variant or not variant.is_active:
                raise CheckoutError("variant_unavailable")
            product_obj = await db.get(Product, variant.product_id)
            title, unit_price = f"{product_obj.name} — {variant.name}" if product_obj else variant.name, D(variant.selling_price)
            currency = product_obj.currency if product_obj else "UZS"
            game_id = product_obj.game_id if product_obj else None
            if variant.stock != -1 and variant.stock < quantity:
                raise CheckoutError("out_of_stock")
        elif product_id:
            product_obj = await db.get(Product, product_id)
            if not product_obj or not product_obj.is_active:
                raise CheckoutError("product_unavailable")
            title, unit_price, currency = product_obj.name, D(product_obj.selling_price), product_obj.currency
            game_id = product_obj.game_id
            if product_obj.stock != -1 and product_obj.stock < quantity:
                raise CheckoutError("out_of_stock")
        else:
            raise CheckoutError("nothing_to_buy")

    subtotal = quantize_money(unit_price * quantity)
    discount: Decimal = D(0)
    applied = None
    if coupon_code:
        try:
            coupon, discount = await coupon_service.validate_coupon(
                db,
                coupon_code,
                user_id=user_id,
                subtotal=subtotal,
                game_id=game_id,
                product_id=(product_obj.id if product_obj else None),
            )
            applied = coupon.code
        except coupon_service.CouponError as exc:
            raise CheckoutError(f"coupon:{exc}") from exc

    service_fee, platform_fee = await _fees(db, money_sub(subtotal, discount))
    total = money_add(money_sub(subtotal, discount), money_add(service_fee, platform_fee))
    return {
        "kind": kind,
        "title": title,
        "unit_price": unit_price,
        "quantity": quantity,
        "subtotal": subtotal,
        "discount": discount,
        "service_fee": service_fee,
        "platform_fee": platform_fee,
        "total": total,
        "currency": currency,
        "coupon_applied": applied,
        "game_id": game_id,
        "product_id": product_obj.id if product_obj else None,
        "variant_id": variant_id,
        "listing_id": listing_id,
    }


async def create_order(
    db: AsyncSession,
    *,
    user_id: int | None,
    product_id: int | None = None,
    variant_id: int | None = None,
    listing_id: int | None = None,
    quantity: int = 1,
    coupon_code: str | None = None,
    customer_fields: dict | None = None,
    idempotency_key: str | None = None,
) -> Order:
    q = await quote(
        db,
        product_id=product_id,
        variant_id=variant_id,
        listing_id=listing_id,
        quantity=quantity,
        coupon_code=coupon_code,
        user_id=user_id,
        customer_fields=customer_fields,
    )
    key = idempotency_key or uuid.uuid4().hex
    existing = (await db.execute(select(Order).where(Order.idempotency_key == key))).scalars().first()
    if existing:
        return existing

    cleaned_fields: dict = dict(customer_fields or {})
    # Validate game player fields for top-up products
    if q["game_id"]:
        from app.models import Game  # local import

        game = await db.get(Game, q["game_id"])
        if game and (game.fields_schema or []):
            try:
                cleaned_fields = await validate_customer_fields(game, customer_fields or {})
            except ValueError as exc:
                raise CheckoutError(str(exc)) from exc

    order = Order(
        public_id=generate_public_id(),
        user_id=user_id,
        status=OrderStatus.PENDING_PAYMENT,
        idempotency_key=key,
        subtotal=q["subtotal"],
        discount=q["discount"],
        service_fee=q["service_fee"],
        platform_fee=q["platform_fee"],
        total=q["total"],
        currency=q["currency"],
        coupon_code=q["coupon_applied"],
        customer_fields=cleaned_fields,
        timeline=[{"event": "order_created", "at": utcnow().isoformat()}],
    )
    db.add(order)
    await db.flush()

    supplier_cost = D(0)
    if q["product_id"]:
        prod = await db.get(Product, q["product_id"])
        if q["variant_id"]:
            var = await db.get(ProductVariant, q["variant_id"])
            supplier_cost = D(var.supplier_cost) * quantity if var else D(0)
        elif prod:
            supplier_cost = D(prod.supplier_cost) * quantity

    db.add(
        OrderItem(
            order_id=order.id,
            kind=q["kind"],
            product_id=q["product_id"],
            variant_id=q["variant_id"],
            listing_id=q["listing_id"],
            title=q["title"],
            quantity=quantity,
            unit_price=q["unit_price"],
            total_price=q["subtotal"],
            supplier_cost=quantize_money(supplier_cost),
        )
    )
    if q["coupon_applied"]:
        from app.models import Coupon  # local import

        coupon = (await db.execute(select(Coupon).where(Coupon.code == q["coupon_applied"]))).scalars().first()
        if coupon:
            await coupon_service.record_usage(db, coupon, user_id=user_id, order_id=order.id)
    await db.flush()
    return order
